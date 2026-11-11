"""Prospective confirmatory-panel freezing and verification.

The confirmatory panel is a scientific input, not a convenience argument to the
inference runner.  This module validates the capacity rules in the frozen manifest,
records the exact dataset hashes, and refuses to overwrite an existing panel artifact.
The resulting JSON is therefore suitable for review and version control *before* any
confirmatory model response is requested.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .dataset import load_items, validate_dataset


class PanelValidationError(ValueError):
    """The proposed confirmatory panel violates its prospective protocol."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class PanelCriteria:
    minimum_sources: int
    minimum_base_items_per_source: int
    minimum_total_base_items: int
    required_conditions: tuple[str, ...]
    excluded_ontology_ids: tuple[str, ...]
    panel_file_required: bool
    required_certifier_version: str | None
    required_candidate_sampling: str | None
    required_justification_algorithm: str | None
    required_justification_call_budget: int | None
    build_checkpoint_required: bool

    @classmethod
    def from_manifest(cls, manifest: dict) -> "PanelCriteria":
        config = manifest["datasets"]["confirmatory"]
        # Backward-compatible fallbacks keep the v2/v3 gate readable while v3.3 uses
        # explicit lower-bound names because the panel may contain more than eight sources.
        minimum_sources = int(config.get("minimum_sources", config.get("required_sources", 0)))
        minimum_per_source = int(
            config.get("minimum_base_items_per_source", config.get("base_items_per_source", 0))
        )
        minimum_total = int(
            config.get(
                "minimum_total_base_items",
                minimum_sources * minimum_per_source,
            )
        )
        conditions = tuple(config["required_conditions"])
        generator = manifest.get("dataset_generation", {})
        if minimum_sources < 2:
            raise PanelValidationError("confirmatory minimum_sources must be at least 2")
        if minimum_per_source < 1 or minimum_total < minimum_sources * minimum_per_source:
            raise PanelValidationError(
                "confirmatory total must be at least minimum_sources times the per-source minimum"
            )
        if len(conditions) != len(set(conditions)):
            raise PanelValidationError("required_conditions contains duplicates")
        return cls(
            minimum_sources=minimum_sources,
            minimum_base_items_per_source=minimum_per_source,
            minimum_total_base_items=minimum_total,
            required_conditions=conditions,
            excluded_ontology_ids=tuple(config.get("excluded_ontology_ids", ())),
            panel_file_required=bool(config.get("panel_file_required", False)),
            required_certifier_version=generator.get("certifier_version"),
            required_candidate_sampling=generator.get("candidate_sampling"),
            required_justification_algorithm=generator.get("justification_algorithm"),
            required_justification_call_budget=(
                int(generator["justification_call_budget_per_candidate"])
                if generator.get("justification_call_budget_per_candidate") is not None
                else None
            ),
            build_checkpoint_required=bool(
                generator.get("atomic_progress_checkpoint_required", False)
            ),
        )


@dataclass(frozen=True)
class SourceSummary:
    path: str
    dataset_sha256: str
    ontology_id: str
    ontology_version: str | None
    ontology_source_hash: str | None
    base_items: int
    rows: int
    conditions: tuple[str, ...]
    task_counts: dict[str, int]
    label_counts: dict[str, int]
    build_report_sha256: str | None = None
    source_file_sha256: str | None = None
    source_canonical_sha256: str | None = None
    certifier_version: str | None = None
    candidate_sampling: str | None = None
    justification_algorithm: str | None = None
    justification_call_budget_per_candidate: int | None = None
    build_checkpoint_sha256: str | None = None
    build_checkpoint_status: str | None = None
    inferred_candidates_enumerated: int | None = None
    bounded_candidate_pool_size: int | None = None
    positive_candidates_examined: int | None = None
    justification_reasoner_calls: int | None = None
    justification_reasoner_builds: int | None = None
    justification_cache_hits: int | None = None
    justification_budget_exhausted_candidates: int | None = None

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["conditions"] = list(self.conditions)
        return payload


