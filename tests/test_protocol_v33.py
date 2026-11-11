import hashlib
from pathlib import Path

import yaml

from owl_equivariance import budgeting, modeling, protocol


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "configs" / "open_weight_experiment_v33.yaml"
CONDITIONS = ("C0", "C1", "C2", "C3", "C4", "C4S2", "C5", "C6", "C7", "C8", "C9")


def source(name: str, base_items: int) -> protocol.SourceSummary:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return protocol.SourceSummary(
        path=f"data/certified_v33/{name}/benchmark.jsonl",
        dataset_sha256="0" * 64,
        ontology_id=name,
        ontology_version="frozen",
        ontology_source_hash=digest,
        base_items=base_items,
        rows=base_items * len(CONDITIONS),
        conditions=CONDITIONS,
        task_counts={"ATOMIC_SUBSUMPTION": base_items},
        label_counts={"ENTAILED": base_items // 2, "NOT_ENTAILED": base_items // 2},
        certifier_version="0.2.0",
        candidate_sampling="SEEDED_SHA256_BOTTOM_K",
        justification_algorithm="QUICKXPLAIN",
        justification_call_budget_per_candidate=256,
        build_checkpoint_sha256="1" * 64,
        build_checkpoint_status="COMPLETE",
    )


def test_v33_manifest_is_a_prospective_capacity_amendment():
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    criteria = protocol.PanelCriteria.from_manifest(manifest)

    assert manifest["protocol_id"] == "owleq-jws-2026-08-v33"
    assert "outcomes unseen" in manifest["status"]
    assert criteria.minimum_sources == 8
    assert criteria.minimum_base_items_per_source == 150
    assert criteria.minimum_total_base_items == 1320
    assert criteria.panel_file_required
    assert criteria.required_certifier_version == "0.2.0"
    assert criteria.required_candidate_sampling == "SEEDED_SHA256_BOTTOM_K"
    assert criteria.required_justification_algorithm == "QUICKXPLAIN"
    assert criteria.required_justification_call_budget == 256
    assert criteria.build_checkpoint_required
    assert manifest["analysis"]["primary"]["random_intercepts"] == [
        "ontology_id",
        "ontology_id:base_item_id",
    ]
    assert manifest["analysis"]["power"]["posthoc_confirmatory_power_forbidden"]


def test_v33_known_sources_plus_five_minimum_sources_pass_capacity():
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    criteria = protocol.PanelCriteria.from_manifest(manifest)
    summaries = [source("go", 162), source("envo", 164), source("schemaorg", 300)]
    summaries.extend(source(f"new{index}", 150) for index in range(1, 6))

    assert sum(item.base_items for item in summaries) == 1376
    assert protocol.validate_summaries(criteria, summaries) == []


def test_v33_rejects_too_few_sources_and_a_149_item_source():
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    criteria = protocol.PanelCriteria.from_manifest(manifest)
    summaries = [source(f"o{index}", 160) for index in range(7)]
    summaries.append(source("under", 149))

    problems = protocol.validate_summaries(criteria, summaries)
    assert any("under" in problem and "at least 150" in problem for problem in problems)
    assert any("at least 1320" in problem for problem in problems)

    problems = protocol.validate_summaries(criteria, summaries[:7])
    assert any("at least 8 sources" in problem for problem in problems)


def test_v33_rejects_pre_amendment_or_incomplete_generator_artifacts():
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    criteria = protocol.PanelCriteria.from_manifest(manifest)
    current = source("current", 160)
    old = protocol.SourceSummary(
        **{
            **current.__dict__,
            "certifier_version": "0.1.0",
            "candidate_sampling": None,
            "justification_algorithm": None,
            "justification_call_budget_per_candidate": None,
            "build_checkpoint_sha256": None,
            "build_checkpoint_status": None,
        }
    )

    problems = protocol.validate_summaries(criteria, [old])
    assert any("certifier_version" in problem for problem in problems)
    assert any("candidate_sampling" in problem for problem in problems)
    assert any("build_checkpoint.json is missing" in problem for problem in problems)


def test_v33_budget_uses_1320_base_items_and_three_responses_on_subset():
    report = budgeting.estimate(MANIFEST, "confirmatory", ceiling=False)
    # Per model: 1,320 * 11 primary calls plus two additional calls for a 20% subset.
    assert report.total_calls == (1320 * 11 + 2 * round(1320 * 11 * 0.20)) * 6
    assert report.total_cost_usd == 0


def test_ontology_random_effect_requires_mixed_estimator_and_five_levels():
    assert modeling._resolve_ontology_effect("bayes_mixed", "auto", 8) == "random"
    assert modeling._resolve_ontology_effect("gee", "auto", 8) == "fixed"

    try:
        modeling._resolve_ontology_effect("gee", "random", 8)
    except ValueError as exc:
        assert "bayes_mixed" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("GEE incorrectly accepted an ontology random effect")

    try:
        modeling._resolve_ontology_effect("bayes_mixed", "random", 4)
    except ValueError as exc:
        assert "at least five" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("underidentified ontology random effect was accepted")


def test_primary_r_script_contains_both_preregistered_random_intercepts():
    text = (ROOT / "scripts" / "analyze_confirmatory_v33.R").read_text(encoding="utf-8")
    assert "+ (1 | ontology_id) + (1 | item_cluster)" in text
    assert "post-hoc power calculation=forbidden" in text
