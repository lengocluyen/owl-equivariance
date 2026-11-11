"""Orbit-level metrics (spec section 21).

Per-condition accuracy answers "how often is it right on this kind of input". Orbit metrics
answer the question the study is actually about: "is it right on *every* presentation of the
same problem". A model can hold 80% on each of five conditions and still get zero robust
orbit accuracy, if it fails a different fifth of the items each time.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..schemas import BenchmarkItem, Prediction


@dataclass
class OrbitMetrics:
    n_orbits: int = 0
    robust_orbit_accuracy: float = 0.0
    orbit_consistency: float = 0.0
    worst_condition: str | None = None
    worst_condition_accuracy: float = 0.0
    mean_orbit_degradation: float = 0.0
    failure_histogram: dict[int, int] = field(default_factory=dict)
    conditions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "n_orbits": self.n_orbits,
            "robust_orbit_accuracy": self.robust_orbit_accuracy,
            "orbit_consistency": self.orbit_consistency,
            "worst_condition": self.worst_condition,
            "worst_condition_accuracy": self.worst_condition_accuracy,
            "mean_orbit_degradation": self.mean_orbit_degradation,
            "failure_histogram": {str(k): v for k, v in sorted(self.failure_histogram.items())},
            "conditions": self.conditions,
        }


def compute(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    reference: str = "C0",
    require_conditions: list[str] | None = None,
) -> OrbitMetrics:
    by_id = {i.orbit_item_id: i for i in items}
    orbits: dict[str, dict[str, tuple[BenchmarkItem, Prediction]]] = defaultdict(dict)

    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is not None:
            orbits[item.base_item_id][item.condition] = (item, pred)

    if not orbits:
        return OrbitMetrics()

    all_conditions = sorted({c for slot in orbits.values() for c in slot})
    needed = require_conditions or all_conditions

    # Only complete orbits count. A partially-evaluated orbit would silently inflate
    # robustness, since the missing member is the one that might have failed.
    complete = {
        base: slot for base, slot in orbits.items() if all(c in slot for c in needed)
    }
    if not complete:
        return OrbitMetrics(conditions=all_conditions)

    robust = 0
    consistent = 0
    degradations: list[float] = []
    failures: dict[int, int] = defaultdict(int)
    per_condition_correct: dict[str, list[bool]] = defaultdict(list)

    for slot in complete.values():
        outcomes = {}
        labels = set()
        for condition in needed:
            item, pred = slot[condition]
            correct = pred.label == item.task.label
            outcomes[condition] = correct
            labels.add(pred.label)
            per_condition_correct[condition].append(correct)

        n_failed = sum(1 for v in outcomes.values() if not v)
        failures[n_failed] += 1
        if n_failed == 0:
            robust += 1
        if len(labels) == 1:
            consistent += 1

        if reference in outcomes:
            others = [v for c, v in outcomes.items() if c != reference]
            if others:
                degradations.append(
                    float(outcomes[reference]) - sum(others) / len(others)
                )

    accuracies = {
        condition: sum(values) / len(values)
        for condition, values in per_condition_correct.items()
        if values
    }
    if accuracies:
        # ``min`` also names a condition when every accuracy is exactly 1.0. The previous
        # strict-less-than loop returned ``None`` and then reported accuracy 0.0 for a
        # perfect oracle, an internally contradictory result.
        worst_condition = min(accuracies, key=lambda c: (accuracies[c], c))
        worst_acc = accuracies[worst_condition]
    else:
        worst_condition, worst_acc = None, 0.0

    n = len(complete)
    return OrbitMetrics(
        n_orbits=n,
        robust_orbit_accuracy=robust / n,
        orbit_consistency=consistent / n,
        worst_condition=worst_condition,
        worst_condition_accuracy=worst_acc,
        mean_orbit_degradation=sum(degradations) / len(degradations) if degradations else 0.0,
        failure_histogram=dict(failures),
        conditions=needed,
    )
