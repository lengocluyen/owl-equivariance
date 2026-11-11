# Open-weight journal experiment v2

**Protocol:** `owleq-jws-2026-07-v2`  
**Manifest:** `configs/open_weight_experiment_v2.yaml`  
**Model matrix:** `configs/lmstudio_models_v2.tsv`

This protocol supersedes v1 only for new LM Studio open-weight runs. Existing v1
predictions and reports remain unchanged.

## What the runner now guarantees

- Loads and unloads one already-installed LM Studio model at a time.
- Saves every prediction immediately, so an interrupted run can resume.
- Retains the complete API response JSON, extracted answer text, response channel,
  finish reason, token counts, timing, parser error and deterministic parser repairs.
- Records the LM Studio catalog, loaded-process metadata, model artifact hash,
  environment, GPU details, Python packages, Java version, source hashes and wall time.
- Separates logical correctness from parse-valid response rate.
- Stops smoke, discovery and confirmatory runs if any condition exceeds 2% invalid
  responses or if any API call fails.
- Runs symbolic proof-support validation and requires 100% validation coverage.
- Freezes a stratified 20% subset for two additional responses and analyzes repeats
  within item rather than treating them as independent observations.
- Refuses confirmatory inference unless exactly six certified datasets, at least 200
  base items each, and all eleven conditions are supplied.

## Server preparation

From the repository root on the Linux server:

```bash
set -euo pipefail

python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[api,stats,dev]'
bash scripts/build_java.sh -q package -DskipTests
./.venv/bin/python -m pytest -q

lms server status >/dev/null 2>&1 || lms server start --port 1234
```

The runner does not download models. Verify that the six catalog keys in
`configs/lmstudio_models_v2.tsv` match `lms ls`. If a key differs on the server, edit a
copy of the matrix and pass it through `MODEL_MATRIX_FILE`; do not change identifiers
after data collection begins.

For discovery and confirmatory runs, set `LM_STUDIO_MODELS_DIR` to the directory from
which the loaded GGUF/model artifact can be resolved and hashed:

```bash
export LM_STUDIO_MODELS_DIR="/absolute/path/to/lmstudio/models"
```

## Phase 1: response-channel diagnostic

The diagnostic evaluates 20 complete orbits from CL and PO for every model: 360 calls per
model, 2,160 calls total. It surveys every model even when a gate fails, writes all
diagnostic reports, then exits non-zero if any model/dataset fails.

```bash
RUN_ID=owleq-jws-2026-07-v2-diagnostic-content \
  bash scripts/run_lmstudio_publication.sh diagnostic
```

Read:

```text
reports/<RUN_ID>/diagnostics/<model>/<dataset>/response_validity.md
```

The frozen answer field is `content`. If full response payloads demonstrate that one
adapter places the final JSON in another field, perform a new diagnostic run with a new
run id. `auto` is for diagnosis only; freeze one explicit field before discovery:

```bash
RUN_ID=owleq-jws-2026-07-v2-diagnostic-auto \
FORCE_ANSWER_FIELD=auto \
  bash scripts/run_lmstudio_publication.sh diagnostic
```

Do not select a field by comparing task accuracy. Select it only from the documented
location of the final assistant answer and response-validity evidence. If the prompt,
schema, reasoning setting, output ceiling or answer field changes, assign a new protocol
suffix and repeat the diagnostic.

Stored payloads can be inspected under a different field without another model call:

```bash
./.venv/bin/python -m owl_equivariance.cli reparse \
  --dataset data/certified/cl/benchmark.jsonl \
  --predictions data/predictions/<RUN_ID>/<FILE>.jsonl \
  --answer-field reasoning_content \
  --output data/predictions/<RUN_ID>/<FILE>.reparsed-reasoning-content.jsonl
```

This command only changes parsing fields in a new artifact; it clears prior symbolic
support-validation fields. Run `diagnose` and `validate-support` again afterward.

## Phase 2: full six-model discovery

Run this only after every diagnostic cell passes:

```bash
export LM_STUDIO_MODELS_DIR="/absolute/path/to/lmstudio/models"

DIAGNOSTIC_APPROVED=YES \
DIAGNOSTIC_RUN_DIR=reports/owleq-jws-2026-07-v2-diagnostic-content \
RUN_ID=owleq-jws-2026-07-v2-discovery \
  bash scripts/run_lmstudio_publication.sh discovery
```

The discovery run evaluates all 204 CL/PO base orbits under nine conditions, all six
models, and two extra responses on the frozen 20% subset. It produces:

- raw and parsed prediction JSONL under `data/predictions/<RUN_ID>/`;
- per-model answer, response-validity, orbit and proof reports;
- repeat-stability reports;
- correctness and response-validity GEE models;
- condition-by-model interaction models and paired confirmatory power simulations;
- immutable checksums and provenance under `reports/<RUN_ID>/`.

Resume with the exact same command and `RUN_ID`. Completed `(item, repeat)` records are
skipped. Never reuse a `RUN_ID` after changing a model, prompt, parser option or dataset.

## Confirmatory run

Confirmatory execution remains intentionally blocked until the six held-out certified
datasets exist. When they do, pass their exact paths:

```bash
DATASETS_CSV="data/certified/a/benchmark.jsonl,data/certified/b/benchmark.jsonl,data/certified/c/benchmark.jsonl,data/certified/d/benchmark.jsonl,data/certified/e/benchmark.jsonl,data/certified/f/benchmark.jsonl" \
CONFIRMATORY_APPROVED=YES \
RUN_ID=owleq-jws-2026-07-v2-confirmatory \
  bash scripts/run_lmstudio_publication.sh confirmatory
```

The capacity, condition, response-validity, provenance, proof-validation and repeat gates
all run before or during inference. A failed gate is an experiment stop, not a result to
silently exclude.

## Useful standalone audits

```bash
./.venv/bin/python -m owl_equivariance.cli diagnose \
  --dataset data/certified/cl/benchmark.jsonl \
  --predictions data/predictions/<RUN_ID>/<FILE>.jsonl \
  --output-dir reports/<RUN_ID>/manual-diagnostic \
  --max-invalid-rate 0.02 \
  --max-api-error-rate 0 \
  --require-response-payload \
  --require-answer-field content

./.venv/bin/python -m owl_equivariance.cli budget \
  --manifest configs/open_weight_experiment_v2.yaml \
  --stage discovery
```
