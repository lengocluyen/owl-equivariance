"""Auditable post-failure continuation support for frozen LM Studio runs.

This module deliberately does not reinterpret a failed confirmatory run as a passing
preregistered run.  It protects every prediction byte that existed at the amendment
boundary and records the continuation as a protocol deviation.  New inference may only
append records after those protected byte prefixes.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTINUATION_SCHEMA = "owleq-post-failure-continuation-v1"
ATTEMPT_SCHEMA = "owleq-post-failure-continuation-attempt-v1"
V33_PROTOCOL_ID = "owleq-jws-2026-08-v33"


class ContinuationError(RuntimeError):
    """Raised when a continuation safety or provenance gate fails."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _sha256(path: Path, *, byte_limit: int | None = None) -> str:
    digest = hashlib.sha256()
    remaining = byte_limit
    with path.open("rb") as handle:
        while remaining is None or remaining > 0:
            size = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
            block = handle.read(size)
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    if remaining not in (None, 0):
        raise ContinuationError(
            f"file became shorter while hashing its protected prefix: {path}"
        )
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    count = 0
    last = b""
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            count += block.count(b"\n")
            last = block[-1:]
    return count + (1 if path.stat().st_size and last != b"\n" else 0)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ContinuationError(f"artifact is outside the repository: {path}") from exc


