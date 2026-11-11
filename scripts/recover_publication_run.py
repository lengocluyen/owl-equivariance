#!/usr/bin/env python3
"""Verify and recover a failed publication run without performing inference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from owl_equivariance.recovery import (
    RecoveryError,
    finalize_recovered_run,
    generate_missing_derived_outputs,
    load_frozen_run,
    rebuild_or_verify_analysis,
    verify_checksums,
    verify_prediction_artifacts,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Recover pooled analyses, power reports, and immutable finalization from a "
            "completed inference run. This command never contacts LM Studio."
        )
    )
    result.add_argument("--run-id", required=True)
    result.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root (defaults to the parent of scripts/).",
    )
    result.add_argument("--report-root", default="")
    result.add_argument("--prediction-root", default="")
    result.add_argument(
        "--planned-pairs",
        type=int,
        default=None,
        help="Override the frozen manifest target (normally omit this option).",
    )
    result.add_argument("--simulations", type=int, default=10000)
    result.add_argument(
        "--finalize",
        action="store_true",
        help=(
            "Generate derived artifacts and RUN_COMPLETE.json. Without this flag the "
            "command performs a read-only prediction-completeness check."
        ),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if (args.planned_pairs is not None and args.planned_pairs < 1) or args.simulations < 1:
        print("--planned-pairs, when supplied, and --simulations must be positive", file=sys.stderr)
        return 2
    try:
        run = load_frozen_run(
            args.repo_root,
            args.run_id,
            report_root=args.report_root or None,
            prediction_root=args.prediction_root or None,
        )
        complete = run.report_root / "RUN_COMPLETE.json"
        checksums = run.report_root / "SHA256SUMS"
        if complete.exists() and checksums.exists():
            verify_checksums(run)
            print(f"PASS: {run.run_id} is already complete and all checksums verify")
            return 0

        verification, primary_paths = verify_prediction_artifacts(run)
        print(json.dumps(verification, indent=2, sort_keys=True))
        if not args.finalize:
            print("CHECK ONLY: no files were changed; add --finalize after reviewing this PASS")
            return 0

        analysis_csv = rebuild_or_verify_analysis(run, primary_paths)
        derived = generate_missing_derived_outputs(
            run,
            analysis_csv,
            primary_paths,
            planned_pairs=args.planned_pairs,
            simulations=args.simulations,
        )
        completion = finalize_recovered_run(run, verification, derived)
        print(json.dumps(completion, indent=2, sort_keys=True))
        print(f"PASS: recovered publication run {run.run_id} without inference")
        print(f"reports:   {run.report_root}")
        print(f"checksums: {run.report_root / 'SHA256SUMS'}")
        return 0
    except RecoveryError as exc:
        print(f"RECOVERY REFUSED: {exc}", file=sys.stderr)
        print("No inference retry was attempted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
