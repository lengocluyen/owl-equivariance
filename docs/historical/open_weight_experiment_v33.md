# Open-weight confirmatory protocol v3.3

**Protocol:** `owleq-jws-2026-08-v33`  
**Frozen:** 2026-08-18; deterministic generator amendment 2026-08-25, both before
confirmatory LLM inference  
**Status:** capacity and generator-runtime amendments frozen; final source panel not yet frozen

## Pre-confirmatory generator amendment (2026-08-25)

No confirmatory LLM request had been made and no confirmatory outcome was inspected. Two
deterministic Uberon source builds were externally terminated after multiple days without
producing `benchmark.jsonl`, `build_report.json`, or a controlled exit code. A third launcher
failure (`/usr/bin/time` absent, exit 127) never started Java and is infrastructure provenance,
not an experimental result. Kernel and cgroup audits recorded no OOM, the host did not reboot,
and disk capacity was ample. The surviving GC log reached 78,148 young collections while live
heap repeatedly returned to about 2.6 GiB. This identifies allocation/computation scaling rather
than a memory leak or insufficient heap.

Inspection of `Justifier` found that the former deletion algorithm created a new OWL manager,
ontology, and ELK reasoner for each attempted axiom removal. `QueryGenerator` also materialized
and sorted the complete inferred subclass closure before examining at most eight times the
requested positive count. These are deterministic implementation costs and reveal no model
outcome.

`owl-certifier` 0.2.0 prospectively freezes the following replacements:

- deterministic QuickXplain minimal-justification extraction;
- a maximum of 256 uncached ELK classifications per candidate;
- exhausted candidates are dropped and counted, never emitted with partial support;
- one OWL manager and mutable working ontology per justification search, an exact-subset cache,
  and a fresh ELK reasoner for every uncached subset (no reliance on incremental reasoning);
- inferred candidates ranked by
  `SHA256(seed + "\\n" + canonical_query)` and the lowest
  `max(8 * requested_positives, 200)` retained;
- atomic checkpoint JSON before and during every long build stage;
- build reports record candidate, reasoner-call, reasoner-build, cache-hit, and budget-exhaustion
  counts.

QuickXplain changes computational strategy, not the logical acceptance rule: every returned
support still entails the query and is subset-minimal, and every emitted label is independently
checked against the supplied transformed context. A deterministic synthetic regression embeds a
seven-axiom proof in 199 logical axioms and requires fewer than half as many classifications as
linear deletion, plus independent minimality checks. Budget exhaustion has a separate regression
that must return no partial support.

Because seeded bottom-k selection changes which eligible queries are considered, **all
confirmatory sources—including GO, ENVO, and Schema.org—must be regenerated with certifier
0.2.0 and the frozen 256-call budget before the final panel is frozen**. Discovery CL/PO artifacts
remain unchanged and discovery-only. No old and new generator artifacts may be mixed in the
v3.3 confirmatory panel.

## Why this amendment is prospective

V3.2 discovery results and deterministic oracle checks were available. No response from a
confirmatory model/dataset cell had been requested or inspected. The only new information
used for this amendment was certified source capacity:

| Source | Certified base items | Decision under v3.3 |
|---|---:|---|
| GO | 162 | eligible |
| ENVO | 164 | eligible |
| Schema.org 30.0 | 300 | eligible |
| SAREF Core 4.1.1 | 16 | external probe only |
| SSN | 0 | rejected |

These counts were observed under the pre-0.2.0 builder and justified the capacity threshold only.
They are not final v3.3 panel counts. GO, ENVO, and Schema.org return to `candidate` status until
they are regenerated and pass every gate under the amended generator.

The former six-source, 200-item-per-source gate excluded two complete, balanced,
reasoner-certified sources for an arbitrary shortfall. V3.3 replaces it with a design that
increases source-level replication while retaining the discovery-derived power target.

## Frozen capacity rules

The primary confirmatory panel must satisfy all of the following before inference:

- at least eight distinct ontology/material sources;
- at least 150 certified base items per source;
- at least 1,320 base items in total;
- exactly one complete member of each base-item orbit for
  `C0,C1,C2,C3,C4,C4S2,C5,C6,C7,C8,C9`;
- no repeated ontology id, dataset path, or base-item id across sources;
- no CL, PO, or toy data in the confirmatory panel;
- all ordinary dataset publication gates, mapping-manifest checks, certified labels, and
  context-balance checks pass.

With GO, ENVO, and Schema.org contributing 626 items, five additional sources at the
150-item minimum produce 1,376 items and pass both lower bounds. SAREF and SSN do not count
toward the primary panel.

The exact panel is a separate immutable JSON artifact. The freeze command records the
manifest hash, ordered dataset paths, dataset and build-report hashes, ontology versions,
source hashes, task counts, label counts, and the explicit assertion that confirmatory
outcomes remain unseen. It refuses to overwrite an existing artifact.

## Frozen inference design

The model matrix and inference settings are unchanged from the calibrated v3 family except
for v3.3 result identifiers. Each model receives one response for every item. A deterministic
20% stratified orbit subset receives response indices 1 and 2 in addition to the primary
response. Invalid output remains incorrect in the headline denominator. API errors are not
retried automatically.

At the minimum 1,320-item panel, the planned volume is:

- 14,520 primary prompts per model;
- 2,904 prompts in the 20% repeat subset, each receiving two additional responses;
- 20,328 calls per model;
- 121,968 calls across six models.

## Preregistered confirmatory analysis

