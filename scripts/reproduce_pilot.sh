#!/usr/bin/env bash
# Regenerate the pilot end to end from frozen inputs (spec section 36.3).
#
#   source .owleq-toolchain.env    # from scripts/bootstrap_toolchain.sh
#   bash scripts/reproduce_pilot.sh
#
# One ontology per invocation; run it once per ontology for a multi-ontology pilot:
#
#   bash scripts/reproduce_pilot.sh                                    # cl (default)
#   ONTOLOGY_ID=po ONTOLOGY_FILE=data/raw/po.owl EL_FRAGMENT=1 \
#     ONTOLOGY_URL=http://purl.obolibrary.org/obo/po.owl \
#     ONTOLOGY_VERSION=po-2026-07 bash scripts/reproduce_pilot.sh
#
# Then pool them for analysis:
#
#   owleq export-analysis \
#     --dataset data/certified/cl/benchmark.jsonl data/certified/po/benchmark.jsonl \
#     --predictions data/predictions/*.validated.jsonl --output reports/analysis.csv
#
# Every step is deterministic given (ontology, seed, condition list), so a rerun produces
# byte-identical artifacts and identical content hashes. Model inference is the one stage
# that is not: the reference baselines are deterministic, real models are not.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ONTOLOGY_ID="${ONTOLOGY_ID:-cl}"
ONTOLOGY_FILE="${ONTOLOGY_FILE:-data/raw/cl-basic.owl}"
ONTOLOGY_URL="${ONTOLOGY_URL:-http://purl.obolibrary.org/obo/cl/cl-basic.owl}"
# Pinned and passed through to the build, so the dataset records which release it came from.
ONTOLOGY_VERSION="${ONTOLOGY_VERSION:-cl-basic-2026-07}"
CONDITIONS="${CONDITIONS:-C0,C1,C2,C4,C4S2,C5,C6,C7,C8}"
POSITIVES="${POSITIVES:-60}"
NEGATIVES="${NEGATIVES:-60}"
DISTRACTORS="${DISTRACTORS:-12}"
MAX_CONTEXT="${MAX_CONTEXT:-45}"
SEED="${SEED:-42}"
JUSTIFICATION_CALL_BUDGET="${JUSTIFICATION_CALL_BUDGET:-256}"
MODELS="${MODELS:-oracle majority lexical}"
# Set to 1 for ontologies that miss OWL 2 EL by a few axioms (ELK is not complete outside
# EL, so a non-EL ontology is rejected rather than silently mis-labelled).
EL_FRAGMENT="${EL_FRAGMENT:-0}"

EL_FLAG=()
[[ "$EL_FRAGMENT" == "1" ]] && EL_FLAG=(--el-fragment)

PY="${PY:-python}"
[[ -x .venv/bin/python ]]        && PY=.venv/bin/python
[[ -x .venv/Scripts/python.exe ]] && PY=.venv/Scripts/python.exe

CERT="bash scripts/certifier.sh"
DATASET="data/certified/$ONTOLOGY_ID/benchmark.jsonl"

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "0. Toolchain"
if [[ ! -f java/owl-certifier/target/owl-certifier.jar ]]; then
  bash scripts/build_java.sh -q package -DskipTests
fi
$PY -c "import owl_equivariance" 2>/dev/null || $PY -m pip install -q -e .

step "1. Fetch and freeze the source ontology"
if [[ ! -f "$ONTOLOGY_FILE" ]]; then
  mkdir -p "$(dirname "$ONTOLOGY_FILE")"
  curl -fsSL --retry 3 -o "$ONTOLOGY_FILE" "$ONTOLOGY_URL"
fi
$CERT inspect --input "$ONTOLOGY_FILE" --root-only \
  --output "data/normalized/$ONTOLOGY_ID.stats.json"

step "2. Certify the transforms before trusting anything built from them"
mkdir -p "reports/$ONTOLOGY_ID"
IFS=',' read -ra CONDS <<< "$CONDITIONS"
for c in "${CONDS[@]}"; do
  [[ "$c" == "C0" ]] && continue
  $CERT validate-orbit --source "$ONTOLOGY_FILE" --root-only --condition "$c" \
    --sample 300 --seed "$SEED" \
    --report "reports/$ONTOLOGY_ID/$c.validation.json"
done

step "3. Build the benchmark"
$CERT build-dataset \
  --input "$ONTOLOGY_FILE" --root-only "${EL_FLAG[@]}" \
  --ontology-id "$ONTOLOGY_ID" \
  --ontology-version "$ONTOLOGY_VERSION" \
  --output "$DATASET" \
  --report "data/certified/$ONTOLOGY_ID/build_report.json" \
  --checkpoint "data/certified/$ONTOLOGY_ID/build_checkpoint.json" \
  --mappings-dir "data/certified/$ONTOLOGY_ID/mappings" \
  --positives "$POSITIVES" --negatives "$NEGATIVES" \
  --distractors "$DISTRACTORS" --max-context-axioms "$MAX_CONTEXT" \
  --justification-call-budget "$JUSTIFICATION_CALL_BUDGET" \
  --seed "$SEED" --conditions "$CONDITIONS"

step "4. Validation gates"
# Fails on empty contexts, size imbalance between labels, condition leakage, identical
# seed mappings, incomplete orbits and dangling mapping manifests -- not just on whether
# the labels are logically certified.
$PY -m owl_equivariance.cli validate --dataset "$DATASET" --expect-conditions "$CONDITIONS"

step "5. Tokenization controls"
# Non-fatal: with a proxy counter the matching check reports NOT ASSESSABLE (exit 2) rather
# than certifying a control it cannot actually check. Set TOKENIZER=hf:<id> for real counts.
$PY -m owl_equivariance.cli tokens --dataset "$DATASET" \
  --tokenizer "${TOKENIZER:-chars}" --output-dir "reports/$ONTOLOGY_ID" || true

step "6. Record the environment"
bash scripts/record_environment.sh "reports/$ONTOLOGY_ID/environment.json"

step "7. Inference and evaluation"
for model in $MODELS; do
  slug="$(echo "$model" | tr ':/' '__')"
  raw="data/predictions/$ONTOLOGY_ID.$slug.jsonl"
  validated="data/predictions/$ONTOLOGY_ID.$slug.validated.jsonl"

  echo "--- $model ---"
  $PY -m owl_equivariance.cli infer \
    --dataset "$DATASET" --model "$model" \
    --style structured_proof --output "$raw"

  # Symbolic validation of the cited axiom sets: this is what makes CAIP measurable.
  $CERT validate-support --dataset "$DATASET" --predictions "$raw" --output "$validated"

  $PY -m owl_equivariance.cli evaluate \
    --dataset "$DATASET" --predictions "$validated" \
    --output-dir "reports/$ONTOLOGY_ID/$slug"
done

step "Done"
echo "dataset: $DATASET"
echo "reports: reports/$ONTOLOGY_ID/"
