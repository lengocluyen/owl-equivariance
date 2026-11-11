#!/usr/bin/env bash
# Deterministic, no-LLM v3.3 source probe/full build using owl-certifier 0.2.0.
#
# Probe example:
#   ONTOLOGY_ID=uberon \
#   ONTOLOGY_FILE=data/raw/uberon-v2026-06-23.owl \
#   ONTOLOGY_VERSION=uberon-v2026-06-23 \
#   RUN_ID=uberon-probe-01 \
#     bash scripts/build_v33_candidate.sh probe
#
# Full build (only after the probe is reviewed):
#   V33_BUILD_APPROVED=YES ONTOLOGY_ID=uberon \
#   ONTOLOGY_FILE=data/raw/uberon-v2026-06-23.owl \
#   ONTOLOGY_VERSION=uberon-v2026-06-23 \
#   RUN_ID=uberon-full-01 \
#     bash scripts/build_v33_candidate.sh full
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="${1:-probe}"
[[ "$MODE" == "probe" || "$MODE" == "full" ]] || {
  echo "usage: build_v33_candidate.sh probe|full" >&2
  exit 2
}

: "${ONTOLOGY_ID:?set ONTOLOGY_ID}"
: "${ONTOLOGY_FILE:?set ONTOLOGY_FILE to a pinned local source}"
: "${ONTOLOGY_VERSION:?set ONTOLOGY_VERSION to the pinned release}"
: "${RUN_ID:?set a unique RUN_ID}"

[[ -s "$ONTOLOGY_FILE" ]] || {
  echo "source ontology not found or empty: $ONTOLOGY_FILE" >&2
  exit 2
}

if [[ "$MODE" == "probe" ]]; then
  OUTPUT_ROOT="results/v33_capacity_probes/$RUN_ID/$ONTOLOGY_ID"
  POSITIVES=4
  NEGATIVES=4
  CONDITIONS="C0"
else
  [[ "${V33_BUILD_APPROVED:-NO}" == "YES" ]] || {
    echo "full build refused: set V33_BUILD_APPROVED=YES after reviewing the probe" >&2
    exit 2
  }
  OUTPUT_ROOT="data/certified_v33/$ONTOLOGY_ID"
  POSITIVES=100
  NEGATIVES=100
  CONDITIONS="C0,C1,C2,C3,C4,C4S2,C5,C6,C7,C8,C9"
fi

if [[ -e "$OUTPUT_ROOT" ]] && find "$OUTPUT_ROOT" -mindepth 1 -print -quit | grep -q .; then
  echo "refusing to overwrite existing attempt artifacts: $OUTPUT_ROOT" >&2
  exit 2
fi
mkdir -p "$OUTPUT_ROOT/mappings"

PY=python
[[ -x .venv/bin/python ]] && PY=.venv/bin/python
[[ -x .venv/Scripts/python.exe ]] && PY=.venv/Scripts/python.exe

CHECKPOINT="$OUTPUT_ROOT/build_checkpoint.json"
DATASET="$OUTPUT_ROOT/benchmark.jsonl"
REPORT="$OUTPUT_ROOT/build_report.json"
EXIT_RECORD="$OUTPUT_ROOT/runner_exit_code.txt"

record_exit() {
  local rc=$?
  printf '%s\n' "$rc" > "$EXIT_RECORD"
  printf 'runner_finished_at=%s exit_code=%s\n' "$(date -Is)" "$rc"
}
trap record_exit EXIT

if [[ ! -f java/owl-certifier/target/owl-certifier.jar ]]; then
  bash scripts/build_java.sh -q package
fi

{
  printf 'protocol_id=owleq-jws-2026-08-v33\n'
  printf 'certifier_version=0.2.0\n'
  printf 'mode=%s\n' "$MODE"
  printf 'run_id=%s\n' "$RUN_ID"
  printf 'ontology_id=%s\n' "$ONTOLOGY_ID"
  printf 'ontology_version=%s\n' "$ONTOLOGY_VERSION"
  printf 'ontology_file=%s\n' "$ONTOLOGY_FILE"
  printf 'conditions=%s\n' "$CONDITIONS"
  printf 'positives=%s\n' "$POSITIVES"
  printf 'negatives=%s\n' "$NEGATIVES"
  printf 'justification_algorithm=QUICKXPLAIN\n'
  printf 'justification_call_budget=256\n'
  printf 'candidate_sampling=SEEDED_SHA256_BOTTOM_K\n'
  printf 'started_at=%s\n' "$(date -Is)"
} > "$OUTPUT_ROOT/run_parameters.txt"
sha256sum "$ONTOLOGY_FILE" > "$OUTPUT_ROOT/source.sha256"
sha256sum java/owl-certifier/target/owl-certifier.jar > "$OUTPUT_ROOT/certifier_jar.sha256"

EL_FLAGS=()
[[ "${EL_FRAGMENT:-1}" == "1" ]] && EL_FLAGS=(--el-fragment)

TIMEFORMAT=$'elapsed_seconds=%R\nuser_seconds=%U\nsystem_seconds=%S'
time bash scripts/certifier.sh build-dataset \
  --input "$ONTOLOGY_FILE" \
  --root-only "${EL_FLAGS[@]}" \
  --ontology-id "$ONTOLOGY_ID" \
  --ontology-version "$ONTOLOGY_VERSION" \
  --output "$DATASET" \
  --report "$REPORT" \
  --checkpoint "$CHECKPOINT" \
  --mappings-dir "$OUTPUT_ROOT/mappings" \
  --positives "$POSITIVES" \
  --negatives "$NEGATIVES" \
  --distractors 12 \
  --max-context-axioms 45 \
  --justification-call-budget 256 \
  --seed 42 \
  --conditions "$CONDITIONS"

"$PY" -m owl_equivariance.cli validate \
  --dataset "$DATASET" \
  --expect-conditions "$CONDITIONS"

if [[ "$MODE" == "full" ]]; then
  "$PY" - "$DATASET" <<'PY'
import json
import sys
from collections import defaultdict
from pathlib import Path

path = Path(sys.argv[1])
expected = {"C0", "C1", "C2", "C3", "C4", "C4S2",
            "C5", "C6", "C7", "C8", "C9"}
orbits = defaultdict(set)
for line in path.read_text(encoding="utf-8").splitlines():
    if line.strip():
        row = json.loads(line)
        orbits[row["base_item_id"]].add(row["transform"]["lexical_condition"])
complete = sum(conditions == expected for conditions in orbits.values())
eligible = len(orbits) >= 150 and complete == len(orbits)
print(f"base_items={len(orbits)}")
print(f"complete_orbits={complete}/{len(orbits)}")
print(f"V3.3_ELIGIBLE={eligible}")
if not eligible:
    raise SystemExit(2)
PY
fi

echo "PASS: $MODE build completed and validated at $OUTPUT_ROOT"
