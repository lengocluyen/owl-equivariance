"""Answer-level metrics (spec section 20)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..schemas import BenchmarkItem, Prediction
from .stats import holm_correction, mcnemar_exact, paired_bootstrap_ci, wilson_interval


@dataclass
class ConditionMetrics:
    condition: str
    n: int = 0
    correct: int = 0
    invalid: int = 0
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def invalid_rate(self) -> float:
        return self.invalid / self.n if self.n else 0.0

    @property
    def valid_only_accuracy(self) -> float | None:
        valid = self.n - self.invalid
        return self.correct / valid if valid else None

    @property
    def accuracy_ci(self) -> tuple[float, float]:
        return wilson_interval(self.correct, self.n)

    def _prf(self, tp: int, fp: int, fn: int) -> tuple[float, float, float]:
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        return precision, recall, f1

    @property
    def entailed_prf(self) -> tuple[float, float, float]:
        return self._prf(self.tp, self.fp, self.fn)

    @property
    def not_entailed_prf(self) -> tuple[float, float, float]:
        return self._prf(self.tn, self.fn, self.fp)

    @property
    def macro_f1(self) -> float:
        return (self.entailed_prf[2] + self.not_entailed_prf[2]) / 2

    def as_dict(self) -> dict:
        lo, hi = self.accuracy_ci
        return {
            "condition": self.condition,
            "n": self.n,
            "accuracy": self.accuracy,
            "accuracy_ci_low": lo,
            "accuracy_ci_high": hi,
            "macro_f1": self.macro_f1,
            "entailed_precision": self.entailed_prf[0],
            "entailed_recall": self.entailed_prf[1],
            "not_entailed_precision": self.not_entailed_prf[0],
            "not_entailed_recall": self.not_entailed_prf[1],
            "invalid_rate": self.invalid_rate,
            "valid_only_accuracy": self.valid_only_accuracy,
        }


@dataclass
class PairedComparison:
    """One condition measured against the reference condition (spec 20.2 - 20.5)."""

    condition: str
    reference: str
    n_pairs: int
    invariance_gap: float
    correct_to_wrong: float
    wrong_to_correct: float
    pair_consistency: float
    p_value: float
    ci_low: float
    ci_high: float
    discordant_b: int = 0
    discordant_c: int = 0
    discordant_odds_ratio: float | None = None
    p_value_holm: float | None = None

    def as_dict(self) -> dict:
        return {
            "condition": self.condition,
            "reference": self.reference,
            "n_pairs": self.n_pairs,
            "invariance_gap": self.invariance_gap,
            "invariance_gap_ci_low": self.ci_low,
            "invariance_gap_ci_high": self.ci_high,
            "correct_to_wrong_flip_rate": self.correct_to_wrong,
            "wrong_to_correct_flip_rate": self.wrong_to_correct,
            "pair_consistency": self.pair_consistency,
            "mcnemar_p": self.p_value,
            "mcnemar_p_holm": self.p_value_holm,
            "discordant_correct_only_in_reference": self.discordant_b,
            "discordant_correct_only_in_condition": self.discordant_c,
            "discordant_odds_ratio_ref_over_condition": self.discordant_odds_ratio,
        }


@dataclass
class PairedValidityComparison:
    """Paired change in parse-valid output rate versus the reference condition."""

    condition: str
    reference: str
    n_pairs: int
    validity_gap: float
    ci_low: float
    ci_high: float
    valid_to_invalid: int
    invalid_to_valid: int
    pair_consistency: float
    p_value: float
    p_value_holm: float | None = None

    def as_dict(self) -> dict:
        odds_ratio = (
            self.valid_to_invalid / self.invalid_to_valid
            if self.invalid_to_valid
            else (float("inf") if self.valid_to_invalid else None)
        )
        return {
            "condition": self.condition,
            "reference": self.reference,
            "n_pairs": self.n_pairs,
            "validity_gap": self.validity_gap,
            "validity_gap_ci_low": self.ci_low,
            "validity_gap_ci_high": self.ci_high,
            "valid_to_invalid": self.valid_to_invalid,
            "invalid_to_valid": self.invalid_to_valid,
            "pair_consistency": self.pair_consistency,
            "mcnemar_p": self.p_value,
            "mcnemar_p_holm": self.p_value_holm,
            "discordant_odds_ratio_ref_over_condition": odds_ratio,
        }


def index_items(items: list[BenchmarkItem]) -> dict[str, BenchmarkItem]:
    return {i.orbit_item_id: i for i in items}


def per_condition(
    items: list[BenchmarkItem], predictions: list[Prediction]
) -> dict[str, ConditionMetrics]:
    by_id = index_items(items)
    out: dict[str, ConditionMetrics] = {}

    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is None:
            continue
        m = out.setdefault(item.condition, ConditionMetrics(condition=item.condition))
        m.n += 1
        gold = item.task.label

        if pred.label is None:
            # Unparseable counts as incorrect in the headline number, and is also
            # reported on its own line (spec section 19.2).
            m.invalid += 1
            if gold == "ENTAILED":
                m.fn += 1
            else:
                m.fp += 1
            continue

        if pred.label == gold:
            m.correct += 1
            if gold == "ENTAILED":
                m.tp += 1
            else:
                m.tn += 1
        elif gold == "ENTAILED":
            m.fn += 1
        else:
            m.fp += 1

    return out


def _paired_outcomes(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    reference: str,
    condition: str,
) -> tuple[list[bool], list[bool], list[tuple[str | None, str | None]]]:
    """Correctness vectors for the base items present in *both* conditions."""
    by_id = index_items(items)
    gold: dict[str, str] = {}
    per_base: dict[str, dict[str, Prediction]] = defaultdict(dict)

    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is None:
            continue
        per_base[item.base_item_id][item.condition] = pred
        gold[item.base_item_id] = item.task.label

    ref_correct: list[bool] = []
    cond_correct: list[bool] = []
    labels: list[tuple[str | None, str | None]] = []

    for base_id in sorted(per_base):
        slot = per_base[base_id]
        if reference not in slot or condition not in slot:
            continue
        want = gold[base_id]
        ref_correct.append(slot[reference].label == want)
        cond_correct.append(slot[condition].label == want)
        labels.append((slot[reference].label, slot[condition].label))

    return ref_correct, cond_correct, labels


def compare_to_reference(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    reference: str = "C0",
    n_resamples: int = 10000,
    seed: int = 42,
) -> list[PairedComparison]:
    conditions = sorted({index_items(items)[p.orbit_item_id].condition
                         for p in predictions
                         if p.orbit_item_id in index_items(items)})

    out: list[PairedComparison] = []
    for condition in conditions:
        if condition == reference:
            continue
        ref, cond, labels = _paired_outcomes(items, predictions, reference, condition)
        if not ref:
            continue

        gap, lo, hi = paired_bootstrap_ci(ref, cond, n_resamples=n_resamples, seed=seed)
        test = mcnemar_exact(ref, cond)

        ref_right = sum(ref)
        ref_wrong = len(ref) - ref_right
        cwf = sum(1 for r, c in zip(ref, cond) if r and not c) / ref_right if ref_right else 0.0
        wcf = sum(1 for r, c in zip(ref, cond) if not r and c) / ref_wrong if ref_wrong else 0.0
        consistency = sum(1 for a, b in labels if a == b) / len(labels)

        out.append(
            PairedComparison(
                condition=condition,
                reference=reference,
                n_pairs=len(ref),
                invariance_gap=gap,
                correct_to_wrong=cwf,
                wrong_to_correct=wcf,
                pair_consistency=consistency,
                p_value=test.p_value,
                ci_low=lo,
                ci_high=hi,
                discordant_b=test.b,
                discordant_c=test.c,
                discordant_odds_ratio=test.odds_ratio,
            )
        )

    # Every condition is tested against the same reference, so this is a family of
    # comparisons and the raw p-values are optimistic. Holm is applied here rather than
    # left to the caller: an uncorrected p reported next to eight comparisons is the single
    # easiest way for this pipeline to overstate a result.
    if out:
        adjusted = holm_correction({c.condition: c.p_value for c in out})
        for comparison in out:
            comparison.p_value_holm = adjusted[comparison.condition]
    return out


def compare_validity_to_reference(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    reference: str = "C0",
    n_resamples: int = 10000,
    seed: int = 42,
) -> list[PairedValidityComparison]:
    """Compare structured-output validity with the same paired design as accuracy."""
    by_id = index_items(items)
    per_base: dict[str, dict[str, Prediction]] = defaultdict(dict)
    for prediction in predictions:
        item = by_id.get(prediction.orbit_item_id)
        if item is not None:
            per_base[item.base_item_id][item.condition] = prediction

    conditions = sorted(
        {
            item.condition
            for item in by_id.values()
            if item.condition != reference
        }
    )
    out: list[PairedValidityComparison] = []
    for condition in conditions:
        ref_valid: list[bool] = []
        cond_valid: list[bool] = []
        for base_id in sorted(per_base):
            slot = per_base[base_id]
            if reference not in slot or condition not in slot:
                continue
            ref_valid.append(slot[reference].label is not None)
            cond_valid.append(slot[condition].label is not None)
        if not ref_valid:
            continue
        gap, lo, hi = paired_bootstrap_ci(
            ref_valid,
            cond_valid,
            n_resamples=n_resamples,
            seed=seed,
        )
        test = mcnemar_exact(ref_valid, cond_valid)
        out.append(
            PairedValidityComparison(
                condition=condition,
                reference=reference,
                n_pairs=len(ref_valid),
                validity_gap=gap,
                ci_low=lo,
                ci_high=hi,
                valid_to_invalid=test.b,
                invalid_to_valid=test.c,
                pair_consistency=sum(a == b for a, b in zip(ref_valid, cond_valid))
                / len(ref_valid),
                p_value=test.p_value,
            )
        )
    if out:
        adjusted = holm_correction({row.condition: row.p_value for row in out})
        for row in out:
            row.p_value_holm = adjusted[row.condition]
    return out


@dataclass
class SeedDisagreement:
    """Self-inconsistency between two logically indistinguishable renamings.

    Two seeds of the same operator differ only in which arbitrary integer generated the
    identifiers. A model that answers them differently is contradicting itself on the same
    problem -- the cleanest available evidence that the answer is not coming from the
    logic, and the reason the pilot ships seed replicates at all.
    """

    condition_a: str
    condition_b: str
    n_pairs: int
    disagreement_rate: float
    both_correct: int = 0
    both_wrong: int = 0
    exactly_one_correct: int = 0
    fields: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "condition_a": self.condition_a,
            "condition_b": self.condition_b,
            "n_pairs": self.n_pairs,
            "disagreement_rate": self.disagreement_rate,
            "both_correct": self.both_correct,
            "both_wrong": self.both_wrong,
            "exactly_one_correct": self.exactly_one_correct,
        }


def seed_disagreement(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    condition_a: str,
    condition_b: str,
) -> SeedDisagreement | None:
    ref, cond, labels = _paired_outcomes(items, predictions, condition_a, condition_b)
    if not labels:
        return None

    disagree = sum(1 for a, b in labels if a != b)
    both_right = sum(1 for r, c in zip(ref, cond) if r and c)
    both_wrong = sum(1 for r, c in zip(ref, cond) if not r and not c)
    one = len(ref) - both_right - both_wrong

    return SeedDisagreement(
        condition_a=condition_a,
        condition_b=condition_b,
        n_pairs=len(labels),
        disagreement_rate=disagree / len(labels),
        both_correct=both_right,
        both_wrong=both_wrong,
        exactly_one_correct=one,
    )
