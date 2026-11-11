#!/usr/bin/env bash
# Explicit post-failure collection path for the frozen v3.3 confirmatory run.
#
# This does not erase or reverse the original response-validity gate failure.  It
# preserves all existing response bytes and labels the completed collection as a
# post-failure protocol deviation.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 2

MODE="${1:-check}"
RUN_ID="${RUN_ID:-owleq-jws-2026-08-v33-confirmatory-01}"
PROTOCOL_ID="owleq-jws-2026-08-v33"
REPORT_ROOT="reports/$RUN_ID"
AMENDMENT="$REPORT_ROOT/provenance/post_failure/continuation_amendment.json"

if [[ -f .owleq-toolchain.env ]]; then
  # shellcheck disable=SC1091
  source .owleq-toolchain.env
fi
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
LOCAL_R_BIN="$REPO_ROOT/.tools/r-v33/bin"
if [[ -x "$LOCAL_R_BIN/Rscript" ]]; then
  export PATH="$LOCAL_R_BIN:$PATH"
fi
PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || {
  echo "REFUSED: expected Python environment is missing: $PY" >&2
  exit 2
}
# Prefer this checkout over any stale non-editable package installed in the venv.
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

case "$MODE" in
  prepare)
    "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" prepare \
      --run-id "$RUN_ID" \
      --protocol-id "$PROTOCOL_ID" \
      --amendment "$AMENDMENT"
    rc=$?
    if [[ "$rc" -eq 0 ]]; then
      echo "FROZEN: review $AMENDMENT before running inference."
    fi
    ;;
  check)
    "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" check \
      --amendment "$AMENDMENT" && \
    "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" \
      check-all-attempts --amendment "$AMENDMENT"
    rc=$?
    ;;
  run)
    if [[ "${CONTINUATION_APPROVED:-NO}" != "YES" ]]; then
      echo "REFUSED: review the amendment, then set CONTINUATION_APPROVED=YES." >&2
      rc=2
    elif ! command -v Rscript >/dev/null 2>&1; then
      echo "REFUSED: Rscript is unavailable; expected $LOCAL_R_BIN/Rscript." >&2
      rc=2
    elif ! Rscript -e \
      'if (!requireNamespace("lme4", quietly=TRUE)) quit(status=2)' \
      >/dev/null 2>&1; then
      echo "REFUSED: R is available but the required lme4 package is not." >&2
      rc=2
    elif [[ -f "$REPORT_ROOT/RUN_COMPLETE.json" || \
            -f "$REPORT_ROOT/POST_FAILURE_CONTINUATION_COMPLETE.json" ]]; then
      echo "REFUSED: a completion artifact already exists for $RUN_ID." >&2
      rc=2
    elif ! "$PY" scripts/manage_post_failure_continuation.py \
      --root "$REPO_ROOT" check --amendment "$AMENDMENT"; then
      echo "REFUSED: protected failed-run state did not pass verification." >&2
      rc=2
    elif ! "$PY" scripts/manage_post_failure_continuation.py \
      --root "$REPO_ROOT" check-all-attempts --amendment "$AMENDMENT"; then
      echo "REFUSED: an earlier continuation attempt failed verification." >&2
      rc=2
    else
      attempt_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
      attempt_snapshot="$REPORT_ROOT/provenance/post_failure/attempts/$attempt_id.json"
      if ! "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" \
        snapshot-attempt --amendment "$AMENDMENT" --output "$attempt_snapshot"; then
        echo "REFUSED: could not freeze the pre-attempt prediction state." >&2
        echo "Post-failure continuation '$MODE' finished with exit code: 2"
        echo "The parent tmux shell remains open."
        exit 2
      fi
      DATASETS_CSV="$(paste -sd, "$REPORT_ROOT/provenance/datasets.txt")"
      export DATASETS_CSV
      export PY
      export RUN_ID PROTOCOL_ID
      export MANIFEST="configs/open_weight_experiment_v33.yaml"
      export MODEL_MATRIX_FILE="configs/lmstudio_models_v33.tsv"
      export CONFIRMATORY_PANEL_FILE="$REPORT_ROOT/provenance/confirmatory_panel.json"
      export CONFIRMATORY_APPROVED=YES
      export POST_FAILURE_CONTINUATION=1
      export CONTINUATION_AMENDMENT="$AMENDMENT"
      export CONTINUATION_ATTEMPT_SNAPSHOT="$attempt_snapshot"
      bash scripts/run_lmstudio_publication.sh confirmatory
      rc=$?
    fi
    ;;
  *)
    echo "Usage: RUN_ID=<failed-run-id> $0 {prepare|check|run}" >&2
    rc=2
    ;;
esac

echo "Post-failure continuation '$MODE' finished with exit code: $rc"
echo "The parent tmux shell remains open."
exit "$rc"
