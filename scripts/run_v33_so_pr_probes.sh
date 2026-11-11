#!/usr/bin/env bash
# Acquire immutable Sequence Ontology (SO) and asserted Protein Ontology (PR)
# releases, then run only the frozen owl-certifier 0.2.0 capacity probes.
#
# This is pre-confirmatory source screening. It never starts a full dataset
# build and never calls an LLM. Run this file; do not source it:
#
#   bash scripts/run_v33_so_pr_probes.sh

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "refusing to run while sourced; use: bash scripts/run_v33_so_pr_probes.sh" >&2
  return 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "missing Linux virtual environment: $REPO_ROOT/.venv/bin/activate" >&2
  exit 1
fi

if [[ -f .owleq-toolchain.env ]]; then
  # shellcheck disable=SC1091
  source .owleq-toolchain.env
else
  echo "missing frozen toolchain file: $REPO_ROOT/.owleq-toolchain.env" >&2
  exit 1
fi

PY=python
[[ -x .venv/bin/python ]] && PY=.venv/bin/python

EXPECTED_JAR_SHA="9faa87c5de3184884f07feccc1da63f74185356510fbae6d4969c2a92b6f9efe"
SO_COMMIT="4340c143bac3578bba0c013d02e8c5f0e51ad14a"
SO_URL="https://raw.githubusercontent.com/The-Sequence-Ontology/SO-Ontologies/${SO_COMMIT}/Ontology_Files/so.owl"
SO_FILE="data/raw/so-v2026-08-07.owl"
SO_MARKER="http://purl.obolibrary.org/obo/so/2026-08-07/so.owl"
PR_URL="https://purl.obolibrary.org/obo/pr/73.0/pr-asserted.owl"
PR_FILE="data/raw/pr-asserted-v73.0.owl"
PR_MARKER="http://purl.obolibrary.org/obo/pr/73.0/pr-asserted.owl"
SUMMARIES=()
FAILED=0

JAVA_OPTIONS_COMBINED="${JAVA_TOOL_OPTIONS:-} ${JDK_JAVA_OPTIONS:-} ${_JAVA_OPTIONS:-}"
if [[ "$JAVA_OPTIONS_COMBINED" == *"jdk.xml."* ]]; then
  echo "refusing to inherit ChEBI-specific XML parser settings" >&2
  echo "unset JAVA_TOOL_OPTIONS JDK_JAVA_OPTIONS _JAVA_OPTIONS, then run again" >&2
  exit 1
fi

command -v curl >/dev/null 2>&1 || {
  echo "curl is required to acquire the pinned ontology releases" >&2
  exit 1
}

verify_frozen_certifier() {
  local jar="java/owl-certifier/target/owl-certifier.jar"

  [[ -s "$jar" ]] || {
    echo "frozen certifier JAR is missing: $jar" >&2
    return 1
  }

  printf '%s  %s\n' "$EXPECTED_JAR_SHA" "$jar" | sha256sum -c -
}

contains_marker() {
  local path="$1"
  local marker="$2"

  "$PY" - "$path" "$marker" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
needle = sys.argv[2].encode("utf-8")
overlap = b""

with path.open("rb") as handle:
    while chunk := handle.read(4 * 1024 * 1024):
        block = overlap + chunk
        if needle in block:
            raise SystemExit(0)
        overlap = block[-max(len(needle) - 1, 0):]

raise SystemExit(1)
PY
}

acquire_source() {
  local ontology_id="$1"
  local url="$2"
  local destination="$3"
  local marker="$4"
  local partial="${destination}.part"
  local sha_file="${destination}.sha256"
  local url_file="${destination}.source-url.txt"

  echo
  echo "============================================================"
  echo "SOURCE: $ontology_id"
  echo "URL:    $url"
  echo "FILE:   $destination"
  echo "============================================================"

  mkdir -p "$(dirname "$destination")"

  if [[ -e "$destination" && ! -s "$destination" ]]; then
    echo "refusing empty existing source file: $destination" >&2
    return 1
  fi

  if [[ -s "$destination" ]]; then
    echo "using existing pinned source"
  else
    echo "downloading pinned source (a partial download is resumable)"
    if ! curl \
      --fail \
      --location \
      --retry 5 \
      --retry-all-errors \
      --continue-at - \
      --output "$partial" \
      "$url"; then
      echo "source download failed; resumable partial retained at $partial" >&2
      return 1
    fi

    if ! contains_marker "$partial" "$marker"; then
      echo "downloaded source does not contain its frozen version IRI: $marker" >&2
      return 1
    fi

    mv "$partial" "$destination"
  fi

  if ! contains_marker "$destination" "$marker"; then
    echo "source version marker verification failed: $destination" >&2
    return 1
  fi

  if [[ -s "$url_file" ]] && [[ "$(tr -d '\r\n' < "$url_file")" != "$url" ]]; then
    echo "refusing conflicting source provenance in $url_file" >&2
    return 1
  fi

  printf '%s\n' "$url" > "$url_file"

  if [[ -s "$sha_file" ]]; then
    sha256sum -c "$sha_file" || return 1
  else
    sha256sum "$destination" > "$sha_file"
  fi

  echo "PASS: pinned source acquired and verified"
}

