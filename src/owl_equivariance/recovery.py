"""Strict post-processing recovery for completed publication inference runs.

The LM Studio publication runner deliberately stops on any failed analysis step.  A late
analysis failure must not force another multi-day inference run, but it also must not be
papered over with an unverified ``RUN_COMPLETE.json``.  This module reconstructs the
frozen run from provenance, verifies every expected prediction, regenerates the pooled
derived analyses, and only then creates an immutable completion manifest and checksums.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import analysis, modeling, power, protocol, reporting
from .dataset import load_items, load_predictions


class RecoveryError(RuntimeError):
    """A frozen-run invariant failed; finalization must stop."""


@dataclass(frozen=True)
class FrozenModel:
    catalog_key: str
    model_id: str
    reasoning_effort: str
    answer_field: str

    @property
    def slug(self) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", self.model_id)


@dataclass(frozen=True)
class FrozenRun:
    repo_root: Path
    report_root: Path
    prediction_root: Path
    protocol_id: str
    run_id: str
    stage: str
    parameters: dict
    manifest: dict
    datasets: tuple[Path, ...]
    models: tuple[FrozenModel, ...]

    @property
    def extra_repeats(self) -> int:
        return int(self.manifest.get("stages", {}).get(self.stage, {}).get("extra_repeats", 0))


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RecoveryError(f"required frozen artifact is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RecoveryError(f"invalid JSON in frozen artifact {path}: {exc}") from exc


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise RecoveryError(f"required artifact is missing: {path}")


def dataset_slug(path: Path) -> str:
    """Reproduce the publication runner's historical ``cl_``/``po_`` slug exactly."""
    # The shell implementation pipes newline-terminated ``basename`` output through
    # ``tr -cs``, so the newline becomes one trailing underscore.  Existing frozen runs
    # use that spelling and recovery must never silently rename their artifacts.
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.parent.name + "\n")


