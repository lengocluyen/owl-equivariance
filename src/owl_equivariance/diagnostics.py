"""Publication gates for response-channel, API and parser validity.

Headline task accuracy is not interpretable when most failures are empty or malformed
responses.  This module reports correctness and response validity separately and exits
through an explicit gate before a large inference run can begin.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import reporting
from .schemas import BenchmarkItem, Prediction


DIAGNOSTIC_COLUMNS = [
    "condition",
    "n",
    "accuracy",
    "valid_response_rate",
    "valid_only_accuracy",
    "invalid",
    "api_errors",
    "parse_errors",
    "empty_outputs",
    "length_finishes",
    "response_payload_rate",
]


@dataclass
class DiagnosticResult:
    rows: list[dict]
    totals: dict
    parse_error_counts: dict[str, int]
    runner_error_counts: dict[str, int]
    answer_field_counts: dict[str, int]
    finish_reason_counts: dict[str, int]
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "totals": self.totals,
            "by_condition": self.rows,
            "parse_error_counts": self.parse_error_counts,
            "runner_error_counts": self.runner_error_counts,
            "answer_field_counts": self.answer_field_counts,
            "finish_reason_counts": self.finish_reason_counts,
            "failures": self.failures,
        }


def _legacy_runner_error(prediction: Prediction) -> str | None:
    """Recognize old files that stored transport failures in ``parse_error``."""
    if prediction.runner_error:
        return prediction.runner_error
    value = prediction.parse_error or ""
    markers = ("connection error:", "APIStatusError:", "response_status:", "empty_choices")
    return value if value.startswith(markers) else None


def analyze(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    *,
    max_invalid_rate: float = 0.02,
    max_overall_invalid_rate: float | None = None,
    max_api_error_rate: float = 0.0,
    require_response_payload: bool = False,
    require_answer_field: str | None = None,
) -> DiagnosticResult:
    if not 0 <= max_invalid_rate <= 1:
        raise ValueError("max_invalid_rate must be between 0 and 1")
    if (
        max_overall_invalid_rate is not None
        and not 0 <= max_overall_invalid_rate <= 1
    ):
        raise ValueError("max_overall_invalid_rate must be between 0 and 1")
    if not 0 <= max_api_error_rate <= 1:
        raise ValueError("max_api_error_rate must be between 0 and 1")

    by_id = {item.orbit_item_id: item for item in items}
    grouped: dict[str, list[tuple[BenchmarkItem, Prediction]]] = defaultdict(list)
    missing_items = 0
    duplicate_keys = Counter(
        (p.model, p.orbit_item_id, p.repeat) for p in predictions
    )
    for prediction in predictions:
        item = by_id.get(prediction.orbit_item_id)
        if item is None:
            missing_items += 1
            continue
        grouped[item.condition].append((item, prediction))

    parse_errors: Counter[str] = Counter()
    runner_errors: Counter[str] = Counter()
    answer_fields: Counter[str] = Counter()
    finish_reasons: Counter[str] = Counter()
    rows: list[dict] = []

    for condition in sorted(grouped):
        pairs = grouped[condition]
        n = len(pairs)
        valid = sum(pred.label is not None for _, pred in pairs)
        correct = sum(pred.label == item.task.label for item, pred in pairs)
        api_errors = sum(_legacy_runner_error(pred) is not None for _, pred in pairs)
        empty = sum(not pred.raw_output.strip() for _, pred in pairs)
        length_finishes = 0
        payloads = 0
        for _, pred in pairs:
            if pred.parse_error:
                parse_errors[pred.parse_error] += 1
            runner_error = _legacy_runner_error(pred)
            if runner_error:
                runner_errors[runner_error] += 1
            field_name = str(pred.runner_metadata.get("selected_answer_field") or "unknown")
            answer_fields[field_name] += 1
            finish = str(pred.runner_metadata.get("finish_reason") or "unknown")
            finish_reasons[finish] += 1
            if finish in {"length", "max_tokens", "max_output_tokens"}:
                length_finishes += 1
            if pred.response_payload is not None:
                payloads += 1

        rows.append(
            {
                "condition": condition,
                "n": n,
                "accuracy": correct / n if n else 0.0,
                "valid_response_rate": valid / n if n else 0.0,
                "valid_only_accuracy": correct / valid if valid else None,
                "invalid": n - valid,
                "api_errors": api_errors,
                "parse_errors": sum(pred.parse_error is not None for _, pred in pairs),
                "empty_outputs": empty,
                "length_finishes": length_finishes,
                "response_payload_rate": payloads / n if n else 0.0,
            }
        )

    n = sum(row["n"] for row in rows)
    invalid = sum(row["invalid"] for row in rows)
    api_errors = sum(row["api_errors"] for row in rows)
    correct = sum(
        pred.label == item.task.label
        for pairs in grouped.values()
        for item, pred in pairs
    )
    valid = n - invalid
    totals = {
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "valid_response_rate": valid / n if n else 0.0,
        "invalid_rate": invalid / n if n else 0.0,
        "valid_only_accuracy": correct / valid if valid else None,
        "api_error_rate": api_errors / n if n else 0.0,
        "missing_dataset_items": missing_items,
        "duplicate_prediction_keys": sum(v - 1 for v in duplicate_keys.values() if v > 1),
    }

    failures: list[str] = []
    if not predictions:
        failures.append("prediction file is empty")
    if missing_items:
        failures.append(f"{missing_items} predictions have no matching dataset item")
    duplicate_count = totals["duplicate_prediction_keys"]
    if duplicate_count:
        failures.append(f"{duplicate_count} duplicate model/item/repeat prediction keys")
    if totals["api_error_rate"] > max_api_error_rate:
        failures.append(
            f"API error rate {totals['api_error_rate']:.2%} exceeds "
            f"{max_api_error_rate:.2%}"
        )
    if (
        max_overall_invalid_rate is not None
        and totals["invalid_rate"] > max_overall_invalid_rate
    ):
        failures.append(
            f"overall invalid-response rate {totals['invalid_rate']:.2%} exceeds "
            f"{max_overall_invalid_rate:.2%}"
        )
    for row in rows:
        # Compare integer counts directly through the rate. Subtracting from 1.0 makes
        # exactly 1/20 appear as 0.050000000000000044 and incorrectly fail an inclusive
        # 5% diagnostic ceiling.
        invalid_rate = row["invalid"] / row["n"] if row["n"] else 0.0
        if invalid_rate > max_invalid_rate:
            failures.append(
                f"{row['condition']} invalid-response rate {invalid_rate:.2%} exceeds "
                f"{max_invalid_rate:.2%}"
            )
    if require_response_payload:
        missing_payload = sum(
            pred.response_payload is None
            for pairs in grouped.values()
            for _, pred in pairs
        )
        if missing_payload:
            failures.append(f"{missing_payload}/{n} responses lack the full API payload")
    if require_answer_field:
        unexpected = {
            field_name: count
            for field_name, count in answer_fields.items()
            if field_name != require_answer_field
        }
        if unexpected:
            failures.append(
                f"answer field was not uniformly {require_answer_field!r}: {unexpected}"
            )

    return DiagnosticResult(
        rows=rows,
        totals=totals,
        parse_error_counts=dict(sorted(parse_errors.items())),
        runner_error_counts=dict(sorted(runner_errors.items())),
        answer_field_counts=dict(sorted(answer_fields.items())),
        finish_reason_counts=dict(sorted(finish_reasons.items())),
        failures=failures,
    )


def render_markdown(result: DiagnosticResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"# Response-validity diagnostic: {status}",
        "",
        reporting.markdown_table(result.rows, DIAGNOSTIC_COLUMNS),
        "",
        "## Totals",
        "",
        f"- Accuracy: {result.totals['accuracy']:.2%}",
        f"- Valid-response rate: {result.totals['valid_response_rate']:.2%}",
        f"- Accuracy conditional on a valid response: "
        f"{_percentage(result.totals['valid_only_accuracy'])}",
        f"- API-error rate: {result.totals['api_error_rate']:.2%}",
        f"- Answer fields: `{json.dumps(result.answer_field_counts, sort_keys=True)}`",
        f"- Finish reasons: `{json.dumps(result.finish_reason_counts, sort_keys=True)}`",
    ]
    if result.failures:
        lines.extend(["", "## Gate failures", ""])
        lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines) + "\n"


def _percentage(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.2%}"


def write_report(result: DiagnosticResult, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    reporting.write_csv(
        out / "response_validity_by_condition.csv",
        result.rows,
        DIAGNOSTIC_COLUMNS,
    )
    (out / "response_validity.json").write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "response_validity.md").write_text(
        render_markdown(result),
        encoding="utf-8",
    )