def _atomic_json(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise ContinuationError(f"refusing to overwrite frozen amendment: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive and path.exists():
            raise ContinuationError(f"refusing to overwrite frozen amendment: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _required_provenance(report_root: Path) -> list[Path]:
    provenance = report_root / "provenance"
    return [
        report_root / "RUN_FAILED.txt",
        provenance / "experiment_manifest.yaml",
        provenance / "run_parameters.json",
        provenance / "datasets.txt",
        provenance / "confirmatory_panel.json",
        provenance / "model_matrix.txt",
        provenance / "dataset_sha256.txt",
        provenance / "model_artifacts.tsv",
        provenance / "model_runtime.tsv",
    ]


def _artifact_record(path: Path, root: Path) -> dict[str, Any]:
    size = path.stat().st_size
    record: dict[str, Any] = {
        "path": _relative(path, root),
        "bytes": size,
        "sha256": _sha256(path),
    }
    if path.suffix == ".jsonl":
        record["lines"] = _line_count(path)
    return record


def prepare_amendment(
    root: str | Path,
    run_id: str,
    amendment_path: str | Path,
    *,
    protocol_id: str = V33_PROTOCOL_ID,
) -> dict[str, Any]:
    """Freeze the state of a failed v3.3 run before any continuation request."""
    root = Path(root).resolve()
    report_root = root / "reports" / run_id
    prediction_root = root / "data" / "predictions" / run_id
    amendment_path = Path(amendment_path)
    if not amendment_path.is_absolute():
        amendment_path = root / amendment_path

    if protocol_id != V33_PROTOCOL_ID:
        raise ContinuationError(
            f"this amendment implementation is restricted to {V33_PROTOCOL_ID!r}"
        )
    if not report_root.is_dir() or not prediction_root.is_dir():
        raise ContinuationError(f"failed run artifacts were not found for {run_id!r}")
    if (report_root / "RUN_COMPLETE.json").exists():
        raise ContinuationError("refusing continuation: RUN_COMPLETE.json already exists")

    required = _required_provenance(report_root)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ContinuationError("required failed-run provenance is missing: " + ", ".join(missing))

    parameters = json.loads(
        (report_root / "provenance" / "run_parameters.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "protocol_id": protocol_id,
        "run_id": run_id,
        "stage": "confirmatory",
    }
    actual = {key: parameters.get(key) for key in expected}
    if actual != expected:
        raise ContinuationError(
            f"failed-run identity mismatch: expected={expected!r}, actual={actual!r}"
        )

    predictions = sorted(prediction_root.glob("*.jsonl"))
    if not predictions:
        raise ContinuationError("no existing predictions were found to protect")
    provenance = [_artifact_record(path, root) for path in required]
    prediction_records = [_artifact_record(path, root) for path in predictions]
    original_failure = (report_root / "RUN_FAILED.txt").read_text(encoding="utf-8")

    payload: dict[str, Any] = {
        "schema": CONTINUATION_SCHEMA,
        "status": "FROZEN_POST_FAILURE_AMENDMENT",
        "created_utc": _utc_now(),
        "protocol_id": protocol_id,
        "run_id": run_id,
        "classification": "post_failure_protocol_deviation",
        "trigger": {
            "kind": "response_validity_gate_failure",
            "original_run_failed_text": original_failure,
            "outcome_knowledge_at_amendment": (
                "The failed response-validity report and already-produced responses had "
                "been inspected; this is not a prospective amendment."
            ),
        },
        "policy": {
            "frozen_manifest_changed": False,
            "existing_prediction_bytes_must_be_preserved": True,
            "completed_item_repeat_retry_prohibited": True,
            "new_requests_are_only_for_missing_item_repeat_keys": True,
            "invalid_responses_are_retained_and_scored_incorrect": True,
            "response_validity_threshold_failures": "recorded_nonfatal_for_collection",
            "api_errors": "fatal",
            "missing_or_duplicate_predictions": "fatal",
            "model_artifact_identity_mismatch": "fatal",
            "support_validation_coverage_failure": "fatal",
            "inference_settings_mismatch": "fatal",
            "manuscript_disclosure_required": True,
            "preregistered_status_must_not_be_claimed": True,
        },
        "protected_provenance": provenance,
        "protected_prediction_prefixes": prediction_records,
        "snapshot_totals": {
            "files": len(prediction_records),
            "lines": sum(record.get("lines", 0) for record in prediction_records),
            "bytes": sum(record["bytes"] for record in prediction_records),
        },
    }
    _atomic_json(amendment_path, payload, exclusive=True)

    original_copy = amendment_path.parent / "original_RUN_FAILED.txt"
    try:
        with original_copy.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(original_failure)
    except FileExistsError:
        if original_copy.read_text(encoding="utf-8") != original_failure:
            raise ContinuationError(
                f"existing original failure copy differs: {original_copy}"
            )
    return payload


def load_amendment(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ContinuationError(f"continuation amendment not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != CONTINUATION_SCHEMA:
        raise ContinuationError("unsupported continuation amendment schema")
    if payload.get("status") != "FROZEN_POST_FAILURE_AMENDMENT":
        raise ContinuationError("continuation amendment is not frozen")
    if payload.get("protocol_id") != V33_PROTOCOL_ID:
        raise ContinuationError("continuation amendment belongs to another protocol")
    return payload


def verify_amendment(root: str | Path, amendment_path: str | Path) -> dict[str, Any]:
    """Verify immutable provenance and byte-prefix preservation of all saved predictions."""
    root = Path(root).resolve()
    amendment_path = Path(amendment_path)
    if not amendment_path.is_absolute():
        amendment_path = root / amendment_path
    payload = load_amendment(amendment_path)
    problems: list[str] = []

    for record in payload["protected_provenance"]:
        path = root / record["path"]
        if not path.is_file():
            problems.append(f"protected provenance disappeared: {record['path']}")
        elif path.stat().st_size != record["bytes"] or _sha256(path) != record["sha256"]:
            problems.append(f"protected provenance changed: {record['path']}")

    extended = 0
    for record in payload["protected_prediction_prefixes"]:
        path = root / record["path"]
        if not path.is_file():
            problems.append(f"protected prediction disappeared: {record['path']}")
            continue
        current_size = path.stat().st_size
        if current_size < record["bytes"]:
            problems.append(f"protected prediction was truncated: {record['path']}")
            continue
        if _sha256(path, byte_limit=record["bytes"]) != record["sha256"]:
            problems.append(f"protected prediction prefix changed: {record['path']}")
        if current_size > record["bytes"]:
            extended += 1

    if problems:
        raise ContinuationError("continuation integrity gate failed:\n- " + "\n- ".join(problems))
    return {
        "status": "PASS",
        "run_id": payload["run_id"],
        "protected_prediction_files": len(payload["protected_prediction_prefixes"]),
        "protected_prediction_lines": payload["snapshot_totals"]["lines"],
        "append_only_extended_files": extended,
        "protected_provenance_files": len(payload["protected_provenance"]),
    }


def snapshot_attempt(
    root: str | Path, amendment_path: str | Path, output: str | Path
) -> dict[str, Any]:
    """Protect every prediction present immediately before a continuation attempt."""
    root = Path(root).resolve()
    amendment_path = Path(amendment_path)
    if not amendment_path.is_absolute():
        amendment_path = root / amendment_path
    amendment = load_amendment(amendment_path)
    verify_amendment(root, amendment_path)
    verify_all_attempt_snapshots(root, amendment_path)
    prediction_root = root / "data" / "predictions" / amendment["run_id"]
    records = [_artifact_record(path, root) for path in sorted(prediction_root.glob("*.jsonl"))]
    payload = {
        "schema": ATTEMPT_SCHEMA,
        "status": "FROZEN_PRE_ATTEMPT_SNAPSHOT",
        "created_utc": _utc_now(),
        "run_id": amendment["run_id"],
        "amendment_path": _relative(amendment_path, root),
        "amendment_sha256": _sha256(amendment_path),
        "protected_prediction_prefixes": records,
        "snapshot_totals": {
            "files": len(records),
            "lines": sum(record.get("lines", 0) for record in records),
            "bytes": sum(record["bytes"] for record in records),
        },
    }
    output = Path(output)
    if not output.is_absolute():
        output = root / output
    _atomic_json(output, payload, exclusive=True)
    return payload


def verify_attempt_snapshot(root: str | Path, path: str | Path) -> dict[str, Any]:
    root = Path(root).resolve()
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise ContinuationError(f"continuation attempt snapshot not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != ATTEMPT_SCHEMA:
        raise ContinuationError("unsupported continuation attempt snapshot schema")
    amendment_path = root / payload["amendment_path"]
    if _sha256(amendment_path) != payload.get("amendment_sha256"):
        raise ContinuationError("attempt snapshot amendment hash mismatch")
    verify_amendment(root, amendment_path)

    problems: list[str] = []
    extended = 0
    for record in payload["protected_prediction_prefixes"]:
        prediction = root / record["path"]
        if not prediction.is_file():
            problems.append(f"attempt prediction disappeared: {record['path']}")
            continue
        if prediction.stat().st_size < record["bytes"]:
            problems.append(f"attempt prediction was truncated: {record['path']}")
            continue
        if _sha256(prediction, byte_limit=record["bytes"]) != record["sha256"]:
            problems.append(f"attempt prediction prefix changed: {record['path']}")
        if prediction.stat().st_size > record["bytes"]:
            extended += 1
    if problems:
        raise ContinuationError("attempt integrity gate failed:\n- " + "\n- ".join(problems))
    return {
        "status": "PASS",
        "run_id": payload["run_id"],
        "protected_prediction_files": len(payload["protected_prediction_prefixes"]),
        "protected_prediction_lines": payload["snapshot_totals"]["lines"],
        "append_only_extended_files": extended,
    }


def verify_all_attempt_snapshots(
    root: str | Path, amendment_path: str | Path
) -> dict[str, Any]:
    root = Path(root).resolve()
    amendment_path = Path(amendment_path)
    if not amendment_path.is_absolute():
        amendment_path = root / amendment_path
    amendment = load_amendment(amendment_path)
    attempt_root = amendment_path.parent / "attempts"
    snapshots = sorted(attempt_root.glob("*.json")) if attempt_root.exists() else []
    extended = 0
    for snapshot in snapshots:
        result = verify_attempt_snapshot(root, snapshot)
        extended += int(result["append_only_extended_files"])
    return {
        "status": "PASS",
        "run_id": amendment["run_id"],
        "attempt_snapshots": len(snapshots),
        "append_only_extended_files_across_snapshots": extended,
    }


def check_diagnostic_report(path: str | Path, max_api_error_rate: float) -> dict[str, Any]:
    """Keep validity failures nonfatal while preserving transport/integrity failures."""
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    totals = payload.get("totals", {})
    fatal: list[str] = []
    if totals.get("missing_dataset_items", 0):
        fatal.append(f"missing_dataset_items={totals['missing_dataset_items']}")
    if totals.get("duplicate_prediction_keys", 0):
        fatal.append(f"duplicate_prediction_keys={totals['duplicate_prediction_keys']}")
    api_rate = float(totals.get("api_error_rate", 0.0))
    if api_rate > max_api_error_rate + 1e-12:
        fatal.append(
            f"api_error_rate={api_rate:.6f} exceeds {max_api_error_rate:.6f}"
        )
    runner_errors = payload.get("runner_error_counts", {})
    if runner_errors and api_rate == 0.0:
        fatal.append(f"runner errors were recorded but API error rate is zero: {runner_errors}")
    if fatal:
        raise ContinuationError(
            f"fatal continuation diagnostic failure in {path}: " + "; ".join(fatal)
        )
    return {
        "status": payload.get("status"),
        "invalid_rate": float(totals.get("invalid_rate", 0.0)),
        "api_error_rate": api_rate,
        "nonfatal_gate_failures": payload.get("failures", []),
    }


def write_validity_summary(
    report_root: str | Path,
    output: str | Path,
    *,
    expected_reports: int,
    max_api_error_rate: float,
) -> dict[str, Any]:
    report_root = Path(report_root)
    reports = sorted(report_root.glob("diagnostics/*/*/response_validity.json"))
    reports += sorted(report_root.glob("diagnostics/*/*/repeats/response_validity.json"))
    if len(reports) != expected_reports:
        raise ContinuationError(
            f"diagnostic coverage failed: {len(reports)}/{expected_reports} reports"
        )
    failures = []
    total_rows = 0
    total_invalid = 0
    for path in reports:
        result = check_diagnostic_report(path, max_api_error_rate)
        payload = json.loads(path.read_text(encoding="utf-8"))
        totals = payload.get("totals", {})
        total_rows += int(totals.get("n", 0))
        total_invalid += sum(
            int(row.get("invalid", 0)) for row in payload.get("by_condition", [])
        )
        if result["status"] != "PASS":
            failures.append(
                {
                    "path": path.as_posix(),
                    "invalid_rate": result["invalid_rate"],
                    "failures": result["nonfatal_gate_failures"],
                }
            )
    summary = {
        "status": "POST_FAILURE_COLLECTION_COMPLETE",
        "classification": "post_failure_protocol_deviation",
        "original_gate_failure_retained": True,
        "preregistered_status": "FAILED_RESPONSE_VALIDITY_GATE",
        "diagnostic_reports": len(reports),
        "response_validity_gate_failures": failures,
        "all_api_error_gates_passed": True,
        "responses": total_rows,
        "invalid_responses": total_invalid,
        "invalid_response_policy": "retained_and_scored_incorrect",
        "manuscript_disclosure_required": True,
        "written_utc": _utc_now(),
    }
    _atomic_json(Path(output), summary)
    return summary


def record_model_artifact(
    original: str | Path,
    continuation: str | Path,
    model_id: str,
    sha256: str,
    artifact_path: str,
) -> str:
    """Verify an existing artifact identity or append a new continuation identity."""
    original = Path(original)
    continuation = Path(continuation)
    rows: dict[str, tuple[str, str]] = {}
    for source in (original, continuation):
        if not source.exists():
            continue
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3:
                raise ContinuationError(f"malformed model artifact row in {source}: {line!r}")
            previous = rows.get(parts[0])
            value = (parts[1], parts[2])
            if previous is not None and previous != value:
                raise ContinuationError(f"conflicting artifact identities for {parts[0]}")
            rows[parts[0]] = value
    if model_id in rows:
        existing_sha, _existing_path = rows[model_id]
        if existing_sha != sha256:
            raise ContinuationError(
                f"model artifact hash changed for {model_id}: {existing_sha} != {sha256}"
            )
        return "VERIFIED_EXISTING"
    continuation.parent.mkdir(parents=True, exist_ok=True)
    with continuation.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{model_id}\t{sha256}\t{artifact_path}\n")
        handle.flush()
        os.fsync(handle.fileno())
    return "RECORDED_NEW"


def merge_model_artifacts(
    original: str | Path, continuation: str | Path, output: str | Path
) -> int:
    rows: dict[str, str] = {}
    for source in (Path(original), Path(continuation)):
        if not source.exists():
            continue
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            model_id = line.split("\t", 1)[0]
            if model_id in rows and rows[model_id] != line:
                raise ContinuationError(f"conflicting artifact rows for {model_id}")
            rows[model_id] = line
    Path(output).write_text(
        "".join(f"{line}\n" for line in rows.values()), encoding="utf-8"
    )
    return len(rows)