def load_frozen_run(
    repo_root: str | Path,
    run_id: str,
    *,
    report_root: str | Path | None = None,
    prediction_root: str | Path | None = None,
) -> FrozenRun:
    repo = Path(repo_root).resolve()
    reports = Path(report_root).resolve() if report_root else repo / "reports" / run_id
    predictions = (
        Path(prediction_root).resolve()
        if prediction_root
        else repo / "data" / "predictions" / run_id
    )
    if not reports.is_dir():
        raise RecoveryError(f"report directory does not exist: {reports}")
    if not predictions.is_dir():
        raise RecoveryError(
            f"prediction directory does not exist: {predictions}; copy the original raw "
            "and validated predictions from the inference server before recovery"
        )

    provenance = reports / "provenance"
    parameters = _read_json(provenance / "run_parameters.json")
    if parameters.get("run_id") != run_id:
        raise RecoveryError(
            f"run-id mismatch: requested {run_id!r}, provenance has {parameters.get('run_id')!r}"
        )
    stage = str(parameters.get("stage", ""))
    if stage not in {"discovery", "confirmatory"}:
        raise RecoveryError(
            f"post-processing recovery is only valid for discovery/confirmatory runs, got {stage!r}"
        )

    manifest_path = provenance / "experiment_manifest.yaml"
    _require_file(manifest_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    protocol_id = str(parameters.get("protocol_id", ""))
    if manifest.get("protocol_id") != protocol_id:
        raise RecoveryError("protocol_id differs between run_parameters.json and frozen manifest")

    datasets_file = provenance / "datasets.txt"
    matrix_file = provenance / "model_matrix.txt"
    _require_file(datasets_file)
    _require_file(matrix_file)
    dataset_names = [
        line for line in datasets_file.read_text(encoding="utf-8").splitlines() if line
    ]
    datasets = tuple(
        (repo / name).resolve() if not Path(name).is_absolute() else Path(name)
        for name in dataset_names
    )
    for dataset in datasets:
        _require_file(dataset)

    models = []
    for line in matrix_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 4 or not all(fields):
            raise RecoveryError(f"invalid frozen model specification: {line!r}")
        models.append(FrozenModel(*fields))
    if not models:
        raise RecoveryError("frozen model matrix is empty")

    manifest_models = [
        (
            str(row["catalog_key"]),
            str(row["model_id"]),
            str(row["reasoning_effort"]),
            str(row["answer_field"]),
        )
        for row in manifest.get("models", [])
    ]
    frozen_models = [
        (model.catalog_key, model.model_id, model.reasoning_effort, model.answer_field)
        for model in models
    ]
    if manifest_models != frozen_models:
        raise RecoveryError("frozen model_matrix.txt does not match the frozen manifest")

    if stage == "confirmatory":
        try:
            criteria = protocol.PanelCriteria.from_manifest(manifest)
        except (KeyError, TypeError, protocol.PanelValidationError) as exc:
            raise RecoveryError("confirmatory manifest has no valid dataset criteria") from exc
        if criteria.panel_file_required:
            panel_path = provenance / "confirmatory_panel.json"
            _require_file(panel_path)
            try:
                protocol.verify_panel(
                    manifest_path,
                    panel_path,
                    list(datasets),
                    root=repo,
                )
            except protocol.PanelValidationError as exc:
                raise RecoveryError(str(exc)) from exc

    return FrozenRun(
        repo_root=repo,
        report_root=reports,
        prediction_root=predictions,
        protocol_id=protocol_id,
        run_id=run_id,
        stage=stage,
        parameters=parameters,
        manifest=manifest,
        datasets=datasets,
        models=tuple(models),
    )


def _prediction_map(predictions, path: Path) -> dict[tuple[str, int], object]:
    mapped = {}
    for prediction in predictions:
        key = (prediction.orbit_item_id, prediction.repeat)
        if key in mapped:
            raise RecoveryError(f"duplicate prediction key {key!r} in {path}")
        mapped[key] = prediction
    return mapped


def _verify_prediction_pair(
    *,
    dataset_path: Path,
    raw_path: Path,
    validated_path: Path,
    model_id: str,
    repeats: tuple[int, ...],
    require_payload: bool,
    max_per_condition_invalid_rate: float,
    max_overall_invalid_rate: float,
    max_api_error_rate: float,
) -> tuple[int, int, int]:
    _require_file(raw_path)
    _require_file(validated_path)
    items = load_items(dataset_path)
    by_id = {item.orbit_item_id: item for item in items}
    if len(by_id) != len(items):
        raise RecoveryError(f"duplicate orbit_item_id values in dataset {dataset_path}")
    expected = {(item.orbit_item_id, repeat) for item in items for repeat in repeats}

    raw_rows = load_predictions(raw_path)
    validated_rows = load_predictions(validated_path)
    raw = _prediction_map(raw_rows, raw_path)
    validated = _prediction_map(validated_rows, validated_path)
    if set(raw) != expected:
        missing = sorted(expected - set(raw))[:3]
        extra = sorted(set(raw) - expected)[:3]
        raise RecoveryError(
            f"prediction completeness failed for {raw_path}: expected={len(expected)}, "
            f"actual={len(raw)}, missing={missing}, extra={extra}"
        )
    if set(validated) != expected:
        missing = sorted(expected - set(validated))[:3]
        extra = sorted(set(validated) - expected)[:3]
        raise RecoveryError(
            f"support-validation coverage failed for {validated_path}: "
            f"expected={len(expected)}, actual={len(validated)}, missing={missing}, extra={extra}"
        )

    invalid_by_condition: dict[str, list[bool]] = {}
    api_errors = 0
    immutable_fields = (
        "orbit_item_id",
        "base_item_id",
        "condition",
        "model",
        "prompt_style",
        "label",
        "raw_output",
        "runner_error",
        "parse_error",
        "repeat",
    )
    for key in sorted(expected):
        prediction = raw[key]
        certified = validated[key]
        item = by_id[prediction.orbit_item_id]
        if prediction.model != model_id:
            raise RecoveryError(
                f"model identity mismatch in {raw_path}: {prediction.model!r} != {model_id!r}"
            )
        if prediction.base_item_id != item.base_item_id or prediction.condition != item.condition:
            raise RecoveryError(f"dataset identity mismatch for {key!r} in {raw_path}")
        if require_payload and not isinstance(prediction.response_payload, dict):
            raise RecoveryError(f"raw response payload missing for {key!r} in {raw_path}")
        if prediction.runner_error:
            api_errors += 1
        invalid = (
            prediction.label is None
            or bool(prediction.parse_error)
            or bool(prediction.runner_error)
        )
        invalid_by_condition.setdefault(prediction.condition, []).append(invalid)
        for field in immutable_fields:
            if getattr(prediction, field) != getattr(certified, field):
                raise RecoveryError(
                    f"support validator changed immutable field {field!r} for {key!r}"
                )
        if not all(
            isinstance(value, bool)
            for value in (
                certified.answer_correct,
                certified.support_valid,
                certified.support_minimal,
            )
        ):
            raise RecoveryError(f"support-validation fields are absent for {key!r}")

    total = len(expected)
    invalid_count = sum(sum(values) for values in invalid_by_condition.values())
    if invalid_count / max(total, 1) > max_overall_invalid_rate + 1e-12:
        raise RecoveryError(
            f"overall invalid-response rate exceeds the frozen gate in {raw_path}: "
            f"{invalid_count}/{total} > {max_overall_invalid_rate:.2%}"
        )
    for condition, values in sorted(invalid_by_condition.items()):
        rate = sum(values) / len(values)
        if rate > max_per_condition_invalid_rate + 1e-12:
            raise RecoveryError(
                f"invalid-response rate for {condition} exceeds the frozen gate in "
                f"{raw_path}: {rate:.2%} > {max_per_condition_invalid_rate:.2%}"
            )
    if api_errors / max(total, 1) > max_api_error_rate + 1e-12:
        raise RecoveryError(
            f"API-error rate exceeds the frozen gate in {raw_path}: "
            f"{api_errors}/{total} > {max_api_error_rate:.2%}"
        )
    return total, invalid_count, api_errors


def _verify_model_artifact_records(run: FrozenRun) -> None:
    path = run.report_root / "provenance" / "model_artifacts.tsv"
    _require_file(path)
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            raise RecoveryError(f"invalid model artifact record: {line!r}")
        model_id, digest, artifact = fields
        if model_id in records:
            raise RecoveryError(f"duplicate model artifact record for {model_id}")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RecoveryError(f"invalid weights SHA-256 for {model_id}: {digest!r}")
        if not artifact:
            raise RecoveryError(f"empty model artifact path for {model_id}")
        records[model_id] = digest
    expected = {model.model_id for model in run.models}
    if set(records) != expected:
        raise RecoveryError(
            f"model artifact coverage mismatch: missing={sorted(expected - set(records))}, "
            f"extra={sorted(set(records) - expected)}"
        )


def _verify_existing_reports(run: FrozenRun) -> int:
    required = []
    evaluation_names = (
        "answer_by_condition.csv",
        "paired_comparisons.csv",
        "paired_validity_comparisons.csv",
        "proof_by_condition.csv",
        "seed_disagreement.csv",
        "orbit_metrics.json",
    )
    for dataset in run.datasets:
        slug = dataset_slug(dataset)
        for model in run.models:
            evaluation = run.report_root / "models" / model.slug / slug
            required.extend(evaluation / name for name in evaluation_names)
            diagnostic = (
                run.report_root / "diagnostics" / model.slug / slug / "response_validity.json"
            )
            required.append(diagnostic)
            if run.extra_repeats:
                required.extend(
                    (
                        run.report_root
                        / "diagnostics"
                        / model.slug
                        / slug
                        / "repeats"
                        / "response_validity.json",
                        evaluation / "stability" / "stability.json",
                    )
                )
        for baseline in ("oracle", "majority", "lexical"):
            evaluation = run.report_root / "baselines" / baseline / slug
            required.extend(evaluation / name for name in evaluation_names)

    for model in run.models:
        required.extend(
            (
                run.report_root / "models" / model.slug / "statistical_model" / "model_fit.json",
                run.report_root
                / "models"
                / model.slug
                / "statistical_model"
                / "model_summary.txt",
                run.report_root
                / "models"
                / model.slug
                / "response_validity_model"
                / "model_fit.json",
                run.report_root
                / "models"
                / model.slug
                / "response_validity_model"
                / "model_summary.txt",
            )
        )

    for path in required:
        _require_file(path)
        if path.name == "response_validity.json":
            payload = _read_json(path)
            if payload.get("status") != "PASS":
                raise RecoveryError(f"response-validity report did not pass: {path}")
    return len(required)


def primary_validated_paths(run: FrozenRun) -> list[Path]:
    """Return the exact model-major order used by the original inference runner."""
    return [
        run.prediction_root
        / f"{dataset_slug(dataset)}.{model.slug}.primary.validated.jsonl"
        for model in run.models
        for dataset in run.datasets
    ]


def verify_prediction_artifacts(run: FrozenRun) -> tuple[dict, list[Path]]:
    """Verify exact prediction/support coverage and return primary validated paths."""
    _verify_model_artifact_records(run)
    verified_reports = _verify_existing_reports(run)
    max_invalid = float(run.parameters["max_invalid_rate"])
    max_overall = float(run.parameters.get("max_overall_invalid_rate", max_invalid))
    max_api = float(run.parameters["max_api_error_rate"])
    primary_rows = repeat_rows = invalid = api_errors = 0

    for dataset in run.datasets:
        slug = dataset_slug(dataset)
        for model in run.models:
            raw = run.prediction_root / f"{slug}.{model.slug}.primary.jsonl"
            validated = run.prediction_root / f"{slug}.{model.slug}.primary.validated.jsonl"
            count, bad, errors = _verify_prediction_pair(
                dataset_path=dataset,
                raw_path=raw,
                validated_path=validated,
                model_id=model.model_id,
                repeats=(0,),
                require_payload=True,
                max_per_condition_invalid_rate=max_invalid,
                max_overall_invalid_rate=max_overall,
                max_api_error_rate=max_api,
            )
            primary_rows += count
            invalid += bad
            api_errors += errors

            if run.extra_repeats:
                subset = (
                    run.report_root
                    / "provenance"
                    / "repeat_subsets"
                    / f"{slug}.repeat-subset.jsonl"
                )
                repeat_raw = run.prediction_root / f"{slug}.{model.slug}.repeats-1-2.jsonl"
                repeat_validated = (
                    run.prediction_root / f"{slug}.{model.slug}.repeats-1-2.validated.jsonl"
                )
                count, bad, errors = _verify_prediction_pair(
                    dataset_path=subset,
                    raw_path=repeat_raw,
                    validated_path=repeat_validated,
                    model_id=model.model_id,
                    repeats=tuple(range(1, run.extra_repeats + 1)),
                    require_payload=True,
                    max_per_condition_invalid_rate=max_invalid,
                    max_overall_invalid_rate=max_overall,
                    max_api_error_rate=max_api,
                )
                repeat_rows += count
                invalid += bad
                api_errors += errors

        # Baselines are model-independent but are part of the frozen discovery release.
        for baseline in ("oracle", "majority", "lexical"):
            raw = run.prediction_root / f"{slug}.{baseline}.primary.jsonl"
            validated = run.prediction_root / f"{slug}.{baseline}.primary.validated.jsonl"
            _verify_prediction_pair(
                dataset_path=dataset,
                raw_path=raw,
                validated_path=validated,
                model_id=baseline,
                repeats=(0,),
                require_payload=False,
                max_per_condition_invalid_rate=1.0,
                max_overall_invalid_rate=1.0,
                max_api_error_rate=1.0,
            )

    expected_primary = sum(len(load_items(path)) for path in run.datasets) * len(run.models)
    if primary_rows != expected_primary:
        raise RecoveryError(
            f"pooled primary count mismatch: {primary_rows} != {expected_primary}"
        )
    # Mirror run_lmstudio_publication.sh exactly: its inference loop is model-major,
    # dataset-minor, and export-analysis preserves prediction input order.  The recovery
    # verifier above is dataset-major for efficient validation, so reconstruct the frozen
    # export order explicitly before byte-comparing primary_analysis.csv.
    primary_validated = primary_validated_paths(run)
    return (
        {
            "status": "PASS",
            "datasets": len(run.datasets),
            "models": len(run.models),
            "primary_predictions": primary_rows,
            "repeat_predictions": repeat_rows,
            "invalid_or_error_predictions": invalid,
            "api_errors": api_errors,
            "primary_validated_files": len(primary_validated),
            "verified_existing_reports": verified_reports,
        },
        primary_validated,
    )


def _same_file(left: Path, right: Path) -> bool:
    return left.read_bytes() == right.read_bytes()


def rebuild_or_verify_analysis(run: FrozenRun, primary_paths: list[Path]) -> Path:
    items = [item for path in run.datasets for item in load_items(path)]
    predictions = [prediction for path in primary_paths for prediction in load_predictions(path)]
    result = analysis.build_rows(
        items,
        predictions,
        reference="C0",
        prompt_style="structured_proof",
    )
    target = run.report_root / "primary_analysis.csv"
    recipe = target.with_suffix(".model-recipe.txt")
    with tempfile.TemporaryDirectory(prefix=".analysis-recovery-", dir=run.report_root) as tmp:
        temporary = Path(tmp) / "primary_analysis.csv"
        reporting.write_csv(temporary, result.as_dicts(), analysis.ANALYSIS_COLUMNS)
        temporary_recipe = temporary.with_suffix(".model-recipe.txt")
        temporary_recipe.write_text(analysis.MODEL_RECIPE, encoding="utf-8")
        if target.exists() and not _same_file(target, temporary):
            raise RecoveryError(
                "existing primary_analysis.csv does not reproduce exactly from frozen predictions"
            )
        if recipe.exists() and not _same_file(recipe, temporary_recipe):
            raise RecoveryError("existing primary_analysis.model-recipe.txt has changed")
        if not target.exists():
            shutil.copy2(temporary, target)
        if not recipe.exists():
            shutil.copy2(temporary_recipe, recipe)
    return target


def _write_model_result(result: modeling.ModelResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if result.coefficients:
        reporting.write_csv(
            output_dir / "model_coefficients.csv",
            result.coefficients,
            modeling.COEFFICIENT_COLUMNS,
        )
    (output_dir / "model_fit.json").write_text(
        json.dumps(result.as_dict(), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    # statsmodels embeds the wall-clock date and time in its text table. Normalize only
    # those presentation fields so an interrupted recovery can reproduce byte-identical
    # scientific artifacts and safely resume.
    summary = re.sub(
        r"Date:\s+.*?(?=\s+Scale:)",
        "Date: reproducibly-omitted",
        result.summary_text,
    )
    summary = re.sub(
        r"Time:\s+\S+",
        "Time: reproducibly-omitted",
        summary,
    )
    (output_dir / "model_summary.txt").write_text(summary + "\n", encoding="utf-8")


def _install_tree(temporary: Path, target: Path) -> None:
    if target.exists():
        left = {
            path.relative_to(temporary): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in temporary.rglob("*")
            if path.is_file()
        }
        right = {
            path.relative_to(target): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in target.rglob("*")
            if path.is_file()
        }
        if left != right:
            raise RecoveryError(
                f"derived output already exists but differs from the reproducible result: {target}"
            )
        return
    shutil.copytree(temporary, target)


def generate_missing_derived_outputs(
    run: FrozenRun,
    analysis_csv: Path,
    primary_paths: list[Path],
    *,
    planned_pairs: int | None = None,
    simulations: int = 10000,
) -> dict:
    """Regenerate the frozen post-processing plan without inference."""
    fit_status = {}
    primary_implementation = (
        run.manifest.get("analysis", {}).get("primary", {}).get("implementation", "gee")
    )
    if run.stage == "confirmatory" and primary_implementation == "lme4_glmer_laplace":
        rscript = shutil.which("Rscript")
        if not rscript:
            raise RecoveryError("v3.3 recovery requires Rscript for the primary GLMM")
        script = run.repo_root / "scripts" / "analyze_confirmatory_v33.R"
        _require_file(script)
        with tempfile.TemporaryDirectory(prefix=".confirmatory-glmm-", dir=run.report_root) as tmp:
            temporary = Path(tmp) / "confirmatory_glmm"
            try:
                subprocess.run(
                    [rscript, str(script), str(analysis_csv), str(temporary)],
                    cwd=run.repo_root,
                    check=True,
                    text=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                raise RecoveryError(
                    "v3.3 primary GLMM recovery failed: "
                    + (exc.stderr.strip() or exc.stdout.strip() or str(exc))
                ) from exc
            _install_tree(temporary, run.report_root / "confirmatory_glmm")
        fit_status["primary_glmm"] = "FIT_OR_RECORDED_CONSTANT_OUTCOME"

    for outcome, dirname in (
        ("correct", "pooled_correctness_interaction_model"),
        ("parsed", "pooled_response_validity_interaction_model"),
    ):
        result = modeling.fit(
            str(analysis_csv),
            estimator="gee",
            reference="C0",
            outcome=outcome,
            condition_model_interaction=True,
        )
        with tempfile.TemporaryDirectory(prefix=f".{dirname}-", dir=run.report_root) as tmp:
            temporary = Path(tmp) / dirname
            _write_model_result(result, temporary)
            _install_tree(temporary, run.report_root / dirname)
        fit_status[outcome] = result.fit_status

    if run.stage == "confirmatory":
        return {
            "pooled_model_fit_status": fit_status,
            "power": {
                "status": "SKIPPED_FROZEN_CONFIRMATORY",
                "reason": "post-hoc confirmatory power is forbidden",
            },
        }

    if planned_pairs is None:
        planned_pairs = int(
            run.manifest.get("stages", {})
            .get("confirmatory", {})
            .get("planned_base_items", 1200)
        )
    items = [item for path in run.datasets for item in load_items(path)]
    predictions = [prediction for path in primary_paths for prediction in load_predictions(path)]
    power_status = {}
    for outcome in ("correct", "parsed"):
        result = power.analyze(
            items,
            predictions,
            reference="C0",
            condition="C4",
            outcome=outcome,
            planned_pairs=planned_pairs,
            target_gap=0.05,
            family_size=10,
            simulations=simulations,
            min_power=0.80,
            seed=int(run.parameters["inference_seed"]),
        )
        power_name = "correctness" if outcome == "correct" else "response_validity"
        target = run.report_root / "power" / power_name
        with tempfile.TemporaryDirectory(prefix=f".power-{outcome}-", dir=run.report_root) as tmp:
            temporary = Path(tmp) / outcome
            power.write_report(result, temporary)
            _install_tree(temporary, target)
        power_status[outcome] = {
            "status": "PASS" if result.passed else "ADVISORY_FAIL",
            "failures": result.failures,
        }
    return {"pooled_model_fit_status": fit_status, "power": power_status}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _checksum_files(run: FrozenRun) -> list[Path]:
    excluded = {
        run.report_root / "SHA256SUMS",
        run.report_root / "logs" / "run.log",
    }
    files = []
    for root in (run.prediction_root, run.report_root):
        files.extend(path for path in root.rglob("*") if path.is_file() and path not in excluded)
    return sorted(files, key=lambda path: _checksum_name(run, path))


def _checksum_name(run: FrozenRun, path: Path) -> str:
    try:
        return path.relative_to(run.repo_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def verify_checksums(run: FrozenRun) -> None:
    checksum_path = run.report_root / "SHA256SUMS"
    _require_file(checksum_path)
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RecoveryError(f"malformed SHA256SUMS line {line_number}: {line!r}")
        recorded = Path(name)
        path = recorded if recorded.is_absolute() else (run.repo_root / recorded).resolve()
        if not recorded.is_absolute() and run.repo_root not in (path, *path.parents):
            raise RecoveryError(f"checksum entry escapes the repository root: {name!r}")
        _require_file(path)
        actual = _sha256(path)
        if actual != digest:
            raise RecoveryError(f"checksum mismatch for {name}: {actual} != {digest}")


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _inference_runtime_bounds(run: FrozenRun) -> tuple[str | None, str | None]:
    path = run.report_root / "provenance" / "model_runtime.tsv"
    if not path.is_file():
        return None, None
    starts = []
    finishes = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) >= 3:
            starts.append(fields[1])
            finishes.append(fields[2])
    return (min(starts) if starts else None, max(finishes) if finishes else None)


def finalize_recovered_run(run: FrozenRun, verification: dict, derived: dict) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    failure_path = run.report_root / "RUN_FAILED.txt"
    _require_file(failure_path)
    original_failure = {}
    for line in failure_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            original_failure[key] = value

    recovery_path = run.report_root / "RUN_RECOVERY.json"
    complete_path = run.report_root / "RUN_COMPLETE.json"
    checksum_path = run.report_root / "SHA256SUMS"
    if complete_path.exists() and checksum_path.exists():
        complete = _read_json(complete_path)
        if complete.get("completion_mode") != "recovered_postprocessing":
            raise RecoveryError("RUN_COMPLETE.json exists and was not created by recovery")
        verify_checksums(run)
        return complete

    existing_recovery = _read_json(recovery_path) if recovery_path.exists() else None
    recovered_utc = (
        str(existing_recovery["recovered_utc"]) if existing_recovery else now
    )
    inference_started, inference_finished = _inference_runtime_bounds(run)
    source_files = [
        run.repo_root / "src" / "owl_equivariance" / "analysis.py",
        run.repo_root / "src" / "owl_equivariance" / "dataset.py",
        run.repo_root / "src" / "owl_equivariance" / "modeling.py",
        run.repo_root / "src" / "owl_equivariance" / "power.py",
        run.repo_root / "src" / "owl_equivariance" / "recovery.py",
        run.repo_root / "src" / "owl_equivariance" / "reporting.py",
        run.repo_root / "src" / "owl_equivariance" / "schemas.py",
        run.repo_root / "scripts" / "recover_lmstudio_publication.sh",
        run.repo_root / "scripts" / "recover_publication_run.py",
    ]
    if run.protocol_id == "owleq-jws-2026-08-v33":
        source_files.extend(
            [
                run.repo_root / "src" / "owl_equivariance" / "protocol.py",
                run.repo_root / "scripts" / "analyze_confirmatory_v33.R",
            ]
        )
    recovery = {
        "status": "PASS",
        "protocol_id": run.protocol_id,
        "run_id": run.run_id,
        "stage": run.stage,
        "recovered_utc": recovered_utc,
        "original_inference_started_utc": inference_started,
        "original_inference_finished_utc": inference_finished,
        "original_failure": original_failure,
        "verification": verification,
        "derived_outputs": derived,
        "recovery_source_sha256": {
            path.relative_to(run.repo_root).as_posix(): _sha256(path) for path in source_files
        },
        "notes": [
            "No inference request was made during recovery.",
            "RUN_FAILED.txt is retained as immutable provenance of the original analysis failure.",
            "A NON_IDENTIFIABLE validity model is a statistical result, not a recovery failure.",
        ],
    }
    complete = {
        "status": "PASS",
        "protocol_id": run.protocol_id,
        "run_id": run.run_id,
        "stage": run.stage,
        "started_utc": inference_started,
        "inference_finished_utc": inference_finished,
        "finished_utc": recovered_utc,
        "completion_mode": "recovered_postprocessing",
        "inference_repeated": False,
        "original_failure_retained": True,
    }
    _atomic_json(recovery_path, recovery)
    _atomic_json(complete_path, complete)

    lines = []
    for path in _checksum_files(run):
        lines.append(f"{_sha256(path)}  {_checksum_name(run, path)}\n")
    temporary = checksum_path.with_name(".SHA256SUMS.tmp")
    temporary.write_text("".join(lines), encoding="utf-8", newline="\n")
    os.replace(temporary, checksum_path)
    verify_checksums(run)
    return complete
