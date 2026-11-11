"""Metric definitions, checked against hand-computed values."""

from __future__ import annotations

import pytest

from owl_equivariance import power
from owl_equivariance.metrics import answer, orbit, proof, stats
from owl_equivariance.schemas import (
    Axiom,
    BenchmarkItem,
    ContextInfo,
    OntologyInfo,
    Prediction,
    ReferenceInfo,
    TaskInfo,
    TransformInfo,
)


def item(base: str, condition: str, label: str = "ENTAILED", positive: bool = True):
    return BenchmarkItem(
        base_item_id=base,
        orbit_item_id=f"{base}:{condition}",
        ontology=OntologyInfo(ontology_id="toy"),
        task=TaskInfo(
            type="ATOMIC_SUBSUMPTION",
            query_functional="SubClassOf(<x#A> <x#B>)",
            label=label,
            positive=positive,
        ),
        transform=TransformInfo(operator="opaque", lexical_condition=condition),
        context=ContextInfo(axioms=[Axiom(id="A1", text="a"), Axiom(id="A2", text="b")]),
        reference=ReferenceInfo(support_axiom_sets=[["A1", "A2"]]),
    )


def pred(base: str, condition: str, label, **kw):
    return Prediction(
        orbit_item_id=f"{base}:{condition}",
        base_item_id=base,
        condition=condition,
        model="m",
        prompt_style="structured_proof",
        label=label,
        **kw,
    )


class TestAnswerMetrics:
    def test_accuracy_and_invalid_rate(self):
        items = [item("b1", "C0"), item("b2", "C0", label="NOT_ENTAILED", positive=False)]
        preds = [pred("b1", "C0", "ENTAILED"), pred("b2", "C0", None)]

        m = answer.per_condition(items, preds)["C0"]
        assert m.n == 2
        assert m.accuracy == 0.5
        assert m.invalid_rate == 0.5
        assert m.valid_only_accuracy == 1.0

    def test_unparseable_counts_as_wrong_in_the_right_cell(self):
        # A missing answer on a positive is a false negative, not a free pass.
        items = [item("b1", "C0")]
        m = answer.per_condition(items, [pred("b1", "C0", None)])["C0"]
        assert m.fn == 1 and m.tp == 0

    def test_flip_rates_and_pair_consistency(self):
        items = []
        preds = []
        # b1: right then wrong (a correct-to-wrong flip)
        # b2: wrong then right (a wrong-to-correct flip)
        # b3: right in both
        for base, c0, c4 in [
            ("b1", "ENTAILED", "NOT_ENTAILED"),
            ("b2", "NOT_ENTAILED", "ENTAILED"),
            ("b3", "ENTAILED", "ENTAILED"),
        ]:
            for condition, label in (("C0", c0), ("C4", c4)):
                items.append(item(base, condition))
                preds.append(pred(base, condition, label))

        [cmp] = answer.compare_to_reference(items, preds, reference="C0", n_resamples=200)
        assert cmp.n_pairs == 3
        assert cmp.correct_to_wrong == pytest.approx(0.5)   # 1 of 2 correct in C0
        assert cmp.wrong_to_correct == pytest.approx(1.0)   # 1 of 1 wrong in C0
        assert cmp.pair_consistency == pytest.approx(1 / 3)
        assert cmp.invariance_gap == pytest.approx(0.0)     # 2/3 both ways
        assert cmp.discordant_odds_ratio == pytest.approx(1.0)
        assert "discordant_odds_ratio_ref_over_condition" in cmp.as_dict()

    def test_multiplicity_correction_is_applied_to_the_comparison_family(self):
        # Every condition is tested against the same reference, so the raw p-values are a
        # family. An uncorrected p reported beside eight comparisons overstates the result.
        items, preds = [], []
        conditions = ["C0", "C1", "C2", "C4", "C4S2", "C5", "C6", "C7", "C8"]
        for base in range(20):
            for condition in conditions:
                items.append(item(f"b{base}", condition))
                wrong = condition != "C0" and base < 6
                preds.append(
                    pred(f"b{base}", condition, "NOT_ENTAILED" if wrong else "ENTAILED")
                )

        comparisons = answer.compare_to_reference(items, preds, reference="C0", n_resamples=200)
        assert len(comparisons) == 8
        for c in comparisons:
            assert c.p_value_holm is not None
            assert c.p_value_holm >= c.p_value  # correction can only be conservative
            assert c.p_value_holm <= 1.0
        assert "mcnemar_p_holm" in comparisons[0].as_dict()

    def test_response_validity_has_its_own_paired_comparison(self):
        items, preds = [], []
        for base in range(10):
            for condition in ("C0", "C4"):
                items.append(item(f"b{base}", condition))
                label = None if condition == "C4" and base < 6 else "ENTAILED"
                preds.append(pred(f"b{base}", condition, label))

        [comparison] = answer.compare_validity_to_reference(
            items,
            preds,
            reference="C0",
            n_resamples=200,
        )
        assert comparison.validity_gap == pytest.approx(0.6)
        assert comparison.valid_to_invalid == 6
        assert comparison.invalid_to_valid == 0
        assert comparison.p_value_holm is not None

    def test_seed_disagreement_detects_self_contradiction(self):
        items, preds = [], []
        for base, a, b in [("b1", "ENTAILED", "NOT_ENTAILED"), ("b2", "ENTAILED", "ENTAILED")]:
            for condition, label in (("C4", a), ("C4S2", b)):
                items.append(item(base, condition))
                preds.append(pred(base, condition, label))

        result = answer.seed_disagreement(items, preds, "C4", "C4S2")
        assert result.n_pairs == 2
        assert result.disagreement_rate == pytest.approx(0.5)
        assert result.exactly_one_correct == 1


