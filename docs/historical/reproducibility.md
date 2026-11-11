# Reproducibility

## What is deterministic, and what is not

| Stage | Deterministic? | Determined by |
|---|---|---|
| Ontology normalization + hashing | yes | source file bytes |
| Query generation | yes | (ontology, seed, counts) |
| Context construction | yes | (ontology, seed, query, distractor budget) |
| Signature isomorphisms | yes | (ontology, operator, seed) |
| Benchmark JSONL | yes | all of the above |
| Support validation | yes | (dataset, predictions) |
| Metrics and tables | yes | (dataset, predictions, bootstrap seed) |
| **Model inference** | **no** | the model |

Everything except inference reproduces byte for byte. Rerunning `reproduce_pilot.sh` on the
same inputs yields identical files and identical SHA-256 hashes.

Determinism is engineered, not assumed. Entities are sorted by IRI before index assignment,
axioms are sorted by canonical rendering before shuffling with a fixed seed, JSON keys are
emitted in sorted order, and all files are written UTF-8 with Unix line endings.

## Reference baselines are deterministic; models are not

`oracle`, `majority` and `lexical` are pure functions of the item. They should reproduce
exactly, and a change in their numbers means the *dataset* changed.

Real models do not reproduce exactly, and this pipeline does not pretend otherwise. The
spec asks for temperature 0; current Claude models **reject** `temperature`, `top_p` and
`top_k` with a 400, so that lever does not exist. What the runner does instead:

- a fixed prompt, byte-identical across items except for the item itself;
- `output_config.format` constraining the reply to the response schema;
- one response per item.

Runs are therefore "one greedy-intent sample per item", not "reproducible". Residual
variation is a property of the measurement and should be reported as such — the honest way
to bound it is to repeat a run and report the spread, not to claim a determinism the API
does not offer.

## Recording a run

`scripts/record_environment.sh` writes the environment manifest and a pip lock file;
`build_report.json` carries the dataset provenance. Both are produced automatically by
`reproduce_pilot.sh`.

**Dataset** — ontology id, pinned version, ontology IRI, OWL profile, seed, condition list,
distractor kind and budget, max context size, target namespace, per-condition item counts,
per-label context-size distributions, candidate-sampling algorithm, justification algorithm,
per-candidate reasoner-call budget, reasoner-call/build/cache counters, budget-exhaustion count,
and the paths of the mapping manifests. All in
`data/certified/<id>/build_report.json`.

**Build checkpoint** — `build_checkpoint.json` is an atomically replaced runtime-status file,
not a scientific result and not a resumable cache. It records the PID, immutable build
parameters, current long-running stage, timestamps, terminal status, and final counters. A
missing terminal update after the process disappears is evidence of external termination. Use a
new checkpoint path for every attempted publication build; never append multiple attempts into
one provenance record.

**Two hashes, and they are not interchangeable.** The report records both:

- `source_file_sha256` — the SHA-256 of the **file's bytes**. This is what an ontology
  publisher publishes and what a third party can verify against the download. Use this to
  answer "did we use the same file?"
- `source_canonical_sha256` — the SHA-256 of the deterministic serialization. Stable across
  serialization formats and RDF/XML triple ordering, so it answers "did we use the same
  *ontology*?" even when the bytes differ.

Recording only the canonical hash — as an earlier version did — looks like a checksum but
cannot be checked against anything anyone else publishes.

**Mappings** — one manifest per condition under `data/certified/<id>/mappings/`, holding the
full entity-to-entity mapping, the operator, the seed and the annotation policy. These are
what the dataset's `mapping_id` fields refer to; without them the renaming cannot be
inverted or audited. `owleq validate` fails if a referenced manifest is missing.

**Model** — exact model id (never an alias that can move), prompt style, `max_tokens`,
effort level, thinking mode, and for local models the revision hash, tokenizer revision,
quantization, inference engine, GPU type and precision.

**Environment** — JDK version, OWLAPI and ELK versions, Python version, dependency lock
file, and the `owl-certifier` jar's build.

## Pinned dependencies, and why

