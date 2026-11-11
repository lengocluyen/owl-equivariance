#!/usr/bin/env bash
# Thin, version-pinned entry point for the prospective v3.3 open-weight protocol.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PROTOCOL_ID="${PROTOCOL_ID:-owleq-jws-2026-08-v33}"
export MANIFEST="${MANIFEST:-configs/open_weight_experiment_v33.yaml}"
export MODEL_MATRIX_FILE="${MODEL_MATRIX_FILE:-configs/lmstudio_models_v33.tsv}"

exec bash scripts/run_lmstudio_publication.sh "${1:-diagnostic}"
