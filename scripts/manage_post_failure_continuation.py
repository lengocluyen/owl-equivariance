#!/usr/bin/env python3
"""Create and enforce the v3.3 post-failure continuation amendment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Always use the module from the same repository checkout as this script.  A server may
# have a non-editable, older owl-equivariance wheel in its virtual environment.
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from owl_equivariance.continuation import (
    ContinuationError,
    check_diagnostic_report,
    merge_model_artifacts,
    prepare_amendment,
    record_model_artifact,
    snapshot_attempt,
    verify_amendment,
    verify_all_attempt_snapshots,
    verify_attempt_snapshot,
    write_validity_summary,
)


def _print(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(REPO_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--protocol-id", required=True)
    prepare.add_argument("--amendment", required=True)

    check = sub.add_parser("check")
    check.add_argument("--amendment", required=True)

    attempt = sub.add_parser("snapshot-attempt")
    attempt.add_argument("--amendment", required=True)
    attempt.add_argument("--output", required=True)

    check_attempt = sub.add_parser("check-attempt")
    check_attempt.add_argument("--snapshot", required=True)

    check_attempts = sub.add_parser("check-all-attempts")
    check_attempts.add_argument("--amendment", required=True)

    diagnostic = sub.add_parser("diagnostic-check")
    diagnostic.add_argument("--report", required=True)
    diagnostic.add_argument("--max-api-error-rate", type=float, required=True)

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--amendment", required=True)
    finalize.add_argument("--report-root", required=True)
    finalize.add_argument("--output", required=True)
    finalize.add_argument("--expected-reports", type=int, required=True)
    finalize.add_argument("--max-api-error-rate", type=float, required=True)

    record = sub.add_parser("record-model-artifact")
    record.add_argument("--original", required=True)
    record.add_argument("--continuation", required=True)
    record.add_argument("--model-id", required=True)
    record.add_argument("--sha256", required=True)
    record.add_argument("--path", required=True)

    merge = sub.add_parser("merge-model-artifacts")
    merge.add_argument("--original", required=True)
    merge.add_argument("--continuation", required=True)
    merge.add_argument("--output", required=True)

    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "prepare":
            payload = prepare_amendment(
                root, args.run_id, args.amendment, protocol_id=args.protocol_id
            )
            _print({"status": "FROZEN", **payload["snapshot_totals"]})
        elif args.command == "check":
            _print(verify_amendment(root, args.amendment))
        elif args.command == "snapshot-attempt":
            payload = snapshot_attempt(root, args.amendment, args.output)
            _print({"status": "FROZEN", **payload["snapshot_totals"]})
        elif args.command == "check-attempt":
            _print(verify_attempt_snapshot(root, args.snapshot))
        elif args.command == "check-all-attempts":
            _print(verify_all_attempt_snapshots(root, args.amendment))
        elif args.command == "diagnostic-check":
            _print(check_diagnostic_report(args.report, args.max_api_error_rate))
        elif args.command == "finalize":
            integrity = verify_amendment(root, args.amendment)
            summary = write_validity_summary(
                args.report_root,
                args.output,
                expected_reports=args.expected_reports,
                max_api_error_rate=args.max_api_error_rate,
            )
            _print({"integrity": integrity, "validity": summary})
        elif args.command == "record-model-artifact":
            status = record_model_artifact(
                args.original,
                args.continuation,
                args.model_id,
                args.sha256,
                args.path,
            )
            _print({"status": status, "model_id": args.model_id})
        elif args.command == "merge-model-artifacts":
            count = merge_model_artifacts(args.original, args.continuation, args.output)
            _print({"status": "PASS", "models": count, "output": args.output})
    except (ContinuationError, FileNotFoundError, json.JSONDecodeError) as exc:
        parser.exit(2, f"CONTINUATION REFUSED: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
