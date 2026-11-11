from __future__ import annotations

import json
from pathlib import Path

import pytest

from owl_equivariance.continuation import (
    ContinuationError,
    check_diagnostic_report,
    prepare_amendment,
    record_model_artifact,
    snapshot_attempt,
    verify_amendment,
    verify_all_attempt_snapshots,
    verify_attempt_snapshot,
)


RUN_ID = "owleq-jws-2026-08-v33-confirmatory-01"
PROTOCOL_ID = "owleq-jws-2026-08-v33"


def _failed_run(tmp_path: Path) -> tuple[Path, Path]:
    report = tmp_path / "reports" / RUN_ID
    provenance = report / "provenance"
    predictions = tmp_path / "data" / "predictions" / RUN_ID
    provenance.mkdir(parents=True)
    predictions.mkdir(parents=True)
    (report / "RUN_FAILED.txt").write_text(
        "status=FAILED\nline=730\nexit_status=1\nutc=2026-09-04T14:11:01Z\n",
        encoding="utf-8",
    )
    (provenance / "run_parameters.json").write_text(
        json.dumps(
            {
                "protocol_id": PROTOCOL_ID,
                "run_id": RUN_ID,
                "stage": "confirmatory",
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "experiment_manifest.yaml",
        "datasets.txt",
        "confirmatory_panel.json",
        "model_matrix.txt",
        "dataset_sha256.txt",
        "model_artifacts.tsv",
        "model_runtime.tsv",
    ):
        (provenance / name).write_text(f"frozen {name}\n", encoding="utf-8")
    prediction = predictions / "eco_.model.primary.jsonl"
    prediction.write_text('{"orbit_item_id":"one"}\n', encoding="utf-8")
    return report, prediction


def test_amendment_allows_only_append_after_protected_prediction_prefix(tmp_path):
    report, prediction = _failed_run(tmp_path)
    amendment = report / "provenance" / "post_failure" / "continuation_amendment.json"
    prepared = prepare_amendment(tmp_path, RUN_ID, amendment)

    assert prepared["classification"] == "post_failure_protocol_deviation"
    assert prepared["policy"]["completed_item_repeat_retry_prohibited"] is True
    assert verify_amendment(tmp_path, amendment)["append_only_extended_files"] == 0

    with prediction.open("a", encoding="utf-8") as handle:
        handle.write('{"orbit_item_id":"two"}\n')
    assert verify_amendment(tmp_path, amendment)["append_only_extended_files"] == 1

    content = prediction.read_bytes()
    prediction.write_bytes(b"X" + content[1:])
    with pytest.raises(ContinuationError, match="prefix changed"):
        verify_amendment(tmp_path, amendment)


def test_amendment_refuses_changed_historical_provenance_and_overwrite(tmp_path):
    report, _prediction = _failed_run(tmp_path)
    amendment = report / "provenance" / "post_failure" / "continuation_amendment.json"
    prepare_amendment(tmp_path, RUN_ID, amendment)
    with pytest.raises(ContinuationError, match="overwrite frozen amendment"):
        prepare_amendment(tmp_path, RUN_ID, amendment)

    (report / "RUN_FAILED.txt").write_text("replaced\n", encoding="utf-8")
    with pytest.raises(ContinuationError, match="protected provenance changed"):
        verify_amendment(tmp_path, amendment)


def test_each_continuation_attempt_protects_predictions_created_after_amendment(tmp_path):
    report, _prediction = _failed_run(tmp_path)
    amendment = report / "provenance" / "post_failure" / "continuation_amendment.json"
    prepare_amendment(tmp_path, RUN_ID, amendment)
    later = tmp_path / "data" / "predictions" / RUN_ID / "later.primary.jsonl"
    later.write_text('{"orbit_item_id":"new"}\n', encoding="utf-8")
    attempt = report / "provenance" / "post_failure" / "attempts" / "one.json"
    snapshot_attempt(tmp_path, amendment, attempt)
    assert verify_attempt_snapshot(tmp_path, attempt)["protected_prediction_files"] == 2
    assert verify_all_attempt_snapshots(tmp_path, amendment)["attempt_snapshots"] == 1

    content = later.read_bytes()
    later.write_bytes(b"X" + content[1:])
    with pytest.raises(ContinuationError, match="attempt prediction prefix changed"):
        verify_attempt_snapshot(tmp_path, attempt)
    with pytest.raises(ContinuationError, match="attempt prediction prefix changed"):
        verify_all_attempt_snapshots(tmp_path, amendment)


def test_diagnostic_response_threshold_is_nonfatal_but_api_errors_are_fatal(tmp_path):
    report = tmp_path / "response_validity.json"
    report.write_text(
        json.dumps(
            {
                "status": "FAIL",
                "totals": {
                    "invalid_rate": 0.025,
                    "api_error_rate": 0.0,
                    "missing_dataset_items": 0,
                    "duplicate_prediction_keys": 0,
                },
                "runner_error_counts": {},
                "failures": ["C0 invalid-response rate 2.50% exceeds 2.00%"],
            }
        ),
        encoding="utf-8",
    )
    result = check_diagnostic_report(report, 0.0)
    assert result["status"] == "FAIL"
    assert result["nonfatal_gate_failures"]

    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["totals"]["api_error_rate"] = 0.01
    payload["runner_error_counts"] = {"connection error": 1}
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ContinuationError, match="api_error_rate"):
        check_diagnostic_report(report, 0.0)


def test_model_artifact_identity_is_append_only_and_hash_checked(tmp_path):
    original = tmp_path / "original.tsv"
    continuation = tmp_path / "continuation.tsv"
    original.write_text("model-a\taaaa\t/path/a\n", encoding="utf-8")

    assert (
        record_model_artifact(original, continuation, "model-a", "aaaa", "/new/path/a")
        == "VERIFIED_EXISTING"
    )
    assert not continuation.exists()
    assert (
        record_model_artifact(original, continuation, "model-b", "bbbb", "/path/b")
        == "RECORDED_NEW"
    )
    assert continuation.read_text(encoding="utf-8").startswith("model-b\tbbbb\t")
    with pytest.raises(ContinuationError, match="hash changed"):
        record_model_artifact(original, continuation, "model-a", "xxxx", "/path/a")