The primary model is a binomial logistic mixed model fitted with Laplace approximation:

```text
correct ~ condition + task_type + proof_depth_z + context_axioms_z + token_delta_z
          + (1 | ontology_id) + (1 | ontology_id:base_item_id)
```

The implementation is `scripts/analyze_confirmatory_v33.R` using `lme4::glmer` with
`nAGQ=1`. Per-model fits are primary; the pooled model includes condition-by-model
interactions. Structured-output validity (`parsed`) is fitted as a separate outcome rather
than conditioning correctness on successful parsing. Holm adjustment is applied within the
condition-versus-C0 coefficient family.

Sensitivity analyses are:

1. logistic GEE clustered on the ontology-qualified base item, with ontology fixed effects;
2. the Python variational binomial mixed model with ontology and base-item random intercepts.

No observed confirmatory effect is used for a post-hoc power calculation. The sample target
is frozen from discovery-only simulation.

## Freeze the final panel

First run a non-outcome performance probe for every large source. This writes separate staging
artifacts and cannot enter the confirmatory panel:

```bash
bash scripts/build_java.sh -q package

bash scripts/certifier.sh build-dataset \
  --input data/raw/uberon-v2026-06-23.owl \
  --root-only --el-fragment \
  --ontology-id uberon-probe \
  --ontology-version uberon-v2026-06-23 \
  --output results/v33_capacity_probes/uberon/benchmark.jsonl \
  --report results/v33_capacity_probes/uberon/build_report.json \
  --checkpoint results/v33_capacity_probes/uberon/build_checkpoint.json \
  --mappings-dir results/v33_capacity_probes/uberon/mappings \
  --positives 4 --negatives 4 \
  --distractors 12 --max-context-axioms 45 \
  --justification-call-budget 256 \
  --seed 42 --conditions C0
```

The checkpoint must finish with `status: COMPLETE`. Review elapsed time, candidate counts,
reasoner calls, and budget exhaustion before approving the full source build. The full build uses
100 requested positives, 100 requested negatives, all eleven conditions, an attempt-specific
checkpoint, and new output paths. Never reuse an attempt log or checkpoint.

The version-pinned wrapper performs those checks and keeps probes separate from final artifacts:

```bash
ONTOLOGY_ID=uberon \
ONTOLOGY_FILE=data/raw/uberon-v2026-06-23.owl \
ONTOLOGY_VERSION=uberon-v2026-06-23 \
RUN_ID=uberon-v020-probe-01 \
  bash scripts/build_v33_candidate.sh probe

# Only after reviewing the probe:
V33_BUILD_APPROVED=YES \
ONTOLOGY_ID=uberon \
ONTOLOGY_FILE=data/raw/uberon-v2026-06-23.owl \
ONTOLOGY_VERSION=uberon-v2026-06-23 \
RUN_ID=uberon-v020-full-01 \
  bash scripts/build_v33_candidate.sh full
```

Final 0.2.0 sources live under `data/certified_v33/<ontology>/`; the pre-amendment
`data/certified/<ontology>/` files remain untouched for auditability.

Do not run this with placeholders. Supply eight or more certified files in the intended
analysis order:

```bash
source .venv/bin/activate

DATASETS=(
  data/certified_v33/go/benchmark.jsonl
  data/certified_v33/envo/benchmark.jsonl
  data/certified_v33/schemaorg/benchmark.jsonl
  data/certified_v33/SOURCE4/benchmark.jsonl
  data/certified_v33/SOURCE5/benchmark.jsonl
  data/certified_v33/SOURCE6/benchmark.jsonl
  data/certified_v33/SOURCE7/benchmark.jsonl
  data/certified_v33/SOURCE8/benchmark.jsonl
)

python -m owl_equivariance.cli freeze-confirmatory-panel \
  --manifest configs/open_weight_experiment_v33.yaml \
  --dataset "${DATASETS[@]}" \
  --output configs/confirmatory_panel_v33.json \
  --acknowledge-no-confirmatory-outcomes
```

Review and version the JSON, then independently recompute every gate:

```bash
python -m owl_equivariance.cli verify-confirmatory-panel \
  --manifest configs/open_weight_experiment_v33.yaml \
  --panel configs/confirmatory_panel_v33.json \
  --dataset "${DATASETS[@]}"
```

## Pre-inference checks and execution

The primary GLMM is a required dependency and is checked before the runner starts inference:

```bash
command -v Rscript
Rscript -e 'stopifnot(requireNamespace("lme4", quietly=TRUE))'
```

Run a new response-channel diagnostic under the v3.3 identifiers:

```bash
RUN_ID=owleq-jws-2026-08-v33-diagnostic-01 \
  bash scripts/run_lmstudio_v33.sh diagnostic
```

After reviewing that run and the frozen panel, execute the confirmatory matrix:

```bash
DATASETS_CSV="$(IFS=,; echo "${DATASETS[*]}")" \
CONFIRMATORY_PANEL_FILE=configs/confirmatory_panel_v33.json \
CONFIRMATORY_APPROVED=YES \
REQUIRE_WEIGHTS_HASH=1 \
RUN_ID=owleq-jws-2026-08-v33-confirmatory-01 \
  bash scripts/run_lmstudio_v33.sh confirmatory
```

The runner verifies the panel and all hashes again, copies the panel into run provenance,
loads and hashes one local model at a time, retains raw responses, validates cited supports,
fits the preregistered GLMM, runs GEE sensitivity models, and deliberately skips post-hoc
confirmatory power estimation.