```
OWLAPI  4.1.3     ELK 0.4.3 is compiled against it and declares it `provided`.
ELK     0.4.3     Latest release on Maven Central under org.semanticweb.elk.
Guice   5.1.0     OWLAPI wires its parsers through Guice; the 4.0 it pulls bundles a
                  cglib that cannot generate classes on a modern JVM. 5.1 dropped cglib
                  for ASM and still uses javax.inject, which is what OWLAPI compiles
                  against -- the one version that satisfies both ends.
Guava   32.1.3    Guice 5.1 calls Guava APIs newer than the Guava 18 OWLAPI pins.
Jackson 2.13.5    Declared as a full set (databind + core + annotations) so Maven's
                  nearest-wins mediation cannot split the version across artifacts.
```

Do not bump OWLAPI or ELK independently. The pairing is the constraint, not either version.

## Common failure modes

**`ExceptionInInitializerError` in `com.google.inject.internal.cglib`** — the Guice
override was lost. Check the explicit `com.google.inject:guice` dependency.

**`NoSuchMethodError` on `Preconditions.checkArgument`** — Guice 5.1 with old Guava. Check
the explicit Guava dependency.

**`cannot access com.fasterxml.jackson.core.exc.StreamReadException`** — Jackson versions
split across artifacts. All three Jackson artifacts must be declared explicitly.

**Profile reported as `NONE` on a valid-looking ontology** — usually undeclared annotation
properties, which violate OWL 2 DL. The violation list is in the `inspect` output. This is a
real finding about the ontology, not a tool bug.

**`build-dataset` exits 3** — a label changed under a transform. This is a bug in the
transform, and the dataset is deliberately not written: shipping it would poison every
downstream number. The first ten failures are printed.

**`owleq validate` exits 1 on a dataset whose labels are all correct** — that is the point.
The gates check *experimental adequacy*, not just logic:

| Gate | What it catches |
|---|---|
| empty contexts | items answerable without reading any axiom |
| context size balance | length alone predicting the label |
| condition leakage | the condition id or seed visible in the prompt's IRIs |
| distinct seed mappings | "two seeds" that produce the same renaming |
| orbit completeness | a condition missing from some orbits, inflating robustness |
| mapping manifests | `mapping_id` pointing at a file that does not exist |

A dataset can pass every logical check and still be worthless. These gates exist because
that happened: an earlier build shipped 59 of 60 negative items with zero axioms and
validated clean.

## Pre-experiment gates

Four commands, all exiting non-zero on failure, all cheap. Run them before any paid
inference:

```bash
owleq validate --dataset <benchmark> --expect-conditions <list>   # adequacy gates
owleq tokens   --dataset <benchmark> --tokenizer hf:<model-id>    # tokenization controls
owleq split    --dataset <benchmark> --output <splits> --assign a=train b=test
bash scripts/record_environment.sh reports/environment.json
```

`owleq tokens` exits **2** — not 0 — when the counter cannot see inside a whitespace token.
Fragmentation is sub-word, so a word count reports every de-lexicalized condition as
identical regardless of the truth; certifying a control that was never checked is worse than
reporting nothing. Use `--tokenizer hf:<model-id>`, or `chars` as a crude but non-blind
stand-in.

## Raw outputs

`owleq infer` **keeps raw responses by default** (`--drop-raw` to opt out). They are a
required release artifact and the only way to re-parse a run without paying for it again —
if the parser is later found to mishandle a format, a stored raw response can be re-parsed;
a discarded one cannot.

For nondeterministic backends use `--repeats N`. Repeats are tagged, not averaged, and the
command reports what fraction of items changed answer across runs — the honest way to bound
residual variation rather than assume it away.

## Artifacts to release

Source ontology manifests with checksums and licenses; the benchmark JSONL; mapping
manifests per condition; the orbit validation reports; prompts; raw model outputs where
licenses permit; parsed and support-validated predictions; evaluation scripts; the toolchain
bootstrap; dependency lock files; hardware metadata; and every seed.

## Regenerating from scratch

```bash
bash scripts/bootstrap_toolchain.sh && source .owleq-toolchain.env
bash scripts/build_java.sh package        # runs the Java test suite
python -m venv .venv && ./.venv/bin/pip install -e '.[dev]'
./.venv/bin/pytest -q                     # Python test suite
bash scripts/reproduce_pilot.sh
```

The Java suite is not optional scaffolding: it contains the constructor round-trip,
punning, module query-completeness and distractor-invariance checks that back the
certificates. A failure there invalidates the dataset, not just the build.
