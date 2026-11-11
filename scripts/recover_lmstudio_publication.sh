#!/usr/bin/env bash
# Recover only post-processing for a completed LM Studio publication run.
# This script contains no `lms`, API, or inference command.
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:-check}"
RUN_ID="${RUN_ID:-}"
[[ -n "$RUN_ID" ]] || {
  echo "Set RUN_ID to the failed discovery/confirmatory run identifier." >&2
  exit 2
}

PY="${PY:-python3}"
[[ -x .venv/bin/python ]] && PY=.venv/bin/python
[[ -x .venv/Scripts/python.exe ]] && PY=.venv/Scripts/python.exe

ARGS=(
  --run-id "$RUN_ID"
  --simulations "${POWER_SIMULATIONS:-10000}"
)
[[ -n "${PLANNED_PAIRS:-}" ]] && ARGS+=(--planned-pairs "$PLANNED_PAIRS")
[[ -n "${REPORT_ROOT:-}" ]] && ARGS+=(--report-root "$REPORT_ROOT")
[[ -n "${PREDICTION_ROOT:-}" ]] && ARGS+=(--prediction-root "$PREDICTION_ROOT")

case "$MODE" in
  check)
    exec "$PY" scripts/recover_publication_run.py "${ARGS[@]}"
    ;;
  finalize)
    [[ "${RECOVERY_APPROVED:-NO}" == "YES" ]] || {
      echo "Refusing writes: set RECOVERY_APPROVED=YES after the check mode passes." >&2
      exit 2
    }
    exec "$PY" scripts/recover_publication_run.py "${ARGS[@]}" --finalize
    ;;
  *)
    echo "Usage: RUN_ID=<failed-run> $0 {check|finalize}" >&2
    exit 2
    ;;
esac
