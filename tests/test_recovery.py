from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from owl_equivariance.dataset import write_jsonl
from owl_equivariance.recovery import (
    FrozenModel,
    FrozenRun,
    RecoveryError,
    dataset_slug,
    finalize_recovered_run,
    generate_missing_derived_outputs,
    load_frozen_run,
    primary_validated_paths,
    rebuild_or_verify_analysis,
    verify_checksums,
    verify_prediction_artifacts,
)
from owl_equivariance.schemas import (
    Axiom,
    BenchmarkItem,
    ContextInfo,
    OntologyInfo,
    Prediction,
    TaskInfo,
    TransformInfo,
)


def _item(base: str, condition: str) -> BenchmarkItem:
    return BenchmarkItem(
        base_item_id=base,
        orbit_item_id=f"{base}:{condition}",
        ontology=OntologyInfo(ontology_id="toy"),
        task=TaskInfo(
            type="ATOMIC_SUBSUMPTION",
            query_functional="SubClassOf(<x#A> <x#B>)",
            label="ENTAILED",
            positive=True,
        ),
        transform=TransformInfo(operator="identity", lexical_condition=condition),
        context=ContextInfo(axioms=[Axiom(id="A1", text="SubClassOf(<x#A> <x#B>)")]),
    )


def _prediction(item: BenchmarkItem, model: str, repeat: int, validated: bool) -> Prediction:
    return Prediction(
        orbit_item_id=item.orbit_item_id,
        base_item_id=item.base_item_id,
        condition=item.condition,
        model=model,
        prompt_style="structured_proof",
        label="ENTAILED",
        support_axiom_ids=["A1"],
        raw_output='{"label":"ENTAILED","support_axiom_ids":["A1"]}',
        response_payload=(
            {"choices": []} if model not in {"oracle", "majority", "lexical"} else None
        ),
        repeat=repeat,
        answer_correct=True if validated else None,
        support_valid=True if validated else None,
        support_minimal=True if validated else None,
    )


def _write_pair(
    root: Path,
    stem: str,
    items: list[BenchmarkItem],
    model: str,
    repeats: tuple[int, ...],
) -> None:
    raw = [_prediction(item, model, repeat, False) for item in items for repeat in repeats]
    validated = [_prediction(item, model, repeat, True) for item in items for repeat in repeats]
    write_jsonl(root / f"{stem}.jsonl", raw)
    write_jsonl(root / f"{stem}.validated.jsonl", validated)


def _frozen_fixture(tmp_path: Path):
    repo = tmp_path
    run_id = "toy-discovery-01"
    report = repo / "reports" / run_id
    provenance = report / "provenance"
    prediction_root = repo / "data" / "predictions" / run_id
    dataset = repo / "data" / "certified" / "toy" / "benchmark.jsonl"
    provenance.mkdir(parents=True)
    prediction_root.mkdir(parents=True)
    dataset.parent.mkdir(parents=True)

    items = [_item(base, condition) for base in ("b1", "b2") for condition in ("C0", "C4")]
    subset = [item for item in items if item.base_item_id == "b1"]
    write_jsonl(dataset, items)
    repeat_dir = provenance / "repeat_subsets"
    repeat_dir.mkdir()
    write_jsonl(repeat_dir / "toy_.repeat-subset.jsonl", subset)

    parameters = {
        "protocol_id": "toy-protocol",
        "run_id": run_id,
        "stage": "discovery",
        "inference_seed": 42,
        "max_invalid_rate": 0.02,
        "max_overall_invalid_rate": 0.02,
        "max_api_error_rate": 0.0,
    }
    (provenance / "run_parameters.json").write_text(
        json.dumps(parameters), encoding="utf-8"
    )
    (provenance / "datasets.txt").write_text(
        "data/certified/toy/benchmark.jsonl\n", encoding="utf-8"
    )
    matrix = "vendor/model|model-v1|none|content"
    (provenance / "model_matrix.txt").write_text(matrix + "\n", encoding="utf-8")
    manifest = {
        "protocol_id": "toy-protocol",
        "models": [
            {
                "catalog_key": "vendor/model",
                "model_id": "model-v1",
                "reasoning_effort": "none",
                "answer_field": "content",
            }
        ],
        "stages": {"discovery": {"extra_repeats": 2}},
    }
    (provenance / "experiment_manifest.yaml").write_text(
        yaml.safe_dump(manifest), encoding="utf-8"
    )
    (provenance / "model_artifacts.tsv").write_text(
        f"model-v1\t{'a' * 64}\t/models/vendor/model\n", encoding="utf-8"
    )

    _write_pair(prediction_root, "toy_.model-v1.primary", items, "model-v1", (0,))
    _write_pair(
        prediction_root,
        "toy_.model-v1.repeats-1-2",
        subset,
        "model-v1",
        (1, 2),
    )
    for baseline in ("oracle", "majority", "lexical"):
        _write_pair(prediction_root, f"toy_.{baseline}.primary", items, baseline, (0,))
    evaluation_names = (
        "answer_by_condition.csv",
        "paired_comparisons.csv",
        "paired_validity_comparisons.csv",
        "proof_by_condition.csv",
        "seed_disagreement.csv",
        "orbit_metrics.json",
    )
    for owner in (
        report / "models" / "model-v1" / "toy_",
        report / "baselines" / "oracle" / "toy_",
        report / "baselines" / "majority" / "toy_",
        report / "baselines" / "lexical" / "toy_",
    ):
        owner.mkdir(parents=True, exist_ok=True)
        for name in evaluation_names:
            owner.joinpath(name).write_text(
                "{}\n" if name.endswith(".json") else "x\n",
                encoding="utf-8",
            )
    for diagnostic in (
        report / "diagnostics" / "model-v1" / "toy_" / "response_validity.json",
        report
        / "diagnostics"
        / "model-v1"
        / "toy_"
        / "repeats"
        / "response_validity.json",
    ):
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        diagnostic.write_text('{"status":"PASS"}\n', encoding="utf-8")
    stability = report / "models" / "model-v1" / "toy_" / "stability" / "stability.json"
    stability.parent.mkdir(parents=True)
    stability.write_text("{}\n", encoding="utf-8")
    for name in ("statistical_model", "response_validity_model"):
        model_report = report / "models" / "model-v1" / name
        model_report.mkdir(parents=True)
        (model_report / "model_fit.json").write_text("{}\n", encoding="utf-8")
        (model_report / "model_summary.txt").write_text("fixture\n", encoding="utf-8")
    return repo, run_id, prediction_root


