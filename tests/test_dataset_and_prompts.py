"""Dataset integrity checks and prompt construction."""

from __future__ import annotations

from owl_equivariance import prompting
from owl_equivariance.dataset import by_orbit, check_leakage, check_orbit_consistency
from owl_equivariance.runners import build_runner
from owl_equivariance.runners.baselines import LexicalRunner
from owl_equivariance.schemas import (
    Axiom,
    BenchmarkItem,
    ContextInfo,
    OntologyInfo,
    ReferenceInfo,
    TaskInfo,
    TransformInfo,
)


def item(base, condition, split="test", n_axioms=2, label="ENTAILED", query=None):
    return BenchmarkItem(
        base_item_id=base,
        orbit_item_id=f"{base}:{condition}",
        ontology=OntologyInfo(ontology_id="toy"),
        task=TaskInfo(
            type="ATOMIC_SUBSUMPTION",
            query_functional=query or "SubClassOf(<http://x#Neuron> <http://x#Cell>)",
            label=label,
            positive=label == "ENTAILED",
        ),
        transform=TransformInfo(operator="opaque", lexical_condition=condition),
        context=ContextInfo(
            axioms=[Axiom(id=f"A{i+1}", text=f"SubClassOf(<http://x#C{i}> <http://x#D{i}>)")
                    for i in range(n_axioms)],
            label_preservation_certified=True,
        ),
        reference=ReferenceInfo(support_axiom_sets=[["A1"]]),
        split=split,
    )


class TestDatasetChecks:
    def test_orbit_grouping(self):
        items = [item("b1", "C0"), item("b1", "C4"), item("b2", "C0")]
        orbits = by_orbit(items)
        assert set(orbits) == {"b1", "b2"}
        assert len(orbits["b1"]) == 2

    def test_split_leakage_is_detected(self):
        items = [item("b1", "C0", split="train"), item("b1", "C4", split="test")]
        problems = check_leakage(items)
        assert len(problems) == 1 and "spans splits" in problems[0]

    def test_clean_orbit_has_no_leakage(self):
        assert check_leakage([item("b1", "C0"), item("b1", "C4")]) == []

    def test_label_drift_within_an_orbit_is_detected(self):
        items = [item("b1", "C0", label="ENTAILED"), item("b1", "C4", label="NOT_ENTAILED")]
        assert any("disagree on the label" in p for p in check_orbit_consistency(items))

    def test_context_size_drift_within_an_orbit_is_detected(self):
        items = [item("b1", "C0", n_axioms=2), item("b1", "C4", n_axioms=3)]
        assert any("differ in context size" in p for p in check_orbit_consistency(items))


class TestExperimentalAdequacyGates:
    """Checks that ask whether items *measure* something, not just whether labels are right.

    A dataset can pass every logical check and still be worthless -- an item with no axioms
    is correctly labelled NOT_ENTAILED and answerable without reading anything.
    """

    def test_empty_contexts_are_rejected(self):
        from owl_equivariance.dataset import check_non_empty_contexts

        items = [item("b1", "C0", n_axioms=0), item("b2", "C0", n_axioms=5)]
        problems = check_non_empty_contexts(items)
        assert problems and "empty context" in problems[0]

    def test_non_empty_contexts_pass(self):
        from owl_equivariance.dataset import check_non_empty_contexts

        assert check_non_empty_contexts([item("b1", "C0", n_axioms=3)]) == []

    def test_size_imbalance_between_labels_is_rejected(self):
        # If negatives are systematically shorter, length alone predicts the label.
        from owl_equivariance.dataset import check_context_size_balance

        items = [item(f"p{i}", "C0", n_axioms=20) for i in range(5)]
        items += [item(f"n{i}", "C0", n_axioms=2, label="NOT_ENTAILED") for i in range(5)]
        problems = check_context_size_balance(items)
        assert problems and "context size differs by label" in problems[0]

    def test_matched_sizes_pass(self):
        from owl_equivariance.dataset import check_context_size_balance

        items = [item(f"p{i}", "C0", n_axioms=20) for i in range(5)]
        items += [item(f"n{i}", "C0", n_axioms=19, label="NOT_ENTAILED") for i in range(5)]
        assert check_context_size_balance(items) == []

    def test_condition_id_in_iris_is_detected(self):
        from owl_equivariance.dataset import check_condition_leakage

        leaky = item("b1", "C7")
        leaky.context.axioms[0].text = "SubClassOf(<urn:owleq:c7:42:c#A> <urn:owleq:c7:42:c#B>)"
        problems = check_condition_leakage([leaky])
        assert problems and "condition id appears" in problems[0]

    def test_neutral_namespace_passes(self):
        from owl_equivariance.dataset import check_condition_leakage

        clean = item("b1", "C7")
        clean.context.axioms[0].text = "SubClassOf(<urn:owleq:c#A> <urn:owleq:c#B>)"
        assert check_condition_leakage([clean]) == []

    @staticmethod
    def _seeded(condition, seed, policy, query, bases=("b1", "b2")):
        out = []
        for base in bases:
            it = item(base, condition, query=query)
            it.transform.seed = seed
            it.transform.annotation_policy = policy
            out.append(it)
        return out

    def test_identical_seed_mappings_are_detected(self):
        # C4 and C4S2 must differ; if they do not, the self-consistency contrast compares a
        # run against itself.
        from owl_equivariance.dataset import check_distinct_seed_mappings

        same = "SubClassOf(<urn:owleq:c#C_1> <urn:owleq:c#C_2>)"
        items = self._seeded("C4", 42, "REMOVE_ALL_LEXICAL", same)
        items += self._seeded("C4S2", 43, "REMOVE_ALL_LEXICAL", same)
        problems = check_distinct_seed_mappings(items)
        assert problems and "identical renamings" in problems[0]

    def test_distinct_seed_mappings_pass(self):
        from owl_equivariance.dataset import check_distinct_seed_mappings

        items = self._seeded(
            "C4", 42, "REMOVE_ALL_LEXICAL", "SubClassOf(<urn:owleq:c#C_1> <urn:owleq:c#C_2>)"
        )
        items += self._seeded(
            "C4S2", 43, "REMOVE_ALL_LEXICAL", "SubClassOf(<urn:owleq:c#C_9> <urn:owleq:c#C_4>)"
        )
        assert check_distinct_seed_mappings(items) == []

    def test_same_seed_different_annotation_policy_is_not_flagged(self):
        # C1 and C4 share operator and seed on purpose: holding the vocabulary fixed while
        # varying annotations is exactly what isolates the label channel. Identical
        # renamings there are the design, not a defect.
        from owl_equivariance.dataset import check_distinct_seed_mappings

        same = "SubClassOf(<urn:owleq:c#C_1> <urn:owleq:c#C_2>)"
        items = self._seeded("C1", 42, "KEEP_ALL", same)
        items += self._seeded("C4", 42, "REMOVE_ALL_LEXICAL", same)
        assert check_distinct_seed_mappings(items) == []

    def test_incomplete_orbits_are_reported_against_expected_conditions(self):
        from owl_equivariance.dataset import validate_dataset

        items = [item("b1", "C0"), item("b1", "C4")]
        problems = validate_dataset(items, expected_conditions=["C0", "C4", "C7"])
        assert any("C7" in p for p in problems)