def _display_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def summarize_source(
    dataset_path: str | Path,
    *,
    root: str | Path,
    required_conditions: tuple[str, ...],
    full_validation: bool = True,
) -> tuple[SourceSummary, list[str]]:
    path = Path(dataset_path)
    root_path = Path(root)
    problems: list[str] = []
    if not path.is_file():
        raise PanelValidationError(f"dataset does not exist: {path}")
    items = load_items(path)
    if not items:
        raise PanelValidationError(f"dataset is empty: {path}")

    ontology_ids = {item.ontology.ontology_id for item in items}
    if len(ontology_ids) != 1:
        problems.append(f"{path}: expected one ontology_id, found {sorted(ontology_ids)}")
    ontology_id = sorted(ontology_ids)[0] if ontology_ids else ""

    by_base = defaultdict(list)
    for item in items:
        by_base[item.base_item_id].append(item)
    expected = set(required_conditions)
    for base_id, members in by_base.items():
        counts = Counter(item.condition for item in members)
        if set(counts) != expected or any(count != 1 for count in counts.values()):
            problems.append(
                f"{path}: {base_id} is not an exact {len(expected)}-condition orbit"
            )
            break

    if full_validation:
        problems.extend(
            f"{path}: {problem}"
            for problem in validate_dataset(
                items,
                dataset_path=path,
                expected_conditions=list(required_conditions),
            )
        )

    reference_items = [item for item in items if item.condition == "C0"]
    task_counts = Counter(item.task.type for item in reference_items)
    label_counts = Counter(item.task.label for item in reference_items)
    versions = {item.ontology.version for item in items}
    source_hashes = {item.ontology.source_hash for item in items}
    if len(versions) != 1:
        problems.append(f"{path}: ontology version changes within the dataset")
    if len(source_hashes) != 1:
        problems.append(f"{path}: ontology source_hash changes within the dataset")

    build_report = path.with_name("build_report.json")
    report_payload: dict = {}
    report_hash = None
    if build_report.is_file():
        report_hash = sha256_file(build_report)
        report_payload = json.loads(build_report.read_text(encoding="utf-8"))

    build_checkpoint = path.with_name("build_checkpoint.json")
    checkpoint_payload: dict = {}
    checkpoint_hash = None
    if build_checkpoint.is_file():
        checkpoint_hash = sha256_file(build_checkpoint)
        checkpoint_payload = json.loads(build_checkpoint.read_text(encoding="utf-8"))

    summary = SourceSummary(
        path=_display_path(path, root_path),
        dataset_sha256=sha256_file(path),
        ontology_id=ontology_id,
        ontology_version=next(iter(versions)) if len(versions) == 1 else None,
        ontology_source_hash=next(iter(source_hashes)) if len(source_hashes) == 1 else None,
        base_items=len(by_base),
        rows=len(items),
        conditions=tuple(sorted({item.condition for item in items})),
        task_counts=dict(sorted(task_counts.items())),
        label_counts=dict(sorted(label_counts.items())),
        build_report_sha256=report_hash,
        source_file_sha256=report_payload.get("source_file_sha256"),
        source_canonical_sha256=report_payload.get("source_canonical_sha256"),
        certifier_version=report_payload.get("certifier_version"),
        candidate_sampling=report_payload.get("candidate_sampling"),
        justification_algorithm=report_payload.get("justification_algorithm"),
        justification_call_budget_per_candidate=report_payload.get(
            "justification_call_budget_per_candidate"
        ),
        build_checkpoint_sha256=checkpoint_hash,
        build_checkpoint_status=checkpoint_payload.get("status"),
        inferred_candidates_enumerated=report_payload.get(
            "inferred_candidates_enumerated"
        ),
        bounded_candidate_pool_size=report_payload.get("bounded_candidate_pool_size"),
        positive_candidates_examined=report_payload.get("positive_candidates_examined"),
        justification_reasoner_calls=report_payload.get("justification_reasoner_calls"),
        justification_reasoner_builds=report_payload.get("justification_reasoner_builds"),
        justification_cache_hits=report_payload.get("justification_cache_hits"),
        justification_budget_exhausted_candidates=report_payload.get(
            "justification_budget_exhausted_candidates"
        ),
    )
    return summary, problems


