"""Proof-level metrics (spec section 22).

The headline number here is **CAIP**: the rate at which a model gives the correct answer
while citing axioms that do not entail it. Answer accuracy cannot see this at all -- the
item is scored correct -- yet it is the difference between a model that derived the
conclusion and one that guessed and then pointed at something plausible.

Every field these metrics read (``support_valid``, ``support_minimal``,
``unknown_support_ids``) is produced by the Java ``validate-support`` command, which decides
entailment with the same reasoner that generated the labels. Nothing here is judged by a
model.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..schemas import BenchmarkItem, Prediction
from .stats import wilson_interval


@dataclass
class ProofMetrics:
    condition: str
    n_positive: int = 0
    n_validated: int = 0
    answer_correct: int = 0
    support_valid: int = 0
    support_minimal: int = 0
    correct_answer_invalid_proof: int = 0
    hallucinated_ids: int = 0
    empty_support_on_positive: int = 0

    @property
    def support_validity_rate(self) -> float:
        return self.support_valid / self.n_validated if self.n_validated else 0.0

    @property
    def minimality_rate(self) -> float:
        return self.support_minimal / self.support_valid if self.support_valid else 0.0

    @property
    def caip_joint(self) -> float:
        """P(answer correct AND proof invalid) over validated positives.

        This is the specification's definition (section 22.7): a joint probability over all
        validated items, so it falls when the model answers fewer items correctly.
        """
        return (
            self.correct_answer_invalid_proof / self.n_validated if self.n_validated else 0.0
        )

    @property
    def caip_given_correct(self) -> float:
        """P(proof invalid | answer correct).

        The conditional form, reported alongside the joint one because the two answer
        different questions and move in different directions. A model that collapses to
        chance has a *low* joint CAIP simply by getting little right, while its conditional
        CAIP can be near 1: almost nothing it happens to get right is actually derived.
        Reporting either alone invites the wrong reading.
        """
        return (
            self.correct_answer_invalid_proof / self.answer_correct
            if self.answer_correct
            else 0.0
        )

    def as_dict(self) -> dict:
        joint_lo, joint_hi = wilson_interval(
            self.correct_answer_invalid_proof, max(self.n_validated, 0)
        )
        cond_lo, cond_hi = wilson_interval(
            self.correct_answer_invalid_proof, max(self.answer_correct, 0)
        )
        return {
            "condition": self.condition,
            "n_positive": self.n_positive,
            "n_validated": self.n_validated,
            "answer_accuracy_on_positives": (
                self.answer_correct / self.n_positive if self.n_positive else 0.0
            ),
            "support_validity_rate": self.support_validity_rate,
            "minimality_rate": self.minimality_rate,
            "caip_joint": self.caip_joint,
            "caip_joint_ci_low": joint_lo,
            "caip_joint_ci_high": joint_hi,
            "caip_given_correct": self.caip_given_correct,
            "caip_given_correct_ci_low": cond_lo,
            "caip_given_correct_ci_high": cond_hi,
            "hallucinated_axiom_id_count": self.hallucinated_ids,
            "empty_support_on_positive": self.empty_support_on_positive,
        }


def per_condition(
    items: list[BenchmarkItem], predictions: list[Prediction]
) -> dict[str, ProofMetrics]:
    by_id = {i.orbit_item_id: i for i in items}
    out: dict[str, ProofMetrics] = {}

    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is None or not item.task.positive:
            # Proof validity is only defined for entailed queries: the correct support for
            # a non-entailed query is the empty set, which no reasoner can "validate".
            continue

        m = out.setdefault(item.condition, ProofMetrics(condition=item.condition))
        m.n_positive += 1
        m.hallucinated_ids += len(pred.unknown_support_ids)

        correct = pred.label == item.task.label
        if correct:
            m.answer_correct += 1
        if correct and not pred.support_axiom_ids:
            m.empty_support_on_positive += 1

        if pred.support_valid is None:
            continue  # not run through the symbolic validator
        m.n_validated += 1
        if pred.support_valid:
            m.support_valid += 1
            if pred.support_minimal:
                m.support_minimal += 1
        elif correct:
            m.correct_answer_invalid_proof += 1

    return out


@dataclass
class ProofOrbitMetrics:
    n_orbits: int = 0
    proof_validity_orbit_accuracy: float = 0.0
    support_equivariance_mean: float | None = None
    n_support_pairs_compared: int = 0
    n_support_pairs_undefined: int = 0
    conditions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "n_orbits": self.n_orbits,
            "proof_validity_orbit_accuracy": self.proof_validity_orbit_accuracy,
            "support_equivariance_mean": self.support_equivariance_mean,
            "n_support_pairs_compared": self.n_support_pairs_compared,
            "n_support_pairs_undefined": self.n_support_pairs_undefined,
            "conditions": self.conditions,
        }


def orbit_level(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    reference: str = "C0",
) -> ProofOrbitMetrics:
    """PVOA (spec 22.4) and support equivariance (spec 22.5).

    Support equivariance is measured as the Jaccard overlap of the cited axiom **ids** in
    the reference and transformed conditions. Because orbit members are built by mapping
    one ordered context, id ``A7`` denotes corresponding axioms in every variant -- so
    comparing ids is exactly the inverse-mapping comparison the spec describes, without
    needing to invert the renaming.
    """
    by_id = {i.orbit_item_id: i for i in items}
    orbits: dict[str, dict[str, tuple[BenchmarkItem, Prediction]]] = defaultdict(dict)

    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is not None and item.task.positive:
            orbits[item.base_item_id][item.condition] = (item, pred)

    if not orbits:
        return ProofOrbitMetrics()

    conditions = sorted({c for slot in orbits.values() for c in slot})
    complete = {b: s for b, s in orbits.items() if len(s) == len(conditions)}
    if not complete:
        return ProofOrbitMetrics(conditions=conditions)

    good = 0
    jaccards: list[float] = []
    undefined = 0

    for slot in complete.values():
        all_good = True
        for _condition, (item, pred) in slot.items():
            if pred.label != item.task.label or not pred.support_valid:
                all_good = False
                break
        if all_good:
            good += 1

        if reference in slot:
            ref_support = set(slot[reference][1].support_axiom_ids)
            for condition, (_item, pred) in slot.items():
                if condition == reference:
                    continue
                other = set(pred.support_axiom_ids)
                union = ref_support | other
                if not union:
                    # Neither side cited anything. Scoring this 1.0 would credit a model
                    # that never produces a proof with perfect proof equivariance -- the
                    # metric is undefined here, and counting it as agreement is how a
                    # non-reasoning baseline ends up looking maximally equivariant.
                    undefined += 1
                    continue
                jaccards.append(len(ref_support & other) / len(union))

    return ProofOrbitMetrics(
        n_orbits=len(complete),
        proof_validity_orbit_accuracy=good / len(complete),
        support_equivariance_mean=(sum(jaccards) / len(jaccards)) if jaccards else None,
        n_support_pairs_compared=len(jaccards),
        n_support_pairs_undefined=undefined,
        conditions=conditions,
    )
