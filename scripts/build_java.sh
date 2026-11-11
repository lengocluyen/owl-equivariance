#!/usr/bin/env bash
# Build the Java symbolic layer.
#
# Honours OWLEQ_JAVA_HOME / OWLEQ_MVN if the toolchain was installed by
# scripts/bootstrap_toolchain.sh into a non-standard location.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POM="$REPO_ROOT/java/owl-certifier/pom.xml"

if [[ -n "${OWLEQ_JAVA_HOME:-}" ]]; then
  export JAVA_HOME="$OWLEQ_JAVA_HOME"
  export PATH="$JAVA_HOME/bin:$PATH"
fi

MVN="${OWLEQ_MVN:-mvn}"
MVN_ARGS=()
if [[ -n "${OWLEQ_M2:-}" ]]; then
  MVN_ARGS+=("-Dmaven.repo.local=$OWLEQ_M2")
fi

exec "$MVN" -f "$POM" "${MVN_ARGS[@]}" "$@"
