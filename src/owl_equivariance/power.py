"""Simulation-based power for the paired McNemar confirmatory contrast."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from math import comb
from pathlib import Path

import numpy as np

from . import reporting
from .schemas import BenchmarkItem, Prediction


POWER_COLUMNS = [
    "model",
    "outcome",
    "reference",
    "condition",
    "pilot_pairs",
    "pilot_discordance_rate",
    "target_gap",
    "simulated_discordance_rate",
    "planned_pairs",
    "family_size",
    "alpha_per_contrast",
    "simulations",
    "estimated_power",
]


@dataclass
class PowerResult:
    rows: list[dict]
    min_power: float
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "minimum_required_power": self.min_power,
            "rows": self.rows,
            "failures": self.failures,
            "method": (
                "Monte Carlo paired McNemar power; observed pilot discordance is preserved "
                "unless it is smaller than the target gap. Bonferroni alpha/family_size is "
                "used as a conservative lower bound for the planned Holm family."
            ),
        }


@lru_cache(maxsize=None)
def _mcnemar_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, index) for index in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def analyze(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    *,
    reference: str = "C0",
    condition: str = "C4",
    outcome: str = "correct",
    planned_pairs: int = 1200,
    target_gap: float = 0.05,
    family_size: int = 10,
    alpha: float = 0.05,
    simulations: int = 10000,
    min_power: float = 0.80,
    seed: int = 20260725,
) -> PowerResult:
    if outcome not in {"correct", "parsed"}:
        raise ValueError("outcome must be 'correct' or 'parsed'")
    if not 0 < target_gap < 1:
        raise ValueError("target_gap must be between 0 and 1")
    if planned_pairs < 1 or family_size < 1 or simulations < 1:
        raise ValueError("planned_pairs, family_size and simulations must be positive")
    if any(pred.repeat != 0 for pred in predictions):
        raise ValueError("power calibration accepts primary repeat-0 predictions only")

    by_id = {item.orbit_item_id: item for item in items}
    paired: dict[str, dict[tuple[str, str], dict[str, bool]]] = {}
    for prediction in predictions:
        item = by_id.get(prediction.orbit_item_id)
        if item is None or item.condition not in {reference, condition}:
            continue
        if outcome == "correct":
            value = prediction.label == item.task.label
        else:
            value = prediction.label is not None
        key = (item.ontology.ontology_id, item.base_item_id)
        paired.setdefault(prediction.model, {}).setdefault(key, {})[item.condition] = value

    rows = []
    failures = []
    alpha_per_contrast = alpha / family_size
    for model_index, model in enumerate(sorted(paired)):
        complete = [
            values
            for values in paired[model].values()
            if reference in values and condition in values
        ]
        if not complete:
            failures.append(f"{model}: no complete {reference}/{condition} pairs")
            continue
        discordance = sum(
            values[reference] != values[condition] for values in complete
        ) / len(complete)
        simulated_discordance = max(discordance, target_gap)
        p_ref_only = (simulated_discordance + target_gap) / 2
        p_condition_only = (simulated_discordance - target_gap) / 2
        if p_ref_only > 1 or p_condition_only < 0:
            failures.append(
                f"{model}: target gap {target_gap:.3f} is incompatible with "
                f"discordance {simulated_discordance:.3f}"
            )
            continue

        rng = np.random.default_rng(seed + model_index)
        discordant_counts = rng.binomial(
            planned_pairs,
            simulated_discordance,
            size=simulations,
        )
        ref_only_probability = p_ref_only / simulated_discordance
        ref_only = rng.binomial(discordant_counts, ref_only_probability)
        condition_only = discordant_counts - ref_only
        significant = sum(
            _mcnemar_p(int(b), int(c)) <= alpha_per_contrast
            for b, c in zip(ref_only, condition_only)
        )
        estimated_power = significant / simulations
        row = {
            "model": model,
            "outcome": outcome,
            "reference": reference,
            "condition": condition,
            "pilot_pairs": len(complete),
            "pilot_discordance_rate": discordance,
            "target_gap": target_gap,
            "simulated_discordance_rate": simulated_discordance,
            "planned_pairs": planned_pairs,
            "family_size": family_size,
            "alpha_per_contrast": alpha_per_contrast,
            "simulations": simulations,
            "estimated_power": estimated_power,
        }
        rows.append(row)
        if estimated_power < min_power:
            failures.append(
                f"{model}/{outcome}: power {estimated_power:.1%} is below "
                f"{min_power:.1%}"
            )

    if not rows:
        failures.append("no power estimates were produced")
    return PowerResult(rows=rows, min_power=min_power, failures=failures)


def render_markdown(result: PowerResult) -> str:
    lines = [
        f"# Paired power simulation: {'PASS' if result.passed else 'FAIL'}",
        "",
        reporting.markdown_table(result.rows, POWER_COLUMNS),
        "",
        "The per-contrast alpha is Bonferroni-adjusted as a conservative lower bound "
        "for the planned Holm family.",
    ]
    if result.failures:
        lines.extend(["", "## Gate failures", ""])
        lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines) + "\n"


def write_report(result: PowerResult, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    reporting.write_csv(out / "power_by_model.csv", result.rows, POWER_COLUMNS)
    (out / "power.json").write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "power.md").write_text(render_markdown(result), encoding="utf-8")
