"""Strict-parser behaviour (spec section 19)."""

from __future__ import annotations

import pytest

from owl_equivariance.parsing import ParseErrorKind, parse
from owl_equivariance.schemas import (
    Axiom,
    BenchmarkItem,
    ContextInfo,
    OntologyInfo,
    TaskInfo,
    TransformInfo,
)


def make_item(axiom_ids=("A1", "A2", "A3")) -> BenchmarkItem:
    return BenchmarkItem(
        base_item_id="b:1",
        orbit_item_id="b:1:C0",
        ontology=OntologyInfo(ontology_id="toy"),
        task=TaskInfo(
            type="ATOMIC_SUBSUMPTION",
            query_functional="SubClassOf(<x#A> <x#B>)",
            label="ENTAILED",
            positive=True,
        ),
        transform=TransformInfo(operator="none", lexical_condition="C0"),
        context=ContextInfo(axioms=[Axiom(id=i, text=f"ax {i}") for i in axiom_ids]),
    )


def test_clean_json():
    r = parse('{"label": "ENTAILED", "support_axiom_ids": ["A1", "A3"]}', make_item())
    assert r.ok
    assert r.label == "ENTAILED"
    assert r.support_axiom_ids == ["A1", "A3"]
    assert r.repairs == []


def test_code_fence_is_repaired_and_recorded():
    raw = '```json\n{"label": "NOT_ENTAILED", "support_axiom_ids": []}\n```'
    r = parse(raw, make_item())
    assert r.label == "NOT_ENTAILED"
    assert "stripped_code_fence" in r.repairs


def test_prose_wrapped_object_is_extracted():
    raw = 'Looking at the axioms, I conclude:\n{"label": "ENTAILED", "support_axiom_ids": ["A2"]}\nDone.'
    r = parse(raw, make_item())
    assert r.label == "ENTAILED"
    assert "extracted_embedded_object" in r.repairs


def test_repair_can_be_disabled_for_the_no_repair_report():
    raw = '```json\n{"label": "ENTAILED"}\n```'
    assert parse(raw, make_item(), allow_repair=False).ok is False
    assert parse(raw, make_item(), allow_repair=True).ok is True


def test_unknown_axiom_ids_are_reported_not_dropped():
    r = parse('{"label": "ENTAILED", "support_axiom_ids": ["A1", "A99", "Z"]}', make_item())
    assert r.support_axiom_ids == ["A1"]
    assert r.unknown_support_ids == ["A99", "Z"]


def test_duplicate_support_ids_collapse():
    r = parse('{"label": "ENTAILED", "support_axiom_ids": ["A1", "A1", "A2"]}', make_item())
    assert r.support_axiom_ids == ["A1", "A2"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ParseErrorKind.EMPTY),
        ("I cannot answer that.", ParseErrorKind.NO_JSON),
        ('{"label": ', ParseErrorKind.MALFORMED_JSON),
        ('{"support_axiom_ids": []}', ParseErrorKind.MISSING_LABEL),
        ('{"label": "MAYBE"}', ParseErrorKind.INVALID_LABEL),
        ('["ENTAILED"]', ParseErrorKind.NOT_AN_OBJECT),
    ],
)
def test_error_categories(raw, expected):
    r = parse(raw, make_item())
    assert not r.ok
    assert r.error == expected


def test_label_case_and_spacing_normalised():
    r = parse('{"label": "not entailed"}', make_item())
    assert r.label == "NOT_ENTAILED"
    assert "normalized_label" in r.repairs