validate_probe() {
  local root="$1"
  local source_file="$2"

  "$PY" -m owl_equivariance.cli validate \
    --dataset "$root/benchmark.jsonl" \
    --expect-conditions C0 || return 1

  "$PY" - "$root" "$source_file" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
source = Path(sys.argv[2])
checkpoint = json.loads(
    (root / "build_checkpoint.json").read_text(encoding="utf-8")
)
report = json.loads(
    (root / "build_report.json").read_text(encoding="utf-8")
)
exit_code = (root / "runner_exit_code.txt").read_text(encoding="utf-8").strip()

source_hash = hashlib.sha256()
with source.open("rb") as handle:
    while chunk := handle.read(4 * 1024 * 1024):
        source_hash.update(chunk)

assert checkpoint["status"] == "COMPLETE"
assert exit_code == "0"
assert report["certifier_version"] == "0.2.0"
assert report["conditions"] == ["C0"]
assert report["base_items"] >= 6
assert report["emitted"] == report["base_items"]
assert report["source_file_sha256"] == source_hash.hexdigest()
assert report["justification_budget_exhausted_candidates"] == 0
assert report["dropped_unverified"] == 0
assert report["dropped_uncertified"] == 0
assert report["dropped_empty_context"] == 0
assert not report["failures"]

print("PROBE_STATUS=PASS")
print(f"base_items={report['base_items']}")
print(f"inferred_candidates={report['inferred_candidates_enumerated']}")
print(f"candidate_pool={report['bounded_candidate_pool_size']}")
print(f"reasoner_calls={report['justification_reasoner_calls']}")
print(f"budget_exhausted={report['justification_budget_exhausted_candidates']}")
PY
}

run_probe() {
  local ontology_id="$1"
  local ontology_file="$2"
  local ontology_version="$3"
  local run_id="$4"
  local root="results/v33_capacity_probes/$run_id/$ontology_id"
  local log="reports/v33/${run_id}.log"
  local build_rc

  echo
  echo "============================================================"
  echo "CAPACITY PROBE: $ontology_id - $ontology_version"
  echo "============================================================"

  if pgrep -af "[j]ava.*owl-certifier.*--ontology-id[ =]$ontology_id" >/dev/null; then
    echo "refusing to start: an $ontology_id certifier process is already running" >&2
    SUMMARIES+=("$ontology_id: PROCESS_ALREADY_RUNNING")
    return 1
  fi

  if [[ -s "$root/build_checkpoint.json" ]] &&
     "$PY" - "$root/build_checkpoint.json" <<'PY'
import json
import sys

checkpoint = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if checkpoint.get("status") == "COMPLETE" else 1)
PY
  then
    echo "existing complete probe found; validating without rebuilding"
    if validate_probe "$root" "$ontology_file"; then
      SUMMARIES+=("$ontology_id: EXISTING_PASS")
      return 0
    fi
    SUMMARIES+=("$ontology_id: EXISTING_INVALID")
    return 1
  fi

  if [[ -d "$root" ]] && find "$root" -mindepth 1 -print -quit | grep -q .; then
    echo "refusing to overwrite incomplete probe artifacts: $root" >&2
    SUMMARIES+=("$ontology_id: BLOCKED_EXISTING_ARTIFACTS")
    return 1
  fi

  if [[ -e "$log" ]]; then
    echo "refusing to overwrite existing log: $log" >&2
    SUMMARIES+=("$ontology_id: BLOCKED_EXISTING_LOG")
    return 1
  fi

  ONTOLOGY_ID="$ontology_id" \
  ONTOLOGY_FILE="$ontology_file" \
  ONTOLOGY_VERSION="$ontology_version" \
  RUN_ID="$run_id" \
    bash scripts/build_v33_candidate.sh probe \
    2>&1 | tee "$log"

  build_rc="${PIPESTATUS[0]}"
  if [[ "$build_rc" -ne 0 ]]; then
    echo "$ontology_id probe failed with exit code $build_rc" >&2
    SUMMARIES+=("$ontology_id: FAILED_RC_$build_rc")
    return 1
  fi

  if validate_probe "$root" "$ontology_file"; then
    SUMMARIES+=("$ontology_id: PASS")
    return 0
  fi

  SUMMARIES+=("$ontology_id: FINAL_VALIDATION_FAILED")
  return 1
}

mkdir -p reports/v33

if ! verify_frozen_certifier; then
  echo "probe launcher refused: frozen certifier verification failed" >&2
  exit 1
fi

if command -v lms >/dev/null 2>&1; then
  lms unload --all || true
fi

SO_READY=0
PR_READY=0
acquire_source so "$SO_URL" "$SO_FILE" "$SO_MARKER" && SO_READY=1 || {
  SUMMARIES+=("so: SOURCE_ACQUISITION_FAILED")
  FAILED=1
}
acquire_source pr "$PR_URL" "$PR_FILE" "$PR_MARKER" && PR_READY=1 || {
  SUMMARIES+=("pr: SOURCE_ACQUISITION_FAILED")
  FAILED=1
}

if [[ "$SO_READY" -eq 1 ]]; then
  run_probe so "$SO_FILE" so-v2026-08-07 so-v020-probe-01 || FAILED=1
fi

if [[ "$PR_READY" -eq 1 ]]; then
  run_probe pr "$PR_FILE" pr-asserted-v73.0 pr-v020-probe-01 || FAILED=1
fi

echo
echo "================ CAPACITY-PROBE SUMMARY ================"
printf '%s\n' "${SUMMARIES[@]}"
echo "========================================================"
echo "No full dataset build or LLM inference was started."

exit "$FAILED"
