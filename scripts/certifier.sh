#!/usr/bin/env bash
# Run the owl-certifier jar with the noise suppressed.
#
# Guava's AbstractFuture touches sun.misc.Unsafe, and ELK ships a log4j config that warns on
# every start. Neither affects results, but both drown the actual output.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAR="$REPO_ROOT/java/owl-certifier/target/owl-certifier.jar"

if [[ ! -f "$JAR" ]]; then
  echo "jar not built; run scripts/build_java.sh package -DskipTests" >&2
  exit 1
fi

JAVA_BIN="java"
if [[ -n "${OWLEQ_JAVA_HOME:-}" ]]; then
  JAVA_BIN="$OWLEQ_JAVA_HOME/bin/java"
fi

"$JAVA_BIN" \
  --sun-misc-unsafe-memory-access=allow \
  -Dorg.slf4j.simpleLogger.defaultLogLevel=warn \
  -jar "$JAR" "$@" 2> >(grep -vE "^(WARNING:|log4j:)" >&2)