def validate_summaries(
    criteria: PanelCriteria,
    summaries: list[SourceSummary],
) -> list[str]:
    problems: list[str] = []
    if len(summaries) < criteria.minimum_sources:
        problems.append(
            f"requires at least {criteria.minimum_sources} sources, found {len(summaries)}"
        )

    ontology_counts = Counter(source.ontology_id for source in summaries)
    duplicates = sorted(name for name, count in ontology_counts.items() if count > 1)
    if duplicates:
        problems.append(f"ontology sources are not independent/unique: {duplicates}")

    excluded = sorted(set(ontology_counts) & set(criteria.excluded_ontology_ids))
    if excluded:
        problems.append(f"discovery or excluded ontologies appear in the panel: {excluded}")

    path_counts = Counter(source.path for source in summaries)
    duplicate_paths = sorted(path for path, count in path_counts.items() if count > 1)
    if duplicate_paths:
        problems.append(f"dataset paths are repeated: {duplicate_paths}")

    for field_name in ("source_file_sha256", "ontology_source_hash"):
        values = [getattr(source, field_name) for source in summaries]
        counts = Counter(value for value in values if value)
        repeated = sorted(value for value, count in counts.items() if count > 1)
        if repeated:
            problems.append(
                f"multiple ontology ids resolve to the same {field_name}: {repeated}"
            )

    for source in summaries:
        if source.base_items < criteria.minimum_base_items_per_source:
            problems.append(
                f"{source.path}: requires at least "
                f"{criteria.minimum_base_items_per_source} base items, found {source.base_items}"
            )
        if set(source.conditions) != set(criteria.required_conditions):
            problems.append(
                f"{source.path}: condition set differs from the frozen protocol"
            )
        generator_requirements = (
            ("certifier_version", criteria.required_certifier_version),
            ("candidate_sampling", criteria.required_candidate_sampling),
            ("justification_algorithm", criteria.required_justification_algorithm),
            (
                "justification_call_budget_per_candidate",
                criteria.required_justification_call_budget,
            ),
        )
        for field_name, required in generator_requirements:
            if required is not None and getattr(source, field_name) != required:
                problems.append(
                    f"{source.path}: {field_name}={getattr(source, field_name)!r}, "
                    f"requires {required!r}"
                )
        if criteria.build_checkpoint_required:
            if source.build_checkpoint_sha256 is None:
                problems.append(f"{source.path}: required build_checkpoint.json is missing")
            elif source.build_checkpoint_status != "COMPLETE":
                problems.append(
                    f"{source.path}: build checkpoint status is "
                    f"{source.build_checkpoint_status!r}, requires 'COMPLETE'"
                )

    total = sum(source.base_items for source in summaries)
    if total < criteria.minimum_total_base_items:
        problems.append(
            f"requires at least {criteria.minimum_total_base_items} total base items, found {total}"
        )
    return problems