class TestPowerSimulation:
    def test_paired_power_uses_observed_discordance_and_is_reproducible(self):
        items, preds = [], []
        # Pilot discordance is 20%: 15 reference-only correct and 5 condition-only.
        for base in range(100):
            c0 = "NOT_ENTAILED" if 15 <= base < 20 else "ENTAILED"
            c4 = "NOT_ENTAILED" if base < 15 else "ENTAILED"
            for condition, label in (("C0", c0), ("C4", c4)):
                items.append(item(f"b{base}", condition))
                preds.append(pred(f"b{base}", condition, label))

        first = power.analyze(
            items,
            preds,
            planned_pairs=1200,
            target_gap=0.05,
            family_size=10,
            simulations=500,
            seed=7,
        )
        second = power.analyze(
            items,
            preds,
            planned_pairs=1200,
            target_gap=0.05,
            family_size=10,
            simulations=500,
            seed=7,
        )
        assert first.rows == second.rows
        assert first.rows[0]["pilot_discordance_rate"] == pytest.approx(0.20)
        assert 0 <= first.rows[0]["estimated_power"] <= 1


class TestOrbitMetrics:
    def test_robust_orbit_accuracy_requires_every_member(self):
        items, preds = [], []
        for base, labels in [
            ("b1", {"C0": "ENTAILED", "C4": "ENTAILED", "C7": "ENTAILED"}),
            ("b2", {"C0": "ENTAILED", "C4": "ENTAILED", "C7": "NOT_ENTAILED"}),
        ]:
            for condition, label in labels.items():
                items.append(item(base, condition))
                preds.append(pred(base, condition, label))

        m = orbit.compute(items, preds, reference="C0")
        assert m.n_orbits == 2
        # b2 fails one variant, so only b1 is robust -- even though per-condition
        # accuracy is 100%, 100% and 50%.
        assert m.robust_orbit_accuracy == pytest.approx(0.5)
        assert m.orbit_consistency == pytest.approx(0.5)
        assert m.worst_condition == "C7"

    def test_perfect_orbit_reports_a_real_worst_condition_at_full_accuracy(self):
        items = [item("b1", c) for c in ("C0", "C4")]
        preds = [pred("b1", c, "ENTAILED") for c in ("C0", "C4")]
        m = orbit.compute(items, preds)
        assert m.worst_condition == "C0"
        assert m.worst_condition_accuracy == pytest.approx(1.0)

    def test_incomplete_orbits_are_excluded(self):
        items = [item("b1", "C0"), item("b1", "C4"), item("b2", "C0")]
        preds = [
            pred("b1", "C0", "ENTAILED"),
            pred("b1", "C4", "ENTAILED"),
            pred("b2", "C0", "ENTAILED"),
        ]
        # b2 has no C4 member; counting it would inflate robustness.
        assert orbit.compute(items, preds).n_orbits == 1