class TestPrompting:
    def test_axiom_ids_appear_and_are_citable(self):
        p = prompting.build(item("b1", "C0", n_axioms=3), "structured_proof")
        for aid in ("[A1]", "[A2]", "[A3]"):
            assert aid in p.user
        assert p.wants_support

    def test_direct_style_does_not_ask_for_support(self):
        p = prompting.build(item("b1", "C0"), "direct")
        assert not p.wants_support
        assert "support_axiom_ids" not in p.schema["properties"]

    def test_system_prompt_is_identical_across_conditions(self):
        # The shared prefix is both the caching key and an experimental control.
        a = prompting.build(item("b1", "C0"), "structured_proof").system
        b = prompting.build(item("b1", "C7"), "structured_proof").system
        assert a == b

    def test_short_style_strips_iris_to_local_names(self):
        p = prompting.build(item("b1", "C0"), "structured_proof_short")
        assert "http://x#" not in p.user
        assert "Neuron" in p.user

    def test_ignore_names_style_differs_only_by_the_added_instruction(self):
        base = prompting.build(item("b1", "C0"), "direct").system
        ablation = prompting.build(item("b1", "C0"), "direct_ignore_names").system
        assert ablation.startswith(base)
        assert "Ignore the names entirely" in ablation


class TestBaselines:
    def test_oracle_is_always_right(self):
        from owl_equivariance.parsing import parse

        for label in ("ENTAILED", "NOT_ENTAILED"):
            it = item("b1", "C0", label=label)
            p = prompting.build(it, "structured_proof")
            parsed = parse(build_runner("oracle").run(it, p).raw_output, it)
            assert parsed.label == label

    def test_lexical_baseline_never_cites_support(self):
        # It has not looked at an axiom; claiming support would corrupt proof metrics.
        it = item("b1", "C0")
        p = prompting.build(it, "structured_proof")
        from owl_equivariance.parsing import parse

        parsed = parse(LexicalRunner().run(it, p).raw_output, it)
        assert parsed.support_axiom_ids == []

    def test_lexical_baseline_fires_on_containment_and_not_on_unrelated_names(self):
        from owl_equivariance.parsing import parse

        related = item(
            "b1", "C0", query="SubClassOf(<http://x#GlialCell> <http://x#Cell>)"
        )
        unrelated = item(
            "b2", "C0", query="SubClassOf(<http://x#C_000012> <http://x#C_000734>)"
        )
        runner = LexicalRunner()
        p1 = prompting.build(related, "direct")
        p2 = prompting.build(unrelated, "direct")

        assert parse(runner.run(related, p1).raw_output, related).label == "ENTAILED"
        assert parse(runner.run(unrelated, p2).raw_output, unrelated).label == "NOT_ENTAILED"

    def test_unknown_runner_spec_is_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="unknown runner"):
            build_runner("gpt-9")