def validate_cross_source_base_ids(dataset_paths: list[str | Path]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for dataset_path in dataset_paths:
        base_ids = {item.base_item_id for item in load_items(dataset_path)}
        overlap = seen & base_ids
        if overlap:
            problems.append(
                f"{dataset_path}: base_item_id overlaps another source, "
                f"e.g. {sorted(overlap)[:3]}"
            )
        seen.update(base_ids)
    return problems


def _load_manifest(path: str | Path) -> tuple[Path, dict, PanelCriteria]:
    manifest_path = Path(path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return manifest_path, manifest, PanelCriteria.from_manifest(manifest)


def freeze_panel(
    manifest_path: str | Path,
    dataset_paths: list[str | Path],
    output_path: str | Path,
    *,
    acknowledge_no_confirmatory_outcomes: bool,
) -> dict:
    if not acknowledge_no_confirmatory_outcomes:
        raise PanelValidationError(
            "refusing to freeze: explicitly acknowledge that no confirmatory model outcome "
            "has been inspected"
        )
    manifest_path, manifest, criteria = _load_manifest(manifest_path)
    root = manifest_path.resolve().parent.parent
    summaries: list[SourceSummary] = []
    problems: list[str] = []
    for dataset_path in dataset_paths:
        summary, source_problems = summarize_source(
            dataset_path,
            root=root,
            required_conditions=criteria.required_conditions,
        )
        summaries.append(summary)
        problems.extend(source_problems)
    problems.extend(validate_cross_source_base_ids(dataset_paths))
    problems.extend(validate_summaries(criteria, summaries))
    if problems:
        raise PanelValidationError("confirmatory panel failed:\n- " + "\n- ".join(problems))

    payload = {
        "schema_version": "1.0",
        "status": "FROZEN",
        "protocol_id": manifest["protocol_id"],
        "frozen_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "confirmatory_outcomes_inspected": False,
        "freeze_basis": (
            "capacity, certification, source diversity, and deterministic generator "
            "runtime diagnostics only; no confirmatory model outcomes"
        ),
        "manifest": _display_path(manifest_path, root),
        "manifest_sha256": sha256_file(manifest_path),
        "criteria": asdict(criteria),
        "sources": [summary.as_dict() for summary in summaries],
        "totals": {
            "sources": len(summaries),
            "base_items": sum(source.base_items for source in summaries),
            "rows": sum(source.rows for source in summaries),
        },
        "analysis": manifest.get("analysis", {}),
    }
    payload["criteria"]["required_conditions"] = list(criteria.required_conditions)
    payload["criteria"]["excluded_ontology_ids"] = list(criteria.excluded_ontology_ids)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise PanelValidationError(
            f"refusing to overwrite frozen panel artifact: {output}"
        ) from exc
    return payload


def verify_panel(
    manifest_path: str | Path,
    panel_path: str | Path,
    dataset_paths: list[str | Path] | None = None,
    *,
    root: str | Path | None = None,
) -> dict:
    manifest_path, manifest, criteria = _load_manifest(manifest_path)
    root = Path(root).resolve() if root is not None else manifest_path.resolve().parent.parent
    panel = json.loads(Path(panel_path).read_text(encoding="utf-8"))
    problems: list[str] = []
    if panel.get("status") != "FROZEN":
        problems.append("panel status is not FROZEN")
    if panel.get("confirmatory_outcomes_inspected") is not False:
        problems.append("panel does not assert that confirmatory outcomes were unseen")
    if panel.get("protocol_id") != manifest.get("protocol_id"):
        problems.append("panel protocol_id differs from the manifest")
    if panel.get("manifest_sha256") != sha256_file(manifest_path):
        problems.append("manifest changed after the panel was frozen")

    recorded_sources = panel.get("sources") or []
    recorded_paths = [source.get("path") for source in recorded_sources]
    if dataset_paths is not None:
        requested = [_display_path(Path(path), root) for path in dataset_paths]
        if requested != recorded_paths:
            problems.append("runtime dataset order/list differs from the frozen panel")
    else:
        dataset_paths = [root / path for path in recorded_paths]

    summaries: list[SourceSummary] = []
    for path, recorded in zip(dataset_paths, recorded_sources):
        summary, source_problems = summarize_source(
            path,
            root=root,
            required_conditions=criteria.required_conditions,
        )
        summaries.append(summary)
        problems.extend(source_problems)
        if summary.as_dict() != recorded:
            problems.append(f"{summary.path}: dataset/build metadata changed after panel freeze")
    problems.extend(validate_cross_source_base_ids(dataset_paths))
    problems.extend(validate_summaries(criteria, summaries))
    if problems:
        raise PanelValidationError("frozen panel verification failed:\n- " + "\n- ".join(problems))
    return {
        "status": "PASS",
        "protocol_id": manifest["protocol_id"],
        "panel_sha256": sha256_file(panel_path),
        "sources": len(summaries),
        "base_items": sum(source.base_items for source in summaries),
        "rows": sum(source.rows for source in summaries),
        "datasets": [source.path for source in summaries],
    }
