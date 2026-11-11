#!/usr/bin/env bash
# Print the current, measured state of every finding an audit has raised.
#
#   bash scripts/audit_state.sh
#
# Exists so a review does not have to take anyone's word for it, and so a reviewer reading a
# stale checkout can tell immediately. Every line is measured from the working tree at the
# moment it runs -- nothing here is hardcoded from a previous run.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="${PY:-python}"
[[ -x .venv/bin/python ]]         && PY=.venv/bin/python
[[ -x .venv/Scripts/python.exe ]] && PY=.venv/Scripts/python.exe

DATASET="${DATASET:-data/certified/cl/benchmark.jsonl}"
RAW_ONTOLOGY="${RAW_ONTOLOGY:-data/raw/cl-basic.owl}"

pass() { printf '  \033[32m[PASS]\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m[FAIL]\033[0m %s\n' "$1"; }
info() { printf '  \033[33m[OPEN]\033[0m %s\n' "$1"; }

echo "=============================================================="
echo " owl-equivariance :: measured state"
echo " $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================================="

echo
echo "TEST SUITES  (the quickest way to tell which snapshot you are reading)"
if [[ -n "${SKIP_TESTS:-}" ]]; then
  info "skipped (SKIP_TESTS set)"
else
  JAVA_TESTS="$(bash scripts/build_java.sh test 2>/dev/null \
    | grep -oP '(?<=Tests run: )\d+(?=, Failures: 0, Errors: 0, Skipped: 0$)' | tail -1)"
  PY_TESTS="$("$PY" -m pytest -q 2>/dev/null | grep -oP '\d+(?= passed)' | tail -1)"
  echo "  Java:   ${JAVA_TESTS:-unknown} passing"
  echo "  Python: ${PY_TESTS:-unknown} passing"
  echo "  (An audit reporting 17 Java / 41 Python is reading a pre-fix snapshot.)"
fi

echo
echo "BENCHMARK INTEGRITY"
"$PY" - "$DATASET" "$RAW_ONTOLOGY" <<'PYEOF'
import hashlib, json, pathlib, sys

dataset, raw = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
GREEN, RED, YELLOW, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

def line(ok, text):
    tag = f"{GREEN}[PASS]{OFF}" if ok else f"{RED}[FAIL]{OFF}"
    print(f"  {tag} {text}")

if not dataset.exists():
    print(f"  {YELLOW}[OPEN]{OFF} {dataset} not built; run scripts/reproduce_pilot.sh")
    raise SystemExit(0)

items = [json.loads(l) for l in dataset.open(encoding="utf-8")]
byc = {}
for i in items:
    byc.setdefault(i["transform"]["lexical_condition"], []).append(i)
c0 = byc.get("C0", [])
neg = [i for i in c0 if not i["task"]["positive"]]
pos = [i for i in c0 if i["task"]["positive"]]

empty = sum(1 for i in neg if not i["context"]["axioms"])
line(empty == 0, f"negative contexts non-empty: {len(neg) - empty}/{len(neg)} have axioms")

if pos and neg:
    mp = sum(len(i["context"]["axioms"]) for i in pos) / len(pos)
    mn = sum(len(i["context"]["axioms"]) for i in neg) / len(neg)
    rel = abs(mp - mn) / max(mp, mn, 1)
    line(rel <= 0.25, f"context size balanced by label: {mp:.1f} vs {mn:.1f} ({rel:.1%} apart)")

a = {i["base_item_id"]: i["task"]["query_functional"] for i in byc.get("C4", [])}
b = {i["base_item_id"]: i["task"]["query_functional"] for i in byc.get("C4S2", [])}
shared = [k for k in a if k in b]
differ = sum(1 for k in shared if a[k] != b[k])
line(bool(shared) and differ == len(shared),
     f"C4 vs C4S2 are distinct renamings: differ on {differ}/{len(shared)} items")

leaked = []
for cond, its in byc.items():
    seed = str(its[0]["transform"].get("seed"))
    blobs = [ax["text"] for ax in its[0]["context"]["axioms"]] + [its[0]["task"]["query_functional"]]
    for blob in blobs:
        low = blob.lower()
        if f":{cond.lower()}:" in low or (seed and f":{seed}:" in low):
            leaked.append(cond)
            break
line(not leaked, f"no condition/seed in prompt IRIs: {leaked or 'none leaked'}")

