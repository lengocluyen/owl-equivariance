"""Tokenization controls and the regression layer."""

from __future__ import annotations

import pytest

from owl_equivariance import tokens
from owl_equivariance.schemas import (
    Axiom,
    BenchmarkItem,
    ContextInfo,
    LexiconEntry,
    OntologyInfo,
    TaskInfo,
    TransformInfo,
)


def item(base, condition, names, labels=None):
    """One item whose axioms mention `names`, optionally with a vocabulary block."""
    axioms = [
        Axiom(id=f"A{i+1}", text=f"SubClassOf(<urn:owleq:c#{n}> <urn:owleq:c#Root>)")
        for i, n in enumerate(names)
    ]
    lexicon = (
        [LexiconEntry(entity=n, label=labels[n]) for n in names if n in labels]
        if labels
        else []
    )
    return BenchmarkItem(
        base_item_id=base,
        orbit_item_id=f"{base}:{condition}",
        ontology=OntologyInfo(ontology_id="t"),
        task=TaskInfo(
            type="ATOMIC_SUBSUMPTION",
            query_functional=f"SubClassOf(<urn:owleq:c#{names[0]}> <urn:owleq:c#Root>)",
            label="ENTAILED",
            positive=True,
        ),
        transform=TransformInfo(operator="opaque", lexical_condition=condition),
        context=ContextInfo(axioms=axioms, lexicon=lexicon, label_preservation_certified=True),
    )


class TestCounters:
    def test_word_counter_cannot_see_inside_a_token(self):
        # The property that makes it unfit for the fragmentation control.
        c = tokens.Counter("words")
        assert not c.sees_subword
        assert c.count("C_000012 Root") == c.count("Tavrine Root")

    def test_character_counter_sees_inside_a_token(self):
        c = tokens.Counter("chars")
        assert c.sees_subword
        assert c.count("C_000012") != c.count("Tavrine")


class TestMatchChecks:
    def _report(self, spec):
        items = [
            item("b1", "C4", ["C_000012", "C_000044"]),
            item("b1", "C5", ["Tavrine", "Mondera"]),
            item("b1", "C0", ["Neuron", "Astrocyte"]),
        ]
        return tokens.analyse(
            items,
            counter=tokens.Counter(spec),
            match_pairs=[("C4", "C5")],
            tolerance=0.10,
        )

    def test_word_counter_refuses_to_assess_rather_than_claiming_a_match(self):
        # Reporting "matched" from a blind counter would certify a control that was never
        # actually checked -- worse than reporting nothing.
        [check] = self._report("words").match_checks
        assert check.assessable is False
        assert check.matched is None
        assert "NOT ASSESSABLE" in check.verdict()

    def test_subword_counter_produces_a_real_verdict(self):
        [check] = self._report("chars").match_checks
        assert check.assessable is True
        assert check.matched in (True, False)
        assert "NOT ASSESSABLE" not in check.verdict()

    def test_large_length_difference_is_flagged_as_not_matched(self):
        items = [
            item("b1", "C6", ["Kettle"]),
            item("b1", "C7", ["TransitionalMyocyteOfAtrioventricularBundle"]),
            item("b1", "C0", ["Neuron"]),
        ]
        report = tokens.analyse(
            items, counter=tokens.Counter("chars"), match_pairs=[("C6", "C7")], tolerance=0.10
        )
        [check] = report.match_checks
        assert check.assessable and check.matched is False
        assert "confounded" in check.verdict()


class TestLengthWarnings:
    def test_length_difference_against_the_reference_is_reported(self):
        # Removing the vocabulary block shortens the prompt a lot; that is inherent to the
        # manipulation, but it confounds the contrast and must be surfaced.
        items = [
            item("b1", "C0", ["Neuron"], labels={"Neuron": "a neuron is a cell that " * 20}),
            item("b1", "C4", ["C_000012"]),
        ]
        report = tokens.analyse(items, counter=tokens.Counter("chars"))
        assert any("C4 prompts are" in w for w in report.length_warnings)

    def test_no_warning_when_lengths_are_comparable(self):
        items = [item("b1", "C0", ["Neuron"]), item("b1", "C4", ["Tavrix"])]
        report = tokens.analyse(items, counter=tokens.Counter("chars"))
        assert report.length_warnings == []