def test_dataset_slug_preserves_frozen_shell_spelling():
    assert dataset_slug(Path("data/certified/cl/benchmark.jsonl")) == "cl_"


def test_primary_analysis_paths_preserve_original_model_major_order(tmp_path):
    run = FrozenRun(
        repo_root=tmp_path,
        report_root=tmp_path / "reports" / "run",
        prediction_root=tmp_path / "predictions",
        protocol_id="p",
        run_id="run",
        stage="discovery",
        parameters={},
        manifest={},
        datasets=(
            tmp_path / "data" / "certified" / "cl" / "benchmark.jsonl",
            tmp_path / "data" / "certified" / "po" / "benchmark.jsonl",
        ),
        models=(
            FrozenModel("vendor/m1", "m1", "none", "content"),
            FrozenModel("vendor/m2", "m2", "none", "content"),
        ),
    )

    assert [path.name for path in primary_validated_paths(run)] == [
        "cl_.m1.primary.validated.jsonl",
        "po_.m1.primary.validated.jsonl",
        "cl_.m2.primary.validated.jsonl",
        "po_.m2.primary.validated.jsonl",
    ]


def test_prediction_recovery_gate_accepts_complete_frozen_run(tmp_path):
    repo, run_id, _ = _frozen_fixture(tmp_path)
    run = load_frozen_run(repo, run_id)

    summary, primary_paths = verify_prediction_artifacts(run)

    assert summary["status"] == "PASS"
    assert summary["primary_predictions"] == 4
    assert summary["repeat_predictions"] == 4
    assert summary["api_errors"] == 0
    assert len(primary_paths) == 1


def test_prediction_recovery_gate_refuses_missing_call(tmp_path):
    repo, run_id, prediction_root = _frozen_fixture(tmp_path)
    path = prediction_root / "toy_.model-v1.primary.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
    run = load_frozen_run(repo, run_id)

    with pytest.raises(RecoveryError, match="prediction completeness failed"):
        verify_prediction_artifacts(run)


def test_recovery_generates_derived_outputs_and_verified_checksums(tmp_path):
    pytest.importorskip("statsmodels")
    repo, run_id, _ = _frozen_fixture(tmp_path)
    report = repo / "reports" / run_id
    (report / "RUN_FAILED.txt").write_text(
        "status=FAILED\nline=984\nexit_status=1\nutc=2026-08-16T00:00:00Z\n",
        encoding="utf-8",
    )
    recovery_sources = (
        "src/owl_equivariance/analysis.py",
        "src/owl_equivariance/dataset.py",
        "src/owl_equivariance/modeling.py",
        "src/owl_equivariance/power.py",
        "src/owl_equivariance/recovery.py",
        "src/owl_equivariance/reporting.py",
        "src/owl_equivariance/schemas.py",
        "scripts/recover_lmstudio_publication.sh",
        "scripts/recover_publication_run.py",
    )
    for name in recovery_sources:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture for {name}\n", encoding="utf-8")

    run = load_frozen_run(repo, run_id)
    verification, primary_paths = verify_prediction_artifacts(run)
    analysis_csv = rebuild_or_verify_analysis(run, primary_paths)
    derived = generate_missing_derived_outputs(
        run,
        analysis_csv,
        primary_paths,
        planned_pairs=20,
        simulations=20,
    )
    complete = finalize_recovered_run(run, verification, derived)

    assert complete["status"] == "PASS"
    assert complete["inference_repeated"] is False
    assert (report / "pooled_correctness_interaction_model" / "model_fit.json").is_file()
    assert (report / "power" / "correctness" / "power.json").is_file()
    assert (report / "RUN_RECOVERY.json").is_file()
    verify_checksums(run)