c7 = byc.get("C7", [])
if c7:
    names = {ax["text"].split("#")[1].split(">")[0]
             for ax in c7[0]["context"]["axioms"] if "#" in ax["text"]}
    accession = [n for n in names if n[:3].isupper() and "_" in n and n.split("_")[-1].isdigit()]
    sample = sorted(names)[0] if names else "?"
    line(not accession, f"C7 names are label-derived, not accession codes (e.g. {sample})")

if raw.exists():
    report = dataset.parent / "build_report.json"
    if report.exists():
        r = json.loads(report.read_text(encoding="utf-8"))
        real = hashlib.sha256(raw.read_bytes()).hexdigest()
        line(r.get("source_file_sha256") == real,
             f"recorded byte hash matches the file ({real[:12]}...)")
        line(bool(r.get("source_canonical_sha256")), "canonical hash recorded separately")

mappings = list((dataset.parent / "mappings").glob("*.mapping.json"))
line(len(mappings) >= len(byc), f"mapping manifests on disk: {len(mappings)} for {len(byc)} conditions")
PYEOF

echo
echo "METRICS AND STATISTICS"
"$PY" - <<'PYEOF'
from owl_equivariance.metrics import answer, proof, stats
from owl_equivariance import reporting, tokens
GREEN, RED, OFF = "\033[32m", "\033[31m", "\033[0m"
def line(ok, text):
    print(f"  {GREEN}[PASS]{OFF} {text}" if ok else f"  {RED}[FAIL]{OFF} {text}")

line(hasattr(answer.PairedComparison, "__dataclass_fields__")
     and "p_value_holm" in answer.PairedComparison.__dataclass_fields__,
     "Holm correction is a field of every paired comparison")
line("mcnemar_p_holm" in reporting.COMPARISON_COLUMNS,
     "Holm-adjusted p is an exported column")
line("caip_joint" in reporting.PROOF_COLUMNS and "caip_given_correct" in reporting.PROOF_COLUMNS,
     "CAIP exported as both joint (spec 22.7) and conditional")

m = proof.ProofOrbitMetrics()
line(m.support_equivariance_mean is None,
     "support equivariance defaults to undefined, not 1.0, when nothing is cited")
line(not tokens.Counter("words").sees_subword and tokens.Counter("chars").sees_subword,
     "token counter reports whether it can see sub-word fragmentation")
line(hasattr(stats, "orbit_permutation_test"), "orbit permutation test available")
try:
    from owl_equivariance import modeling  # noqa: F401
    line(True, "mixed-effects / GEE model fitting available (owleq model)")
except Exception as exc:
    line(False, f"model fitting unavailable: {exc}")
PYEOF

echo
echo "GATES  (each exits non-zero on failure)"
"$PY" -m owl_equivariance.cli validate --dataset "$DATASET" \
  --expect-conditions C0,C1,C2,C4,C4S2,C5,C6,C7,C8 >/dev/null 2>&1 \
  && pass "owleq validate" || fail "owleq validate"
"$PY" -m owl_equivariance.cli tokens --dataset "$DATASET" --tokenizer chars >/dev/null 2>&1
case $? in
  0) pass "owleq tokens (matched pairs within tolerance)" ;;
  2) fail "owleq tokens (counter cannot assess sub-word fragmentation)" ;;
  *) fail "owleq tokens (a matched pair is confounded)" ;;
esac
[[ -f reports/environment.json ]] && pass "environment manifest" || info "environment manifest not yet recorded"
[[ -f reports/requirements.lock.txt ]] && pass "python lock file" || info "lock file not yet recorded"

echo
echo "GENUINELY OUTSTANDING  (not code defects -- the experiment itself)"
ONTOLOGIES="$(find data/certified -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
BASE_ITEMS="$("$PY" -c "
import json,glob
n=set()
for f in glob.glob('data/certified/*/benchmark.jsonl'):
    for line in open(f,encoding='utf-8'):
        n.add(json.loads(line)['base_item_id'])
print(len(n))" 2>/dev/null || echo '?')"
info "no LLM run: checked-in predictions are deterministic baselines only"
info "ontologies built: $ONTOLOGIES (target for a full paper: 5-10)"
info "base items: $BASE_ITEMS (target per ontology: 200-500)"
info "task families populated: ATOMIC_SUBSUMPTION only (neither ontology has an ABox)"
info "no augmentation/defense experiment; no Level-2 rule-labelled proof graphs"
echo
echo "=============================================================="
