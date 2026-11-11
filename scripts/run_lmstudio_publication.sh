#!/usr/bin/env bash
# Run the six-model open-weight OWL-equivariance panel through LM Studio.
#
# Quick server wiring check:
#   bash scripts/run_lmstudio_publication.sh smoke
#
# Required response-channel survey before the next full experiment:
#   bash scripts/run_lmstudio_publication.sh diagnostic
#
# Full discovery run over the currently certified CL and PO datasets:
#   DIAGNOSTIC_APPROVED=YES DIAGNOSTIC_RUN_DIR=reports/<passing-diagnostic-run> \
#   RUN_ID=owleq-jws-2026-07-v2-discovery \
#     bash scripts/run_lmstudio_publication.sh discovery
#
# Confirmatory execution is deliberately gated. V3.3 requires an independently frozen
# panel artifact as well as the exact ordered dataset list:
#   DATASETS_CSV=data/certified/a/benchmark.jsonl,... \
#   CONFIRMATORY_PANEL_FILE=configs/confirmatory_panel_v33.json \
#   CONFIRMATORY_APPROVED=YES RUN_ID=owleq-confirmatory-v33-01 \
#     bash scripts/run_lmstudio_publication.sh confirmatory
#
# The script never downloads a model, silently truncates a dataset, retries a failed request,
# or replaces an existing dataset. Rerunning the same RUN_ID resumes completed predictions.
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUN_STAGE="${1:-${RUN_STAGE:-diagnostic}}"
PROTOCOL_ID="${PROTOCOL_ID:-owleq-jws-2026-07-v2}"
RUN_ID="${RUN_ID:-${PROTOCOL_ID}-${RUN_STAGE}}"
MANIFEST="${MANIFEST:-configs/open_weight_experiment_v2.yaml}"
CONTEXT_LENGTH="${CONTEXT_LENGTH:-16384}"
MAX_OUTPUT_TOKENS="${MAX_OUTPUT_TOKENS:-1024}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-600}"
INFERENCE_SEED="${INFERENCE_SEED:-20260725}"
REPEAT_SUBSET_SEED="${REPEAT_SUBSET_SEED:-20260725}"
REPEAT_FRACTION="${REPEAT_FRACTION:-0.20}"
SMOKE_ORBITS="${SMOKE_ORBITS:-4}"
DIAGNOSTIC_ORBITS="${DIAGNOSTIC_ORBITS:-20}"
PROGRESS_EVERY="${PROGRESS_EVERY:-25}"
MAX_PARSE_ERROR_RATE="${MAX_PARSE_ERROR_RATE:-}"
MAX_OVERALL_PARSE_ERROR_RATE="${MAX_OVERALL_PARSE_ERROR_RATE:-}"
MAX_API_ERROR_RATE="${MAX_API_ERROR_RATE:-0.00}"
ANSWER_FIELD="${ANSWER_FIELD:-content}"
FORCE_ANSWER_FIELD="${FORCE_ANSWER_FIELD:-}"
CONFIRMATORY_PANEL_FILE="${CONFIRMATORY_PANEL_FILE:-}"
LM_STUDIO_PORT="${LM_STUDIO_PORT:-1234}"
LM_STUDIO_BASE_URL="${LM_STUDIO_BASE_URL:-http://127.0.0.1:${LM_STUDIO_PORT}/v1}"
LM_STUDIO_BASE_URL="${LM_STUDIO_BASE_URL%/}"
export LM_STUDIO_BASE_URL

DISCOVERY_CONDITIONS="C0,C1,C2,C4,C4S2,C5,C6,C7,C8"
FINAL_CONDITIONS="C0,C1,C2,C3,C4,C4S2,C5,C6,C7,C8,C9"

case "$RUN_STAGE" in
  diagnostic)
    DATASETS_CSV="${DATASETS_CSV:-data/certified/cl/benchmark.jsonl,data/certified/po/benchmark.jsonl}"
    EXPECTED_CONDITIONS="${EXPECTED_CONDITIONS:-$DISCOVERY_CONDITIONS}"
    LIMIT_ORBITS="$DIAGNOSTIC_ORBITS"
    RUN_BASELINES="${RUN_BASELINES:-0}"
    RUN_REPEAT_SUBSET="${RUN_REPEAT_SUBSET:-0}"
    REQUIRE_WEIGHTS_HASH="${REQUIRE_WEIGHTS_HASH:-0}"
    ;;
  smoke)
    DATASETS_CSV="${DATASETS_CSV:-data/certified/cl/benchmark.jsonl,data/certified/po/benchmark.jsonl}"
    EXPECTED_CONDITIONS="${EXPECTED_CONDITIONS:-$DISCOVERY_CONDITIONS}"
    LIMIT_ORBITS="$SMOKE_ORBITS"
    RUN_BASELINES="${RUN_BASELINES:-0}"
    RUN_REPEAT_SUBSET="${RUN_REPEAT_SUBSET:-0}"
    REQUIRE_WEIGHTS_HASH="${REQUIRE_WEIGHTS_HASH:-0}"
    ;;
  discovery)
    [[ "${DIAGNOSTIC_APPROVED:-NO}" == "YES" ]] || {
      echo "Refusing discovery inference: set DIAGNOSTIC_APPROVED=YES after reviewing a passing diagnostic run." >&2
      exit 2
    }
    [[ -n "${DIAGNOSTIC_RUN_DIR:-}" ]] || {
      echo "Discovery mode requires DIAGNOSTIC_RUN_DIR=reports/<passing-run-id>." >&2
      exit 2
    }
    DATASETS_CSV="${DATASETS_CSV:-data/certified/cl/benchmark.jsonl,data/certified/po/benchmark.jsonl}"
    EXPECTED_CONDITIONS="${EXPECTED_CONDITIONS:-$DISCOVERY_CONDITIONS}"
    LIMIT_ORBITS=0
    RUN_BASELINES="${RUN_BASELINES:-1}"
    RUN_REPEAT_SUBSET="${RUN_REPEAT_SUBSET:-1}"
    REQUIRE_WEIGHTS_HASH="${REQUIRE_WEIGHTS_HASH:-1}"
    ;;
  confirmatory)
    [[ "${CONFIRMATORY_APPROVED:-NO}" == "YES" ]] || {
      echo "Refusing confirmatory inference: set CONFIRMATORY_APPROVED=YES after dataset freeze." >&2
      exit 2
    }
    [[ -n "${DATASETS_CSV:-}" ]] || {
      echo "Confirmatory mode requires DATASETS_CSV with the frozen ordered dataset paths." >&2
      exit 2
    }
    EXPECTED_CONDITIONS="${EXPECTED_CONDITIONS:-$FINAL_CONDITIONS}"
    [[ "$EXPECTED_CONDITIONS" == "$FINAL_CONDITIONS" ]] || {
      echo "Confirmatory mode requires exactly: $FINAL_CONDITIONS" >&2
      exit 2
    }
    LIMIT_ORBITS=0
    RUN_BASELINES="${RUN_BASELINES:-1}"
    RUN_REPEAT_SUBSET="${RUN_REPEAT_SUBSET:-1}"
    REQUIRE_WEIGHTS_HASH=1
    ;;
  *)
    echo "Usage: $0 {diagnostic|smoke|discovery|confirmatory}" >&2
    exit 2
    ;;
esac

IFS=',' read -r -a DATASETS <<< "$DATASETS_CSV"

# Fields: exact LM Studio catalog key | frozen result identifier | reasoning control | answer field.
# "none" omits reasoning_effort. For Gemma/Qwen, LM Studio 0.4.8+ maps medium to
# model-native thinking; the smoke gate will fail if the installed runtime rejects it.
MODEL_SPECS=(
  "mistralai/mistral-small-3.2|mistral-small-3.2-owleq-v2|none|content"
  "openai/gpt-oss-20b|gpt-oss-20b-owleq-v2|medium|content"
  "google/gemma-4-26b-a4b|gemma-4-26b-a4b-owleq-v2|medium|content"
  "qwen/qwen3.6-35b-a3b|qwen3.6-35b-a3b-owleq-v2|medium|content"
  "meta/llama-3.3-70b|llama-3.3-70b-owleq-v2|none|content"
  "openai/gpt-oss-120b|gpt-oss-120b-owleq-v2|medium|content"
)