class TestModeling:
    def test_pooled_condition_model_interaction_uses_source_columns(self, tmp_path):
        pytest.importorskip("statsmodels")
        pytest.importorskip("pandas")
        from owl_equivariance import modeling

        csv = tmp_path / "pooled-analysis.csv"
        rows = [
            "base_item_id,ontology_id,model,condition,correct,proof_depth,"
            "context_axioms,token_delta"
        ]
        for b in range(60):
            ontology = "cl" if b < 30 else "po"
            for model_index, model in enumerate(("m1", "m2")):
                for condition_index, condition in enumerate(("C0", "C4")):
                    correct = int((b + model_index + 2 * condition_index) % 5 != 0)
                    token_delta = b % 3 - 50 * condition_index
                    rows.append(
                        f"{ontology}-b{b},{ontology},{model},{condition},{correct},"
                        f"{1 + b % 4},{20 + b % 5},{token_delta}"
                    )
        csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

        result = modeling.fit(
            str(csv),
            estimator="gee",
            condition_model_interaction=True,
        )

        assert result.n_observations == 240
        assert result.n_groups == 60
        assert "condition:C(model)" in result.terms
        assert "condition:C(model)" in result.formula
        assert any(":C(model)" in row["term"] for row in result.coefficients)
        assert any("condition-by-model interaction included" in note for note in result.notes)

    def test_constant_validity_outcome_is_reported_as_non_estimable(self, tmp_path):
        pytest.importorskip("statsmodels")
        from owl_equivariance import modeling

        csv = tmp_path / "constant-validity.csv"
        rows = ["base_item_id,ontology_id,model,condition,parsed"]
        for b in range(10):
            for condition in ("C0", "C4"):
                rows.append(f"b{b},cl,m1,{condition},1")
        csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

        result = modeling.fit(str(csv), estimator="gee", outcome="parsed")

        assert result.fit_status == "CONSTANT_OUTCOME"
        assert result.coefficients == []
        assert any("outcome 'parsed' is constant" in note for note in result.notes)

    def test_fit_reports_clusters_and_drops_degenerate_covariates(self, tmp_path):
        pytest.importorskip("statsmodels")
        pytest.importorskip("pandas")
        from owl_equivariance import modeling

        csv = tmp_path / "analysis.csv"
        rows = ["base_item_id,ontology_id,model,condition,correct,proof_depth,"
                "context_axioms,token_delta"]
        for b in range(40):
            for condition, correct in (("C0", 1), ("C4", int(b % 3 == 0))):
                rows.append(
                    f"b{b},cl,m1,{condition},{correct},{1 + b % 4},{20 + b % 5},"
                    f"{0 if condition == 'C0' else -100}"
                )
        csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

        result = modeling.fit(str(csv), estimator="gee")
        assert result.n_groups == 40
        assert result.n_observations == 80
        assert any(c["term"].startswith("condition") for c in result.coefficients)
        condition = next(c for c in result.coefficients if c["term"].startswith("condition"))
        assert condition["p_value_holm"] is not None
        assert condition["p_value_holm"] >= condition["p_value"]
        # One ontology: no ontology term, and the note says why.
        assert "C(ontology_id)" not in result.terms
        assert any("one ontology" in n for n in result.notes)

    def test_constant_covariates_are_dropped_with_a_note(self, tmp_path):
        pytest.importorskip("statsmodels")
        from owl_equivariance import modeling

        csv = tmp_path / "analysis.csv"
        rows = ["base_item_id,ontology_id,model,condition,correct,proof_depth,"
                "context_axioms,token_delta"]
        for b in range(30):
            for condition, correct in (("C0", 1), ("C4", b % 2)):
                # context_axioms is constant here and cannot be estimated.
                rows.append(f"b{b},cl,m1,{condition},{correct},{1 + b % 3},20,"
                            f"{0 if condition == 'C0' else -50}")
        csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

        result = modeling.fit(str(csv), estimator="gee")
        assert "context_axioms" not in result.terms
        assert any("constant" in n for n in result.notes)
