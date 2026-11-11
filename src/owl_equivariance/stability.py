"""Repeat-subset analysis for nondeterministic local inference.

Repeated responses are summarized within item and model.  They are never pooled as
independent benchmark observations.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import reporting
from .schemas import BenchmarkItem, Prediction


STABILITY_COLUMNS = [
    "model",
    "condition",
    "n_items",
    "complete_items",
    "all_valid_rate",
    "unanimous_label_rate",
    "unanimous_valid_label_rate",
    "per_response_accuracy",
    "per_response_invalid_rate",
    "majority_vote_accuracy",
]


@dataclass
class StabilityResult:
    rows: list[dict]
    expected_repeats: int
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "expected_repeats": self.expected_repeats,
            "by_model_condition": self.rows,
            "failures": self.failures,
        }


def analyze(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    *,
    expected_repeats: int = 3,
) -> StabilityResult:
    if expected_repeats < 2:
        raise ValueError("expected_repeats must be at least 2")

    by_id = {item.orbit_item_id: item for item in items}
    slots: dict[tuple[str, str], dict[int, Prediction]] = defaultdict(dict)
    duplicate_keys: list[tuple[str, str, int]] = []
    missing_items = 0
    for prediction in predictions:
        if prediction.orbit_item_id not in by_id:
            # A full primary file is normally supplied beside the repeat-subset file.
            # Predictions outside the frozen subset are intentionally ignored.
            continue
        key = (prediction.model, prediction.orbit_item_id)
        if prediction.repeat in slots[key]:
            duplicate_keys.append((prediction.model, prediction.orbit_item_id, prediction.repeat))
        slots[key][prediction.repeat] = prediction

    models = sorted({model for model, _ in slots})
    grouped_items: dict[str, list[BenchmarkItem]] = defaultdict(list)
    for item in items:
        grouped_items[item.condition].append(item)

    rows: list[dict] = []
    failures: list[str] = []
    required = set(range(expected_repeats))
    if duplicate_keys:
        failures.append(f"{len(duplicate_keys)} duplicate model/item/repeat keys")
    if not models:
        failures.append("no predictions match the repeat-subset dataset")

    for model in models:
        for condition in sorted(grouped_items):
            condition_items = grouped_items[condition]
            complete = 0
            all_valid = 0
            unanimous = 0
            unanimous_valid = 0
            correct_responses = 0
            invalid_responses = 0
            response_count = 0
            majority_correct = 0

            for item in condition_items:
                repeats = slots.get((model, item.orbit_item_id), {})
                if set(repeats) != required:
                    continue
                complete += 1
                labels = [repeats[index].label for index in sorted(required)]
                response_count += len(labels)
                invalid_responses += sum(label is None for label in labels)
                correct_responses += sum(label == item.task.label for label in labels)
                if all(label is not None for label in labels):
                    all_valid += 1
                if len(set(labels)) == 1:
                    unanimous += 1
                    if labels[0] is not None:
                        unanimous_valid += 1
                votes = Counter(label for label in labels if label is not None)
                majority = votes.most_common()
                if majority and (
                    len(majority) == 1 or majority[0][1] > majority[1][1]
                ):
                    majority_correct += majority[0][0] == item.task.label

            n_items = len(condition_items)
            if complete != n_items:
                failures.append(
                    f"{model}/{condition}: {complete}/{n_items} items have exactly "
                    f"repeat indices {sorted(required)}"
                )
            rows.append(
                {
                    "model": model,
                    "condition": condition,
                    "n_items": n_items,
                    "complete_items": complete,
                    "all_valid_rate": all_valid / complete if complete else 0.0,
                    "unanimous_label_rate": unanimous / complete if complete else 0.0,
                    "unanimous_valid_label_rate": (
                        unanimous_valid / complete if complete else 0.0
                    ),
                    "per_response_accuracy": (
                        correct_responses / response_count if response_count else 0.0
                    ),
                    "per_response_invalid_rate": (
                        invalid_responses / response_count if response_count else 0.0
                    ),
                    "majority_vote_accuracy": (
                        majority_correct / complete if complete else 0.0
                    ),
                }
            )

    if missing_items:
        failures.append(f"{missing_items} repeat predictions have no matching item")
    return StabilityResult(
        rows=rows,
        expected_repeats=expected_repeats,
        failures=failures,
    )


def render_markdown(result: StabilityResult) -> str:
    lines = [
        f"# Repeat-subset stability: {'PASS' if result.passed else 'FAIL'}",
        "",
        f"Expected response indices per item: `0..{result.expected_repeats - 1}`.",
        "",
        reporting.markdown_table(result.rows, STABILITY_COLUMNS),
    ]
    if result.failures:
        lines.extend(["", "## Gate failures", ""])
        lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines) + "\n"


def write_report(result: StabilityResult, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    reporting.write_csv(out / "stability_by_condition.csv", result.rows, STABILITY_COLUMNS)
    (out / "stability.json").write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "stability.md").write_text(render_markdown(result), encoding="utf-8")
