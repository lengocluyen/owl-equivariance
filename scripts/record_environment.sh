#!/usr/bin/env bash
# Capture the exact environment a run was produced in (spec section 36.1).
#
#   bash scripts/record_environment.sh reports/cl/environment.json
#
# Writes a machine-readable manifest and, alongside it, a pip lock file. Both belong with
# any released result: without them "we used Python 3.11 and ELK" is not a reproduction
# recipe.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO_ROOT/reports/environment.json}"
mkdir -p "$(dirname "$OUT")"

PY="${PY:-python}"
[[ -x "$REPO_ROOT/.venv/bin/python" ]]         && PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$REPO_ROOT/.venv/Scripts/python.exe" ]] && PY="$REPO_ROOT/.venv/Scripts/python.exe"

JAVA_BIN="java"
[[ -n "${OWLEQ_JAVA_HOME:-}" ]] && JAVA_BIN="$OWLEQ_JAVA_HOME/bin/java"

LOCK="$(dirname "$OUT")/requirements.lock.txt"
"$PY" -m pip freeze --exclude-editable > "$LOCK" 2>/dev/null || true

jq_escape() { "$PY" -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'; }

JAVA_VERSION="$("$JAVA_BIN" -version 2>&1 | head -1 | jq_escape)"
PY_VERSION="$("$PY" --version 2>&1 | jq_escape)"
OS_INFO="$(uname -sro 2>/dev/null || uname -s | jq_escape)"
# The repo may not be under version control yet; a missing commit is worth recording, not
# worth aborting over. Note `pipefail` is on, so the git call must be guarded inside the
# pipeline rather than after it.
GIT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="$( { git -C "$REPO_ROOT" status --porcelain 2>/dev/null || true; } | wc -l | tr -d ' ')"

# Dependency versions come from the POM rather than being restated, so the manifest cannot
# drift from what actually builds.
read_pom() { grep -oP "(?<=<$1>)[^<]+" "$REPO_ROOT/java/owl-certifier/pom.xml" | head -1; }

CPU_MODEL="$("$PY" -c "import platform; print(platform.processor() or platform.machine())")"
CPU_COUNT="$("$PY" -c "import os; print(os.cpu_count())")"

cat > "$OUT" <<EOF
{
  "recorded_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "git": { "commit": "$GIT_COMMIT", "uncommitted_files": $GIT_DIRTY },
  "os": $( printf '%s' "$OS_INFO" | jq_escape ),
  "hardware": { "cpu": $( printf '%s' "$CPU_MODEL" | jq_escape ), "cpu_count": $CPU_COUNT },
  "java": {
    "runtime": $JAVA_VERSION,
    "owlapi": "$(read_pom owlapi.version)",
    "elk": "$(read_pom elk.version)",
    "jackson": "$(read_pom jackson.version)",
    "compiler_release": "$(read_pom maven.compiler.target)"
  },
  "python": { "version": $PY_VERSION, "lock_file": "$(basename "$LOCK")" },
  "note": "GPU/accelerator details must be added by hand for local-model runs."
}
EOF

echo "environment manifest: $OUT"
echo "python lock:          $LOCK"