class TestProofMetrics:
    def test_caip_joint_and_conditional_are_both_reported(self):
        items = [item("b1", "C0"), item("b2", "C0"), item("b3", "C0")]
        preds = [
            pred("b1", "C0", "ENTAILED", support_valid=True, support_minimal=True),
            pred("b2", "C0", "ENTAILED", support_valid=False),   # right answer, bad proof
            pred("b3", "C0", "NOT_ENTAILED", support_valid=False),  # wrong answer
        ]
        m = proof.per_condition(items, preds)["C0"]
        assert m.n_positive == 3
        assert m.answer_correct == 2
        assert m.correct_answer_invalid_proof == 1
        # Spec section 22.7 defines the joint probability over validated items...
        assert m.caip_joint == pytest.approx(1 / 3)
        # ...the conditional form answers a different question and must not be conflated.
        assert m.caip_given_correct == pytest.approx(0.5)

    def test_joint_and_conditional_caip_move_in_opposite_directions(self):
        # A model that answers almost nothing correctly has a LOW joint CAIP purely by
        # getting little right, while its conditional CAIP is 1.0. Reporting either alone
        # invites the wrong reading, which is why both are exported.
        items = [item(f"b{i}", "C0") for i in range(10)]
        preds = [
            pred("b0", "C0", "ENTAILED", support_valid=False),
            *[pred(f"b{i}", "C0", "NOT_ENTAILED", support_valid=False) for i in range(1, 10)],
        ]
        m = proof.per_condition(items, preds)["C0"]
        assert m.caip_joint == pytest.approx(0.1)
        assert m.caip_given_correct == pytest.approx(1.0)

    def test_negatives_are_excluded_from_proof_metrics(self):
        items = [item("b1", "C0", label="NOT_ENTAILED", positive=False)]
        preds = [pred("b1", "C0", "NOT_ENTAILED", support_valid=False)]
        assert proof.per_condition(items, preds) == {}

    def test_support_equivariance_uses_shared_axiom_ids(self):
        items, preds = [], []
        for condition, support in (("C0", ["A1", "A2"]), ("C4", ["A1"])):
            items.append(item("b1", condition))
            preds.append(
                pred("b1", condition, "ENTAILED", support_axiom_ids=support, support_valid=True)
            )
        m = proof.orbit_level(items, preds, reference="C0")
        assert m.support_equivariance_mean == pytest.approx(0.5)  # |{A1}| / |{A1,A2}|
        assert m.n_support_pairs_compared == 1
        assert m.proof_validity_orbit_accuracy == pytest.approx(1.0)

    def test_support_equivariance_is_undefined_when_neither_side_cites_anything(self):
        # Scoring two empty sets as Jaccard 1.0 would hand a model that never produces a
        # proof a perfect proof-equivariance score.
        items, preds = [], []
        for condition in ("C0", "C4"):
            items.append(item("b1", condition))
            preds.append(pred("b1", condition, "ENTAILED", support_axiom_ids=[]))
        m = proof.orbit_level(items, preds, reference="C0")
        assert m.support_equivariance_mean is None
        assert m.n_support_pairs_compared == 0
        assert m.n_support_pairs_undefined == 1


class TestStats:
    def test_mcnemar_matches_hand_computation(self):
        # 5 discordant pairs, all in one direction: p = 2 * (1/2)^5 = 0.0625
        a = [True] * 5 + [True] * 3
        b = [False] * 5 + [True] * 3
        t = stats.mcnemar_exact(a, b)
        assert t.b == 5 and t.c == 0
        assert t.p_value == pytest.approx(0.0625)
        assert t.odds_ratio is None

    def test_mcnemar_with_no_discordant_pairs(self):
        t = stats.mcnemar_exact([True, False], [True, False])
        assert t.p_value == 1.0

    def test_bootstrap_ci_brackets_the_point_estimate(self):
        a = [True] * 80 + [False] * 20
        b = [True] * 50 + [False] * 50
        point, lo, hi = stats.paired_bootstrap_ci(a, b, n_resamples=2000, seed=1)
        assert point == pytest.approx(0.30)
        assert lo < point < hi

    def test_wilson_interval_stays_in_range_at_the_extremes(self):
        lo, hi = stats.wilson_interval(10, 10)
        assert 0.0 <= lo <= 1.0 and hi == pytest.approx(1.0, abs=1e-9)
        lo, hi = stats.wilson_interval(0, 10)
        assert lo == pytest.approx(0.0, abs=1e-9) and hi <= 1.0

    def test_holm_is_monotone_and_bounded(self):
        adj = stats.holm_correction({"a": 0.01, "b": 0.02, "c": 0.5})
        assert adj["a"] <= adj["b"] <= adj["c"] <= 1.0
        assert adj["a"] == pytest.approx(0.03)
