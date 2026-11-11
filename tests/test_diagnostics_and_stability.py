from __future__ import annotations

from owl_equivariance import diagnostics, stability
from owl_equivariance.schemas import BenchmarkItem, Prediction


def item(base: str, condition: str, label: str = "ENTAILED") -> BenchmarkItem:
    return BenchmarkItem.model_validate(
        {
            "base_item_id": base,
            "orbit_item_id": f"{base}:{condition}",
            "ontology": {"ontology_id": "toy"},
            "task": {
                "type": "ATOMIC_SUBSUMPTION",
                "query_functional": "SubClassOf(<A> <B>)",
                "label": label,
                "positive": label == "ENTAILED",
            },
            "transform": {
                "operator": "IDENTITY" if condition == "C0" else "RENAME",
                "lexical_condition": condition,
            },
            "context": {
                "axioms": [{"id": "A1", "text": "SubClassOf(<A> <B>)"}],
            },
        }
    )


def prediction(
    base: str,
    condition: str,
    label: str | None,
    *,
    repeat: int = 0,
    parse_error: str | None = None,
) -> Prediction:
    return Prediction(
        orbit_item_id=f"{base}:{condition}",
        base_item_id=base,
        condition=condition,
        model="model-a",
        prompt_style="structured_proof",
        label=label,
        raw_output="" if label is None else f'{{"label":"{label}"}}',
        parse_error=parse_error,
        repeat=repeat,
        runner_metadata={
            "selected_answer_field": "content",
            "finish_reason": "stop",
        },
        response_payload={"id": f"{base}-{condition}-{repeat}"},
    )


def test_diagnostic_separates_validity_from_valid_only_accuracy(tmp_path):
    items = [item("b1", "C0"), item("b1", "C1")]
    predictions = [
        prediction("b1", "C0", "ENTAILED"),
        prediction("b1", "C1", None, parse_error="empty_output"),
    ]
    result = diagnostics.analyze(
        items,
        predictions,
        max_invalid_rate=0.02,
        require_response_payload=True,
        require_answer_field="content",
    )

    assert not result.passed
    assert result.totals["accuracy"] == 0.5
    assert result.totals["valid_only_accuracy"] == 1.0
    assert any("C1 invalid-response rate" in failure for failure in result.failures)

    diagnostics.write_report(result, tmp_path)
    assert (tmp_path / "response_validity.json").exists()
    assert (tmp_path / "response_validity_by_condition.csv").exists()


def test_diagnostic_supports_distinct_inclusive_cell_and_overall_ceilings():
    items = []
    predictions = []
    for index in range(20):
        base = f"b{index}"
        items.append(item(base, "C0"))
        predictions.append(
            prediction(
                base,
                "C0",
                None if index == 0 else "ENTAILED",
                parse_error="malformed_json" if index == 0 else None,
            )
        )

    result = diagnostics.analyze(
        items,
        predictions,
        max_invalid_rate=0.05,
        max_overall_invalid_rate=0.05,
    )
    assert result.passed

    stricter_overall = diagnostics.analyze(
        items,
        predictions,
        max_invalid_rate=0.05,
        max_overall_invalid_rate=0.01,
    )
    assert not stricter_overall.passed
    assert any(
        "overall invalid-response rate" in failure
        for failure in stricter_overall.failures
    )


def test_stability_requires_and_summarizes_exact_three_repeats():
    items = [item("b1", "C0"), item("b1", "C1")]
    predictions = []
    for repeat in range(3):
        predictions.append(prediction("b1", "C0", "ENTAILED", repeat=repeat))
        predictions.append(
            prediction(
                "b1",
                "C1",
                "NOT_ENTAILED" if repeat == 2 else "ENTAILED",
                repeat=repeat,
            )
        )

    result = stability.analyze(items, predictions, expected_repeats=3)

    assert result.passed
    by_condition = {row["condition"]: row for row in result.rows}
    assert by_condition["C0"]["unanimous_valid_label_rate"] == 1.0
    assert by_condition["C1"]["unanimous_valid_label_rate"] == 0.0
    assert by_condition["C1"]["majority_vote_accuracy"] == 1.0


def test_stability_fails_on_missing_repeat():
    items = [item("b1", "C0")]
    predictions = [
        prediction("b1", "C0", "ENTAILED", repeat=0),
        prediction("b1", "C0", "ENTAILED", repeat=1),
    ]
    result = stability.analyze(items, predictions, expected_repeats=3)
    assert not result.passed
    assert "0/1 items" in result.failures[0]