MODEL_MATRIX_FILE="${MODEL_MATRIX_FILE:-configs/lmstudio_models_v2.tsv}"
if [[ -n "${MODEL_MATRIX_FILE:-}" ]]; then
  [[ -f "$MODEL_MATRIX_FILE" ]] || {
    echo "MODEL_MATRIX_FILE not found: $MODEL_MATRIX_FILE" >&2
    exit 2
  }
  mapfile -t MODEL_SPECS < <(grep -vE '^[[:space:]]*(#|$)' "$MODEL_MATRIX_FILE")
fi

if [[ -n "$FORCE_ANSWER_FIELD" ]]; then
  [[ "$FORCE_ANSWER_FIELD" =~ ^(content|reasoning_content|reasoning|auto)$ ]] || {
    echo "FORCE_ANSWER_FIELD must be content, reasoning_content, reasoning, or auto" >&2
    exit 2
  }
  EFFECTIVE_MODEL_SPECS=()
  for specification in "${MODEL_SPECS[@]}"; do
    IFS='|' read -r model_key model_id reasoning _answer_field <<< "$specification"
    EFFECTIVE_MODEL_SPECS+=(
      "$model_key|$model_id|$reasoning|$FORCE_ANSWER_FIELD"
    )
  done
  MODEL_SPECS=("${EFFECTIVE_MODEL_SPECS[@]}")
fi

PY="${PY:-python3}"
[[ -x .venv/bin/python ]] && PY=.venv/bin/python
[[ -x .venv/Scripts/python.exe ]] && PY=.venv/Scripts/python.exe

PREDICTION_ROOT="data/predictions/$RUN_ID"
REPORT_ROOT="reports/$RUN_ID"
PROVENANCE_ROOT="$REPORT_ROOT/provenance"
LOG_ROOT="$REPORT_ROOT/logs"
POST_FAILURE_CONTINUATION="${POST_FAILURE_CONTINUATION:-0}"
CONTINUATION_AMENDMENT="${CONTINUATION_AMENDMENT:-}"
CONTINUATION_ATTEMPT_SNAPSHOT="${CONTINUATION_ATTEMPT_SNAPSHOT:-}"
CONTINUATION_PROVENANCE_ROOT="$PROVENANCE_ROOT/post_failure/runtime"
ACTIVE_PROVENANCE_ROOT="$PROVENANCE_ROOT"
if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
  [[ "$RUN_STAGE" == "confirmatory" ]] || {
    echo "Post-failure continuation is restricted to confirmatory runs." >&2
    exit 2
  }
  [[ "$PROTOCOL_ID" == "owleq-jws-2026-08-v33" ]] || {
    echo "Post-failure continuation is restricted to owleq-jws-2026-08-v33." >&2
    exit 2
  }
  [[ -n "$CONTINUATION_AMENDMENT" ]] || {
    echo "CONTINUATION_AMENDMENT is required." >&2
    exit 2
  }
  [[ -n "$CONTINUATION_ATTEMPT_SNAPSHOT" ]] || {
    echo "CONTINUATION_ATTEMPT_SNAPSHOT is required." >&2
    exit 2
  }
  ACTIVE_PROVENANCE_ROOT="$CONTINUATION_PROVENANCE_ROOT"
fi
mkdir -p "$PREDICTION_ROOT" "$PROVENANCE_ROOT" "$LOG_ROOT"
[[ "$POST_FAILURE_CONTINUATION" == "1" ]] && mkdir -p "$ACTIVE_PROVENANCE_ROOT"
RUN_LOG="$LOG_ROOT/run.log"
RUN_STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
exec > >(tee -a "$RUN_LOG") 2>&1

on_error() {
  local line="$1"
  local status="$2"
  echo "FAILED at line $line with exit status $status. No automatic retry was attempted." >&2
  local failure_file="$REPORT_ROOT/RUN_FAILED.txt"
  if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
    failure_file="$REPORT_ROOT/POST_FAILURE_CONTINUATION_FAILED.txt"
  fi
  printf 'status=FAILED\nline=%s\nexit_status=%s\nutc=%s\n' \
    "$line" "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$failure_file"
}
trap 'on_error "$LINENO" "$?"' ERR

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { echo "$*" >&2; exit 2; }

freeze_file() {
  local source="$1"
  local destination="$2"
  if [[ -f "$destination" ]]; then
    cmp -s "$source" "$destination" || \
      die "Frozen artifact changed for existing RUN_ID: $destination"
  else
    cp "$source" "$destination"
  fi
}

command -v lms >/dev/null || die "lms CLI is required."
command -v curl >/dev/null || die "curl is required."
command -v sha256sum >/dev/null || die "sha256sum is required."
command -v cmp >/dev/null || die "cmp is required."
[[ -f "$MANIFEST" ]] || die "Experiment manifest not found: $MANIFEST"
[[ "$ANSWER_FIELD" =~ ^(content|reasoning_content|reasoning|auto)$ ]] || \
  die "ANSWER_FIELD must be content, reasoning_content, reasoning, or auto"

if ! "$PY" -c "import owl_equivariance, openai" >/dev/null 2>&1; then
  if [[ "${AUTO_INSTALL:-1}" == "1" ]]; then
    "$PY" -m pip install -e ".[api,stats]"
  else
    die "Python dependencies missing. Run: $PY -m pip install -e '.[api,stats]'"
  fi
fi

if [[ "$RUN_STAGE" == "confirmatory" && -f "$REPORT_ROOT/RUN_FAILED.txt" && \
      "$POST_FAILURE_CONTINUATION" != "1" ]]; then
  die "Refusing an ordinary resume of a failed confirmatory run. Use scripts/run_v33_post_failure_continuation.sh."
fi
if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
  "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" check \
    --amendment "$CONTINUATION_AMENDMENT"
  "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" check-attempt \
    --snapshot "$CONTINUATION_ATTEMPT_SNAPSHOT"
fi

# The manifest owns stage-specific validity gates. Diagnostic samples contain only 20
# items per condition, so v3 permits one malformed response in a cell while retaining a
# stricter aggregate ceiling. Discovery and confirmatory runs keep their frozen limits.
read -r manifest_max_invalid manifest_max_overall < <(
  "$PY" - "$MANIFEST" "$RUN_STAGE" <<'PY'
import sys
from pathlib import Path
import yaml

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
inference = config["inference"]
if sys.argv[2] == "diagnostic":
    per_condition = inference.get(
        "diagnostic_per_condition_max_invalid_rate",
        inference.get("per_condition_max_invalid_rate", 0.02),
    )
    overall = inference.get(
        "diagnostic_overall_max_invalid_rate",
        inference.get("overall_max_invalid_rate", 1.0),
    )
else:
    per_condition = inference.get("per_condition_max_invalid_rate", 0.02)
    overall = inference.get("overall_max_invalid_rate", 1.0)
print(per_condition, overall)
PY
)
MAX_PARSE_ERROR_RATE="${MAX_PARSE_ERROR_RATE:-$manifest_max_invalid}"
MAX_OVERALL_PARSE_ERROR_RATE="${MAX_OVERALL_PARSE_ERROR_RATE:-$manifest_max_overall}"

"$PY" - "$MANIFEST" "$PROTOCOL_ID" <<'PY'
import sys
from pathlib import Path
import yaml

manifest = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
if manifest.get("protocol_id") != sys.argv[2]:
    raise SystemExit(
        f"protocol mismatch: manifest={manifest.get('protocol_id')!r}, "
        f"runner={sys.argv[2]!r}"
    )
PY

if [[ "$RUN_STAGE" == "discovery" ]]; then
  expected_diagnostic_reports="$((${#MODEL_SPECS[@]} * ${#DATASETS[@]}))"
  "$PY" - "$DIAGNOSTIC_RUN_DIR" "$PROTOCOL_ID" "$expected_diagnostic_reports" \
    "$DATASETS_CSV" "${MODEL_SPECS[@]}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
protocol_id = sys.argv[2]
expected = int(sys.argv[3])
expected_datasets = sys.argv[4].split(",")
expected_models = sys.argv[5:]
complete_path = root / "RUN_COMPLETE.json"
if not complete_path.is_file():
    raise SystemExit(f"diagnostic approval artifact missing: {complete_path}")
complete = json.loads(complete_path.read_text(encoding="utf-8"))
if complete.get("protocol_id") != protocol_id or complete.get("stage") != "diagnostic":
    raise SystemExit("DIAGNOSTIC_RUN_DIR belongs to a different protocol or stage")
recorded_datasets = (
    root / "provenance" / "datasets.txt"
).read_text(encoding="utf-8").splitlines()
recorded_models = (
    root / "provenance" / "model_matrix.txt"
).read_text(encoding="utf-8").splitlines()
if recorded_datasets != expected_datasets:
    raise SystemExit("diagnostic dataset list differs from the discovery dataset list")
if recorded_models != expected_models:
    raise SystemExit("diagnostic model settings differ from the discovery model matrix")
reports = sorted(root.glob("diagnostics/*/*/response_validity.json"))
failed = [
    path
    for path in reports
    if json.loads(path.read_text(encoding="utf-8")).get("status") != "PASS"
]
if len(reports) != expected or failed or complete.get("status") != "PASS":
    raise SystemExit(
        f"diagnostic evidence failed: reports={len(reports)}/{expected}, "
        f"failed={len(failed)}, run_status={complete.get('status')}"
    )
print(f"diagnostic evidence accepted: {root} ({len(reports)} passing reports)")
PY
fi

if [[ "$RUN_STAGE" == "discovery" || "$RUN_STAGE" == "confirmatory" ]]; then
  [[ -z "$FORCE_ANSWER_FIELD" ]] || \
    die "FORCE_ANSWER_FIELD is diagnostic-only; update the manifest and protocol id."
  "$PY" - "$MANIFEST" "$RUN_STAGE" "$CONTEXT_LENGTH" "$MAX_OUTPUT_TOKENS" "$REQUEST_TIMEOUT" \
    "$INFERENCE_SEED" "$REPEAT_SUBSET_SEED" "$REPEAT_FRACTION" \
    "$MAX_PARSE_ERROR_RATE" "$MAX_OVERALL_PARSE_ERROR_RATE" \
    "$MAX_API_ERROR_RATE" "${MODEL_SPECS[@]}" <<'PY'
import sys
from pathlib import Path
import yaml

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
stage = sys.argv[2]
inference = config["inference"]
actual = {
    "context_length": int(sys.argv[3]),
    "max_output_tokens": int(sys.argv[4]),
    "request_timeout_seconds": float(sys.argv[5]),
    "seed": int(sys.argv[6]),
    "repeat_subset_seed": int(sys.argv[7]),
    "repeat_subset_fraction": float(sys.argv[8]),
    "per_condition_max_invalid_rate": float(sys.argv[9]),
    "overall_max_invalid_rate": float(sys.argv[10]),
    "max_api_error_rate": float(sys.argv[11]),
}
expected = {
    key: inference[key]
    for key in (
        "context_length",
        "max_output_tokens",
        "request_timeout_seconds",
        "seed",
        "repeat_subset_seed",
        "per_condition_max_invalid_rate",
        "max_api_error_rate",
    )
}
expected["repeat_subset_fraction"] = config["stages"][stage]["repeat_subset_fraction"]
expected["overall_max_invalid_rate"] = inference.get(
    "overall_max_invalid_rate", actual["overall_max_invalid_rate"]
)
for key, value in actual.items():
    if value != expected[key]:
        raise SystemExit(
            f"frozen inference mismatch for {key}: runner={value!r}, "
            f"manifest={expected[key]!r}"
        )

actual_models = [spec.split("|") for spec in sys.argv[12:]]
expected_models = [
    [
        model["catalog_key"],
        model["model_id"],
        str(model["reasoning_effort"]),
        model["answer_field"],
    ]
    for model in config["models"]
]
if actual_models != expected_models:
    raise SystemExit("MODEL_MATRIX_FILE does not match the frozen manifest model matrix")
print("frozen inference and model-matrix gate passed")
PY
fi

read -r PRIMARY_ANALYSIS_IMPLEMENTATION CONFIRMATORY_PLANNED_BASE_ITEMS < <(
  "$PY" - "$MANIFEST" <<'PY'
import sys
from pathlib import Path
import yaml

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
implementation = config.get("analysis", {}).get("primary", {}).get("implementation", "gee")
planned = config.get("stages", {}).get("confirmatory", {}).get("planned_base_items", 1200)
print(implementation, planned)
PY
)

if [[ "$RUN_STAGE" == "confirmatory" && \
      "$PRIMARY_ANALYSIS_IMPLEMENTATION" == "lme4_glmer_laplace" ]]; then
  command -v Rscript >/dev/null || \
    die "v3.3 confirmatory analysis requires Rscript before inference starts."
  Rscript -e 'if (!requireNamespace("lme4", quietly=TRUE)) quit(status=2)' || \
    die "v3.3 confirmatory analysis requires the R package lme4 (Ubuntu: r-cran-lme4)."
fi

if [[ ! -f java/owl-certifier/target/owl-certifier.jar ]]; then
  bash scripts/build_java.sh -q package -DskipTests
fi

CURL_AUTH=()
if [[ -n "${LM_STUDIO_API_TOKEN:-}" ]]; then
  CURL_AUTH=(-H "Authorization: Bearer ${LM_STUDIO_API_TOKEN}")
fi

api_get() {
  local path="$1"
  curl -fsS --max-time 20 "${CURL_AUTH[@]}" \
    "${LM_STUDIO_BASE_URL%/v1}${path}"
}

api_post_json() {
  local path="$1"
  local payload_file="$2"
  curl -fsS --max-time "$REQUEST_TIMEOUT" "${CURL_AUTH[@]}" \
    -H "Content-Type: application/json" \
    --data-binary "@$payload_file" \
    "${LM_STUDIO_BASE_URL%/v1}${path}"
}

load_exact_model() {
  local model_key="$1"
  local response_file="$2"
  local payload_file
  payload_file="$(mktemp "$PROVENANCE_ROOT/.load_request.XXXXXX")"
  "$PY" - "$payload_file" "$model_key" "$CONTEXT_LENGTH" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "model": sys.argv[2],
            "context_length": int(sys.argv[3]),
            "flash_attention": True,
            "offload_kv_cache_to_gpu": True,
            "echo_load_config": True,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY
  api_post_json "/api/v1/models/load" "$payload_file" > "$response_file"
  rm -f "$payload_file"
}

verify_exact_loaded_model() {
  local response_file="$1"
  local ps_json="$2"
  local expected_model_key="$3"
  "$PY" - "$response_file" "$ps_json" "$expected_model_key" \
    "$CONTEXT_LENGTH" <<'PY'
import json
import sys
from pathlib import Path

response = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
processes = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
expected = sys.argv[3]
expected_context = int(sys.argv[4])

if response.get("status") != "loaded":
    raise SystemExit(f"REST load failed: status={response.get('status')!r}")
instance_id = response.get("instance_id")
if instance_id != expected:
    raise SystemExit(
        f"exact-load identity failure: instance_id={instance_id!r}, expected={expected!r}"
    )
load_context = response.get("load_config", {}).get("context_length")
if load_context != expected_context:
    raise SystemExit(
        f"REST load context failure: {load_context!r}, expected={expected_context}"
    )

if isinstance(processes, dict):
    for key in ("data", "models", "loadedModels", "loaded_models"):
        if isinstance(processes.get(key), list):
            processes = processes[key]
            break
if not isinstance(processes, list):
    raise SystemExit("unrecognized `lms ps --json` payload")

matches = [item for item in processes if item.get("modelKey") == expected]
if len(matches) != 1:
    raise SystemExit(
        f"exact-load process failure: found {len(matches)} processes for {expected!r}"
    )
process = matches[0]
if process.get("identifier") != instance_id:
    raise SystemExit(
        f"loaded identifier={process.get('identifier')!r}, expected={instance_id!r}"
    )
if process.get("contextLength") != expected_context:
    raise SystemExit(
        f"loaded context={process.get('contextLength')!r}, expected={expected_context}"
    )
print(instance_id)
PY
}

start_server_if_needed() {
  if api_get "/v1/models" >/dev/null 2>&1; then
    return
  fi
  case "$LM_STUDIO_BASE_URL" in
    http://127.0.0.1:*|http://localhost:*)
      lms server start --port "$LM_STUDIO_PORT"
      ;;
    *)
      die "Remote LM Studio server is unreachable: $LM_STUDIO_BASE_URL"
      ;;
  esac
  for _ in $(seq 1 30); do
    api_get "/v1/models" >/dev/null 2>&1 && return
    sleep 2
  done
  die "LM Studio did not become ready within 60 seconds."
}

dataset_slug() {
  basename "$(dirname "$1")" | tr -cs '[:alnum:]_.-' '_'
}

model_slug() {
  printf '%s' "$1" | tr -cs '[:alnum:]_.-' '_'
}

resolve_loaded_artifact() {
  local ps_json="$1"
  local model_key="$2"
  "$PY" - "$ps_json" "${LM_STUDIO_MODELS_DIR:-}" "$model_key" <<'PY'
import json
import os
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
explicit_root = sys.argv[2]
model_key = sys.argv[3]
roots = [Path.cwd()]
if explicit_root:
    roots.append(Path(explicit_root).expanduser())
roots.extend([
    Path.home() / ".lmstudio" / "models",
    Path.home() / ".cache" / "lm-studio" / "models",
])

entries = []
def walk(value, key=""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            walk(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            walk(child, key)
    elif isinstance(value, str):
        entries.append((key.lower(), value))
walk(payload)

suffixes = (".gguf", ".safetensors", ".mlx")
def candidates(raw):
    candidate = Path(raw).expanduser()
    return [candidate] if candidate.is_absolute() else [root / candidate for root in roots]

# Prefer an exact model artifact over any directory-like runtime metadata.
for _key, raw in entries:
    if not raw.lower().endswith(suffixes):
        continue
    for item in candidates(raw):
        if item.exists():
            print(item.resolve())
            raise SystemExit(0)

# Sharded weights are often represented by a model directory. Only accept values from a
# path-like metadata key and only when they resolve inside a known LM Studio model root.
model_roots = [root.resolve() for root in roots[1:] if root.exists()]
for key, raw in entries:
    if not any(token in key for token in ("path", "file", "artifact")):
        continue
    for item in candidates(raw):
        if not item.exists():
            continue
        resolved = item.resolve()
        if any(root in resolved.parents for root in model_roots):
            print(resolved)
            raise SystemExit(0)

if explicit_root:
    root = Path(explicit_root).expanduser().resolve()
    conventional = root / Path(model_key)
    if conventional.exists():
        print(conventional.resolve())
        raise SystemExit(0)
PY
}

hash_artifact() {
  local artifact="$1"
  if [[ -f "$artifact" ]]; then
    sha256sum "$artifact" | awk '{print $1}'
  elif [[ -d "$artifact" ]]; then
    (
      cd "$artifact"
      find . -type f -print0 | sort -z | xargs -0 sha256sum
    ) | sha256sum | awk '{print $1}'
  else
    return 1
  fi
}

audit_predictions() {
  local dataset="$1"
  local predictions="$2"
  local limit_orbits="$3"
  local repeats="$4"
  local repeat_offset="$5"
  local max_error_rate="$6"
  "$PY" - "$dataset" "$predictions" "$limit_orbits" "$repeats" \
    "$repeat_offset" "$max_error_rate" <<'PY'
import json
import sys
from pathlib import Path

dataset, predictions = map(Path, sys.argv[1:3])
limit, repeats, offset = map(int, sys.argv[3:6])
max_rate = float(sys.argv[6])
items = [json.loads(x) for x in dataset.read_text(encoding="utf-8").splitlines() if x]
if limit:
    selected = set(sorted({x["base_item_id"] for x in items})[:limit])
    items = [x for x in items if x["base_item_id"] in selected]
preds = [json.loads(x) for x in predictions.read_text(encoding="utf-8").splitlines() if x]
expected = len(items) * repeats
pairs = {(x["orbit_item_id"], x.get("repeat", 0)) for x in preds}
allowed_repeats = set(range(offset, offset + repeats))
errors = sum(x.get("label") is None or bool(x.get("parse_error")) for x in preds)
rate = errors / max(len(preds), 1)
print(f"audit: expected={expected} rows={len(preds)} unique={len(pairs)} "
      f"parse_or_api_errors={errors} ({rate:.2%})")
if len(preds) != expected or len(pairs) != expected:
    raise SystemExit("prediction completeness gate failed")
if any(x.get("repeat", 0) not in allowed_repeats for x in preds):
    raise SystemExit("repeat-index gate failed")
if rate > max_rate:
    raise SystemExit(f"parse/API error rate {rate:.2%} exceeds {max_rate:.2%}")
PY
}

validate_confirmatory_capacity() {
  "$PY" - "$MANIFEST" "$CONFIRMATORY_PANEL_FILE" "${DATASETS[@]}" <<'PY'
import sys
from pathlib import Path
import yaml

from owl_equivariance import protocol

manifest_path = Path(sys.argv[1])
panel_path = sys.argv[2]
paths = [Path(x) for x in sys.argv[3:]]
manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
criteria = protocol.PanelCriteria.from_manifest(manifest)

if criteria.panel_file_required:
    if not panel_path:
        raise SystemExit(
            "this protocol requires CONFIRMATORY_PANEL_FILE frozen before inference"
        )
    try:
        result = protocol.verify_panel(manifest_path, panel_path, paths)
    except protocol.PanelValidationError as exc:
        raise SystemExit(str(exc)) from exc
    for path in result["datasets"]:
        print(f"frozen panel source: {path}")
    print(
        f"confirmatory frozen-panel gate passed: {result['sources']} sources, "
        f"{result['base_items']} base items"
    )
else:
    # Backward-compatible gate for v2/v3. New protocols must use a frozen panel file.
    legacy_required = manifest["datasets"]["confirmatory"].get("required_sources")
    if legacy_required is not None and len(paths) != int(legacy_required):
        raise SystemExit(
            f"confirmatory protocol requires exactly {legacy_required} datasets, got {len(paths)}"
        )
    summaries = []
    problems = []
    root = manifest_path.resolve().parent.parent
    for path in paths:
        summary, source_problems = protocol.summarize_source(
            path,
            root=root,
            required_conditions=criteria.required_conditions,
        )
        summaries.append(summary)
        problems.extend(source_problems)
    problems.extend(protocol.validate_summaries(criteria, summaries))
    problems.extend(protocol.validate_cross_source_base_ids(paths))
    if problems:
        raise SystemExit("confirmatory capacity gate failed:\n- " + "\n- ".join(problems))
    print(
        f"confirmatory capacity gate passed: {len(summaries)} sources, "
        f"{sum(x.base_items for x in summaries)} base items"
    )
PY
}

run_inference() {
  local dataset="$1"
  local model_id="$2"
  local reasoning="$3"
  local output="$4"
  local repeats="${5:-1}"
  local repeat_offset="${6:-0}"
  local limit="${7:-0}"
  local answer_field="${8:-$ANSWER_FIELD}"
  local diagnostic_dir="${9:-}"
  local api_model="${10:-$model_id}"

  local limit_args=()
  [[ "$limit" -gt 0 ]] && limit_args=(--limit-orbits "$limit")

  "$PY" -m owl_equivariance.cli infer \
    --dataset "$dataset" \
    --model "lmstudio:$api_model" \
    --record-model-id "$model_id" \
    --style structured_proof \
    --reasoning-effort "$reasoning" \
    --seed "$INFERENCE_SEED" \
    --answer-field "$answer_field" \
    --max-output-tokens "$MAX_OUTPUT_TOKENS" \
    --request-timeout "$REQUEST_TIMEOUT" \
    --repeats "$repeats" \
    --repeat-offset "$repeat_offset" \
    --resume \
    --progress "$PROGRESS_EVERY" \
    "${limit_args[@]}" \
    --output "$output"

  # Completeness is checked independently of the response-validity gate so the diagnostic
  # report is always written, even when the model fails the 2% publication threshold.
  audit_predictions "$dataset" "$output" "$limit" "$repeats" "$repeat_offset" 1.0

  if [[ -n "$diagnostic_dir" ]]; then
    answer_field_args=()
    [[ "$answer_field" != "auto" ]] && \
      answer_field_args=(--require-answer-field "$answer_field")
    advisory_args=()
    if [[ "$RUN_STAGE" == "diagnostic" || "$POST_FAILURE_CONTINUATION" == "1" ]]; then
      advisory_args=(--advisory)
    fi
    "$PY" -m owl_equivariance.cli diagnose \
      --dataset "$dataset" \
      --predictions "$output" \
      --output-dir "$diagnostic_dir" \
      --max-invalid-rate "$MAX_PARSE_ERROR_RATE" \
      --max-overall-invalid-rate "$MAX_OVERALL_PARSE_ERROR_RATE" \
      --max-api-error-rate "$MAX_API_ERROR_RATE" \
      --require-response-payload \
      "${advisory_args[@]}" \
      "${answer_field_args[@]}"
    if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
      # A response-format threshold failure is retained and reported, but it no longer
      # stops post-failure collection. Transport errors and integrity defects remain fatal.
      "$PY" scripts/manage_post_failure_continuation.py diagnostic-check \
        --report "$diagnostic_dir/response_validity.json" \
        --max-api-error-rate "$MAX_API_ERROR_RATE"
    fi
  fi
}

audit_support_validation() {
  local source_predictions="$1"
  local validated_predictions="$2"
  "$PY" - "$source_predictions" "$validated_predictions" <<'PY'
import json
import sys
from pathlib import Path

source, validated = map(Path, sys.argv[1:3])
raw_rows = [json.loads(x) for x in source.read_text(encoding="utf-8").splitlines() if x]
rows = [json.loads(x) for x in validated.read_text(encoding="utf-8").splitlines() if x]
if len(rows) != len(raw_rows):
    raise SystemExit(
        f"support-validation coverage failed: {len(rows)}/{len(raw_rows)} rows"
    )
missing = [
    row.get("orbit_item_id")
    for row in rows
    if not isinstance(row.get("support_valid"), bool)
    or not isinstance(row.get("support_minimal"), bool)
    or not isinstance(row.get("answer_correct"), bool)
]
if missing:
    raise SystemExit(
        f"support-validation fields absent on {len(missing)} rows: {missing[:3]}"
    )
print(f"support-validation coverage: {len(rows)}/{len(raw_rows)} rows (100%)")
PY
}

primary_cell_complete() {
  local dataset="$1"
  local mslug="$2"
  local dslug raw validated
  dslug="$(dataset_slug "$dataset")"
  raw="$PREDICTION_ROOT/${dslug}.${mslug}.primary.jsonl"
  validated="$PREDICTION_ROOT/${dslug}.${mslug}.primary.validated.jsonl"
  [[ -s "$raw" && -s "$validated" ]] || return 1
  [[ -s "$REPORT_ROOT/diagnostics/$mslug/$dslug/response_validity.json" ]] || return 1
  [[ -s "$REPORT_ROOT/models/$mslug/$dslug/orbit_metrics.json" ]] || return 1
  audit_predictions "$dataset" "$raw" "$LIMIT_ORBITS" 1 0 1.0 >/dev/null || return 1
  audit_support_validation "$raw" "$validated" >/dev/null || return 1
  if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
    "$PY" scripts/manage_post_failure_continuation.py diagnostic-check \
      --report "$REPORT_ROOT/diagnostics/$mslug/$dslug/response_validity.json" \
      --max-api-error-rate "$MAX_API_ERROR_RATE" >/dev/null || return 1
  fi
}

repeat_cell_complete() {
  local dataset="$1"
  local mslug="$2"
  local dslug subset raw validated
  dslug="$(dataset_slug "$dataset")"
  subset="$(dirname "$dataset")/${RUN_ID}.repeat-subset.jsonl"
  raw="$PREDICTION_ROOT/${dslug}.${mslug}.repeats-1-2.jsonl"
  validated="$PREDICTION_ROOT/${dslug}.${mslug}.repeats-1-2.validated.jsonl"
  [[ -s "$subset" && -s "$raw" && -s "$validated" ]] || return 1
  [[ -s "$REPORT_ROOT/diagnostics/$mslug/$dslug/repeats/response_validity.json" ]] || return 1
  [[ -s "$REPORT_ROOT/models/$mslug/$dslug/stability/stability.json" ]] || return 1
  audit_predictions "$subset" "$raw" 0 2 1 1.0 >/dev/null || return 1
  audit_support_validation "$raw" "$validated" >/dev/null || return 1
  if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
    "$PY" scripts/manage_post_failure_continuation.py diagnostic-check \
      --report "$REPORT_ROOT/diagnostics/$mslug/$dslug/repeats/response_validity.json" \
      --max-api-error-rate "$MAX_API_ERROR_RATE" >/dev/null || return 1
  fi
}

model_outputs_complete() {
  local mslug="$1"
  local dataset
  for dataset in "${DATASETS[@]}"; do
    primary_cell_complete "$dataset" "$mslug" || return 1
    if [[ "$RUN_REPEAT_SUBSET" == "1" ]]; then
      repeat_cell_complete "$dataset" "$mslug" || return 1
    fi
  done
}

baseline_cell_complete() {
  local dataset="$1"
  local baseline="$2"
  local dslug raw validated
  dslug="$(dataset_slug "$dataset")"
  raw="$PREDICTION_ROOT/${dslug}.${baseline}.primary.jsonl"
  validated="$PREDICTION_ROOT/${dslug}.${baseline}.primary.validated.jsonl"
  [[ -s "$raw" && -s "$validated" ]] || return 1
  [[ -s "$REPORT_ROOT/baselines/$baseline/$dslug/orbit_metrics.json" ]] || return 1
  audit_predictions "$dataset" "$raw" "$LIMIT_ORBITS" 1 0 1.0 >/dev/null || return 1
  audit_support_validation "$raw" "$validated" >/dev/null || return 1
}

step "Run identity and environment"
echo "protocol:       $PROTOCOL_ID"
echo "manifest:       $MANIFEST"
echo "run id:         $RUN_ID"
echo "stage:          $RUN_STAGE"
echo "LM Studio URL:  $LM_STUDIO_BASE_URL"
echo "context:        $CONTEXT_LENGTH"
echo "output ceiling: $MAX_OUTPUT_TOKENS"
echo "request timeout: $REQUEST_TIMEOUT seconds"
echo "sampling seed:  $INFERENCE_SEED"
echo "answer field:   $ANSWER_FIELD"
freeze_file "$MANIFEST" "$PROVENANCE_ROOT/experiment_manifest.yaml"
parameters_tmp="$(mktemp "$PROVENANCE_ROOT/.run_parameters.XXXXXX")"
"$PY" - "$parameters_tmp" "$PROTOCOL_ID" "$RUN_ID" "$RUN_STAGE" \
  "$CONTEXT_LENGTH" "$MAX_OUTPUT_TOKENS" "$REQUEST_TIMEOUT" "$INFERENCE_SEED" \
  "$REPEAT_SUBSET_SEED" "$REPEAT_FRACTION" "$MAX_PARSE_ERROR_RATE" \
  "$MAX_OVERALL_PARSE_ERROR_RATE" \
  "$MAX_API_ERROR_RATE" "$LM_STUDIO_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

keys = [
    "protocol_id",
    "run_id",
    "stage",
    "context_length",
    "max_output_tokens",
    "request_timeout_seconds",
    "inference_seed",
    "repeat_subset_seed",
    "repeat_fraction",
    "max_invalid_rate",
    "max_overall_invalid_rate",
    "max_api_error_rate",
    "lmstudio_base_url",
]
values = sys.argv[2:]
numeric_int = {"context_length", "max_output_tokens", "inference_seed", "repeat_subset_seed"}
numeric_float = {
    "request_timeout_seconds",
    "repeat_fraction",
    "max_invalid_rate",
    "max_overall_invalid_rate",
    "max_api_error_rate",
}
payload = {}
for key, value in zip(keys, values):
    if key in numeric_int:
        value = int(value)
    elif key in numeric_float:
        value = float(value)
    payload[key] = value
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
freeze_file "$parameters_tmp" "$PROVENANCE_ROOT/run_parameters.json"
rm -f "$parameters_tmp"
datasets_tmp="$(mktemp "$PROVENANCE_ROOT/.datasets.XXXXXX")"
printf '%s\n' "${DATASETS[@]}" > "$datasets_tmp"
freeze_file "$datasets_tmp" "$PROVENANCE_ROOT/datasets.txt"
rm -f "$datasets_tmp"
if [[ -n "$CONFIRMATORY_PANEL_FILE" ]]; then
  [[ -f "$CONFIRMATORY_PANEL_FILE" ]] || \
    die "CONFIRMATORY_PANEL_FILE not found: $CONFIRMATORY_PANEL_FILE"
  freeze_file "$CONFIRMATORY_PANEL_FILE" "$PROVENANCE_ROOT/confirmatory_panel.json"
fi
matrix_tmp="$(mktemp "$PROVENANCE_ROOT/.model_matrix.XXXXXX")"
printf '%s\n' "${MODEL_SPECS[@]}" > "$matrix_tmp"
freeze_file "$matrix_tmp" "$PROVENANCE_ROOT/model_matrix.txt"
rm -f "$matrix_tmp"
DATASET_SHA_FILE="$PROVENANCE_ROOT/dataset_sha256.txt"
MODEL_ARTIFACT_FILE="$PROVENANCE_ROOT/model_artifacts.tsv"
MODEL_RUNTIME_FILE="$PROVENANCE_ROOT/model_runtime.tsv"
if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
  DATASET_SHA_FILE="$ACTIVE_PROVENANCE_ROOT/dataset_sha256.txt"
  MODEL_ARTIFACT_FILE="$ACTIVE_PROVENANCE_ROOT/model_artifacts.tsv"
  MODEL_RUNTIME_FILE="$ACTIVE_PROVENANCE_ROOT/model_runtime.tsv"
  : > "$DATASET_SHA_FILE"
  touch "$MODEL_ARTIFACT_FILE"
  if [[ ! -s "$MODEL_RUNTIME_FILE" ]]; then
    printf 'model_id\tstarted_utc\tfinished_utc\twall_seconds\n' \
      > "$MODEL_RUNTIME_FILE"
  fi
else
  : > "$DATASET_SHA_FILE"
  : > "$MODEL_ARTIFACT_FILE"
  printf 'model_id\tstarted_utc\tfinished_utc\twall_seconds\n' \
    > "$MODEL_RUNTIME_FILE"
fi
"$PY" -m pip freeze > "$ACTIVE_PROVENANCE_ROOT/python_packages.txt"
java -version > "$ACTIVE_PROVENANCE_ROOT/java_version.txt" 2>&1 || true
(
  find src scripts configs java/owl-certifier/pom.xml -type f -print0 |
    sort -z |
    xargs -0 sha256sum
) > "$ACTIVE_PROVENANCE_ROOT/source_sha256.txt"

start_server_if_needed
(lms --version || lms version || lms) > "$ACTIVE_PROVENANCE_ROOT/lms_version.txt" 2>&1 || true
lms ls --json > "$ACTIVE_PROVENANCE_ROOT/lms_ls.json"
api_get "/api/v0/models" > "$ACTIVE_PROVENANCE_ROOT/api_v0_models.json"
api_get "/api/v1/models" > "$ACTIVE_PROVENANCE_ROOT/api_v1_models.json"
bash scripts/record_environment.sh "$ACTIVE_PROVENANCE_ROOT/environment.json"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi -q > "$ACTIVE_PROVENANCE_ROOT/nvidia-smi-q.txt"
  nvidia-smi --query-gpu=timestamp,name,uuid,driver_version,memory.total \
    --format=csv,noheader > "$ACTIVE_PROVENANCE_ROOT/gpus.csv"
fi

step "Frozen call budget"
"$PY" -m owl_equivariance.cli budget \
  --manifest "$MANIFEST" \
  --stage "$RUN_STAGE"

step "Dataset publication gates"
declare -A SEEN_DATASET_SLUGS=()
for dataset in "${DATASETS[@]}"; do
  [[ -f "$dataset" ]] || die "Dataset not found: $dataset"
  dslug="$(dataset_slug "$dataset")"
  [[ -z "${SEEN_DATASET_SLUGS[$dslug]:-}" ]] || \
    die "Dataset paths produce the same artifact slug: $dslug"
  SEEN_DATASET_SLUGS[$dslug]=1
  "$PY" -m owl_equivariance.cli validate \
    --dataset "$dataset" \
    --expect-conditions "$EXPECTED_CONDITIONS"
  sha256sum "$dataset" >> "$DATASET_SHA_FILE"
done
if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
  cmp -s "$DATASET_SHA_FILE" "$PROVENANCE_ROOT/dataset_sha256.txt" || \
    die "Continuation dataset hashes differ from the protected failed run."
fi
[[ "$RUN_STAGE" == "confirmatory" ]] && validate_confirmatory_capacity

if [[ "$RUN_BASELINES" == "1" ]]; then
  step "Model-independent baselines"
  for dataset in "${DATASETS[@]}"; do
    dslug="$(dataset_slug "$dataset")"
    for baseline in oracle majority lexical; do
      raw="$PREDICTION_ROOT/${dslug}.${baseline}.primary.jsonl"
      validated="$PREDICTION_ROOT/${dslug}.${baseline}.primary.validated.jsonl"
      if [[ "$POST_FAILURE_CONTINUATION" == "1" ]] && \
         baseline_cell_complete "$dataset" "$baseline"; then
        echo "continuation: verified and skipped complete baseline $baseline/$dslug"
        continue
      fi
      "$PY" -m owl_equivariance.cli infer \
        --dataset "$dataset" --model "$baseline" \
        --style structured_proof --reasoning-effort none \
        --max-output-tokens "$MAX_OUTPUT_TOKENS" --resume --output "$raw"
      bash scripts/certifier.sh validate-support \
        --dataset "$dataset" --predictions "$raw" --output "$validated"
      audit_support_validation "$raw" "$validated"
      "$PY" -m owl_equivariance.cli evaluate \
        --dataset "$dataset" --predictions "$validated" \
        --output-dir "$REPORT_ROOT/baselines/$baseline/$dslug"
    done
  done
fi

ALL_PRIMARY_VALIDATED=()
MODEL_IDS=()

for specification in "${MODEL_SPECS[@]}"; do
  IFS='|' read -r model_key model_id reasoning answer_field <<< "$specification"
  answer_field="${answer_field:-$ANSWER_FIELD}"
  [[ -n "$model_key" && -n "$model_id" && -n "$reasoning" ]] || \
    die "Invalid model specification: $specification"
  MODEL_IDS+=("$model_id")
  mslug="$(model_slug "$model_id")"
  for dataset in "${DATASETS[@]}"; do
    dslug="$(dataset_slug "$dataset")"
    ALL_PRIMARY_VALIDATED+=(
      "$PREDICTION_ROOT/${dslug}.${mslug}.primary.validated.jsonl"
    )
  done
  if [[ "$POST_FAILURE_CONTINUATION" == "1" ]] && \
     model_outputs_complete "$mslug"; then
    step "Verify and skip complete model $model_id"
    echo "No LM Studio load or inference request was needed for $model_id."
    continue
  fi
  model_started_epoch="$(date +%s)"
  model_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  step "Load and freeze $model_key as $model_id"
  lms unload --all || true
  load_response="$ACTIVE_PROVENANCE_ROOT/${mslug}.load_response.json"
  load_exact_model "$model_key" "$load_response"

  lms ps
  ps_json="$ACTIVE_PROVENANCE_ROOT/${mslug}.lms_ps.json"
  lms ps --json > "$ps_json"
  instance_id="$(
    verify_exact_loaded_model "$load_response" "$ps_json" "$model_key"
  )"
  echo "exact model identity verified: $instance_id"
  api_get "/api/v1/models" > "$ACTIVE_PROVENANCE_ROOT/${mslug}.api_v1_models.json"

  artifact="$(resolve_loaded_artifact "$ps_json" "$model_key" || true)"
  weights_sha=""
  if [[ -n "$artifact" ]]; then
    weights_sha="$(hash_artifact "$artifact")"
    if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
      "$PY" scripts/manage_post_failure_continuation.py record-model-artifact \
        --original "$PROVENANCE_ROOT/model_artifacts.tsv" \
        --continuation "$MODEL_ARTIFACT_FILE" \
        --model-id "$model_id" \
        --sha256 "$weights_sha" \
        --path "$artifact"
    else
      printf '%s\t%s\t%s\n' "$model_id" "$weights_sha" "$artifact" \
        >> "$MODEL_ARTIFACT_FILE"
    fi
  elif [[ "$REQUIRE_WEIGHTS_HASH" == "1" ]]; then
    die "Could not resolve the loaded artifact for $model_id. Set LM_STUDIO_MODELS_DIR."
  else
    echo "WARNING: loaded artifact path was not resolved for $model_id." >&2
  fi

  preflight_args=()
  [[ -n "$weights_sha" ]] && preflight_args=(--weights-sha256 "$weights_sha")
  "$PY" -m owl_equivariance.cli lmstudio-preflight \
    --model "$instance_id" \
    --base-url "$LM_STUDIO_BASE_URL" \
    "${preflight_args[@]}" \
    --output "$ACTIVE_PROVENANCE_ROOT/${mslug}.preflight.json"

  step "Primary inference: $model_id"
  for dataset in "${DATASETS[@]}"; do
    dslug="$(dataset_slug "$dataset")"
    raw="$PREDICTION_ROOT/${dslug}.${mslug}.primary.jsonl"
    validated="$PREDICTION_ROOT/${dslug}.${mslug}.primary.validated.jsonl"
    diagnostic_dir="$REPORT_ROOT/diagnostics/$mslug/$dslug"
    if [[ "$POST_FAILURE_CONTINUATION" == "1" ]] && \
       primary_cell_complete "$dataset" "$mslug"; then
      echo "continuation: verified and skipped complete primary cell $model_id/$dslug"
    else
      run_inference "$dataset" "$model_id" "$reasoning" "$raw" 1 0 \
        "$LIMIT_ORBITS" "$answer_field" "$diagnostic_dir" "$instance_id"
      bash scripts/certifier.sh validate-support \
        --dataset "$dataset" --predictions "$raw" --output "$validated"
      audit_support_validation "$raw" "$validated"
      "$PY" -m owl_equivariance.cli evaluate \
        --dataset "$dataset" --predictions "$validated" \
        --output-dir "$REPORT_ROOT/models/$mslug/$dslug"
    fi

    if [[ "$RUN_REPEAT_SUBSET" == "1" ]]; then
      # Keep the subset beside its source benchmark so the original mapping manifests
      # remain resolvable by the publication validation gate.
      subset_dir="$(dirname "$dataset")"
      subset="$subset_dir/${RUN_ID}.repeat-subset.jsonl"
      subset_manifest="$subset_dir/${RUN_ID}.repeat-subset.manifest.json"
      "$PY" scripts/make_repeat_subset.py \
        --dataset "$dataset" \
        --output "$subset" \
        --manifest "$subset_manifest" \
        --fraction "$REPEAT_FRACTION" \
        --seed "$REPEAT_SUBSET_SEED"
      mkdir -p "$PROVENANCE_ROOT/repeat_subsets"
      freeze_file \
        "$subset" \
        "$PROVENANCE_ROOT/repeat_subsets/${dslug}.repeat-subset.jsonl"
      freeze_file \
        "$subset_manifest" \
        "$PROVENANCE_ROOT/repeat_subsets/${dslug}.repeat-subset.manifest.json"
      "$PY" -m owl_equivariance.cli validate \
        --dataset "$subset" --expect-conditions "$EXPECTED_CONDITIONS"

      repeat_raw="$PREDICTION_ROOT/${dslug}.${mslug}.repeats-1-2.jsonl"
      repeat_validated="$PREDICTION_ROOT/${dslug}.${mslug}.repeats-1-2.validated.jsonl"
      if [[ "$POST_FAILURE_CONTINUATION" == "1" ]] && \
         repeat_cell_complete "$dataset" "$mslug"; then
        echo "continuation: verified and skipped complete repeat cell $model_id/$dslug"
      else
        run_inference "$subset" "$model_id" "$reasoning" "$repeat_raw" 2 1 0 \
          "$answer_field" "$REPORT_ROOT/diagnostics/$mslug/$dslug/repeats" \
          "$instance_id"
        bash scripts/certifier.sh validate-support \
          --dataset "$subset" --predictions "$repeat_raw" --output "$repeat_validated"
        audit_support_validation "$repeat_raw" "$repeat_validated"
        "$PY" -m owl_equivariance.cli stability \
          --dataset "$subset" \
          --predictions "$validated" "$repeat_validated" \
          --expected-repeats 3 \
          --output-dir "$REPORT_ROOT/models/$mslug/$dslug/stability"
      fi
    fi
  done
  model_finished_epoch="$(date +%s)"
  printf '%s\t%s\t%s\t%s\n' \
    "$model_id" "$model_started_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$((model_finished_epoch - model_started_epoch))" \
    >> "$MODEL_RUNTIME_FILE"
done

if [[ "$RUN_STAGE" == "discovery" || "$RUN_STAGE" == "confirmatory" ]]; then
  step "Pooled primary analysis"
  "$PY" -m owl_equivariance.cli export-analysis \
    --dataset "${DATASETS[@]}" \
    --predictions "${ALL_PRIMARY_VALIDATED[@]}" \
    --style structured_proof \
    --permutations 10000 \
    --output "$REPORT_ROOT/primary_analysis.csv"

  if [[ "$RUN_STAGE" == "confirmatory" && \
        "$PRIMARY_ANALYSIS_IMPLEMENTATION" == "lme4_glmer_laplace" ]]; then
    step "Preregistered confirmatory crossed-random-intercept GLMM"
    Rscript scripts/analyze_confirmatory_v33.R \
      "$REPORT_ROOT/primary_analysis.csv" \
      "$REPORT_ROOT/confirmatory_glmm"
  fi

  for model_id in "${MODEL_IDS[@]}"; do
    mslug="$(model_slug "$model_id")"
    "$PY" -m owl_equivariance.cli model \
      --analysis "$REPORT_ROOT/primary_analysis.csv" \
      --estimator gee \
      --reference C0 \
      --model "$model_id" \
      --output-dir "$REPORT_ROOT/models/$mslug/statistical_model"
    "$PY" -m owl_equivariance.cli model \
      --analysis "$REPORT_ROOT/primary_analysis.csv" \
      --estimator gee \
      --reference C0 \
      --outcome parsed \
      --model "$model_id" \
      --output-dir "$REPORT_ROOT/models/$mslug/response_validity_model"
  done
  "$PY" -m owl_equivariance.cli model \
    --analysis "$REPORT_ROOT/primary_analysis.csv" \
    --estimator gee \
    --reference C0 \
    --condition-model-interaction \
    --output-dir "$REPORT_ROOT/pooled_correctness_interaction_model"
  "$PY" -m owl_equivariance.cli model \
    --analysis "$REPORT_ROOT/primary_analysis.csv" \
    --estimator gee \
    --reference C0 \
    --outcome parsed \
    --condition-model-interaction \
    --output-dir "$REPORT_ROOT/pooled_response_validity_interaction_model"

  if [[ "$RUN_STAGE" == "discovery" ]]; then
    step "Prospective confirmatory power calibration from discovery discordance"
    "$PY" -m owl_equivariance.cli power \
      --dataset "${DATASETS[@]}" \
      --predictions "${ALL_PRIMARY_VALIDATED[@]}" \
      --reference C0 \
      --condition C4 \
      --outcome correct \
      --planned-pairs "$CONFIRMATORY_PLANNED_BASE_ITEMS" \
      --target-gap 0.05 \
      --family-size 10 \
      --simulations 10000 \
      --min-power 0.80 \
      --advisory \
      --output-dir "$REPORT_ROOT/power/correctness"
    "$PY" -m owl_equivariance.cli power \
      --dataset "${DATASETS[@]}" \
      --predictions "${ALL_PRIMARY_VALIDATED[@]}" \
      --reference C0 \
      --condition C4 \
      --outcome parsed \
      --planned-pairs "$CONFIRMATORY_PLANNED_BASE_ITEMS" \
      --target-gap 0.05 \
      --family-size 10 \
      --simulations 10000 \
      --min-power 0.80 \
      --advisory \
      --output-dir "$REPORT_ROOT/power/response_validity"
  else
    echo "Confirmatory post-hoc power calculation skipped by the frozen protocol."
  fi
else
  echo "$RUN_STAGE stage passed; pooled hypothesis models were intentionally not fitted."
fi

if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
  step "Post-failure integrity and validity accounting"
  expected_validity_reports="$((${#MODEL_SPECS[@]} * ${#DATASETS[@]} * 2))"
  "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" finalize \
    --amendment "$CONTINUATION_AMENDMENT" \
    --report-root "$REPORT_ROOT" \
    --output "$REPORT_ROOT/POST_FAILURE_VALIDITY_SUMMARY.json" \
    --expected-reports "$expected_validity_reports" \
    --max-api-error-rate "$MAX_API_ERROR_RATE"
  "$PY" scripts/manage_post_failure_continuation.py --root "$REPO_ROOT" check-attempt \
    --snapshot "$CONTINUATION_ATTEMPT_SNAPSHOT"
  "$PY" scripts/manage_post_failure_continuation.py merge-model-artifacts \
    --original "$PROVENANCE_ROOT/model_artifacts.tsv" \
    --continuation "$MODEL_ARTIFACT_FILE" \
    --output "$ACTIVE_PROVENANCE_ROOT/all_model_artifacts.tsv"
  recorded_models="$(awk 'NF {count += 1} END {print count + 0}' \
    "$ACTIVE_PROVENANCE_ROOT/all_model_artifacts.tsv")"
  [[ "$recorded_models" -eq "${#MODEL_SPECS[@]}" ]] || \
    die "Continuation model artifact coverage is $recorded_models/${#MODEL_SPECS[@]}."
fi

step "Finalize immutable checksums"
(
  find "$PREDICTION_ROOT" "$REPORT_ROOT" -type f \
    ! -name SHA256SUMS ! -path "$RUN_LOG" -print0 |
    sort -z |
    xargs -0 sha256sum
) > "$REPORT_ROOT/SHA256SUMS"

DIAGNOSTIC_GATE_STATUS=0
if [[ "$RUN_STAGE" == "diagnostic" ]]; then
  expected_diagnostic_reports="$((${#MODEL_SPECS[@]} * ${#DATASETS[@]}))"
  if ! "$PY" - "$REPORT_ROOT" "$expected_diagnostic_reports" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected = int(sys.argv[2])
reports = sorted(root.glob("diagnostics/*/*/response_validity.json"))
failed = []
for path in reports:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "PASS":
        failed.append(str(path))
print(f"diagnostic survey: {len(reports)} model/dataset reports, {len(failed)} failed")
for path in failed:
    print(f"  FAIL: {path}")
if len(reports) != expected:
    print(f"  FAIL: expected {expected} diagnostic reports")
if len(reports) != expected or failed:
    raise SystemExit(1)
PY
  then
    DIAGNOSTIC_GATE_STATUS=1
  fi
fi

if [[ "${KEEP_MODEL_LOADED:-0}" != "1" ]]; then
  lms unload --all || true
fi

RUN_FINISHED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMPLETION_FILE="$REPORT_ROOT/RUN_COMPLETE.json"
[[ "$POST_FAILURE_CONTINUATION" == "1" ]] && \
  COMPLETION_FILE="$REPORT_ROOT/POST_FAILURE_CONTINUATION_COMPLETE.json"
"$PY" - "$COMPLETION_FILE" "$PROTOCOL_ID" "$RUN_ID" "$RUN_STAGE" \
  "$RUN_STARTED_UTC" "$RUN_FINISHED_UTC" "$DIAGNOSTIC_GATE_STATUS" \
  "$POST_FAILURE_CONTINUATION" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
continuation = int(sys.argv[8]) == 1
payload = {
    "status": (
        "POST_FAILURE_COLLECTION_COMPLETE"
        if continuation
        else ("PASS" if int(sys.argv[7]) == 0 else "DIAGNOSTIC_GATE_FAILED")
    ),
    "protocol_id": sys.argv[2],
    "run_id": sys.argv[3],
    "stage": sys.argv[4],
    "started_utc": sys.argv[5],
    "finished_utc": sys.argv[6],
}
if continuation:
    payload.update(
        {
            "classification": "post_failure_protocol_deviation",
            "original_gate_failure_retained": True,
            "preregistered_status": "FAILED_RESPONSE_VALIDITY_GATE",
            "manuscript_disclosure_required": True,
        }
    )
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
sha256sum "$COMPLETION_FILE" >> "$REPORT_ROOT/SHA256SUMS"

echo
echo "Run complete."
echo "Predictions: $PREDICTION_ROOT"
echo "Reports:     $REPORT_ROOT"
echo "Checksums:   $REPORT_ROOT/SHA256SUMS"
echo "Log:         $RUN_LOG"
if [[ "$POST_FAILURE_CONTINUATION" == "1" ]]; then
  echo "Classification: post-failure protocol deviation (original failure retained)."
fi
if [[ "$DIAGNOSTIC_GATE_STATUS" -ne 0 ]]; then
  echo "Diagnostic survey completed, but one or more publication gates failed." >&2
  exit "$DIAGNOSTIC_GATE_STATUS"
fi
