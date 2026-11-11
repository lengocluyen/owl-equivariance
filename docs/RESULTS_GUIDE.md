# Guide to the existing results

Protocol: `owleq-jws-2026-08-v33`. Collection: `owleq-jws-2026-08-v33-confirmatory-01`.

## Small files in Git

`results/v33/models/<model>/<source>_/answer_by_condition.csv` contains existing answer counts and rates. `orbit_metrics.json`, `proof_by_condition.csv`, and `seed_disagreement.csv` contain the family, support, and opaque-seed summaries. The `stability/` subdirectory contains the existing three-execution summaries. Baseline summaries are under `results/v33/baselines/`. HP outcome summaries are included without its transformed ontology text.

`figures/figure_data/` contains the unchanged numerical inputs to the manuscript figures. The figure scripts are supplied as provenance but were not rerun for the deposit.

## Large evidence asset

After extraction, paths retain the research layout:

- `data/certified_v33/<source>/`: benchmark items, mappings, build reports, and checkpoints for the eight redistributable sources. HP has only selected build/hash metadata.
- `data/predictions/<run>/`: raw and validated primary/repeat records for those eight sources, including existing baseline records where present. HP prediction files are omitted.
- `reports/<run>/primary_analysis.csv`: the original primary outcome export for all nine sources, including HP. It contains labels, identifiers, and scalar features, not the model-visible ontology contexts. Its historical `token_delta` column is not a valid adjustment covariate.
- `reports/<run>/models/` and `baselines/`: unmodified report files. Historical inferential files retained here are not article evidence.
- `reports/<run>/provenance/`: frozen panel, manifests, model hashes, software/runtime records, and post-failure continuation records. The HP repeat-context JSONL is omitted, while its manifest is retained.
- `release/ARTIFACT_MANIFEST.json`: included file hashes and exact omitted-file identities/hashes.

The asset's membership differs from the private original evidence bundle. The original `SHA256SUMS` is retained as historical provenance and mentions files not redistributed. Use the public artifact manifest to verify the public package; do not interpret missing HP files as accidental corruption.

## Populations and conventions

| Measure | Population and convention |
|---|---|
| Answer accuracy | Rendered responses; invalid outputs count as incorrect |
| All-condition accuracy / ROA | All 1,460 base families per model; correct in every one of the eleven conditions |
| Family consistency | Complete families whose recorded label values all agree; an all-invalid-label family can satisfy this implementation criterion |
| Proof-valid family accuracy / PVOA | The 730 gold-entailed base families; correct answers and valid cited supports in every condition |
| Support validity | Support-validated gold-entailed responses; not restricted to correctly predicted positives |
| Conditional CAIP | Invalid support among correct positive answers that received support validation |
| Citation overlap | Mean Jaccard overlap over C0/transformed pairs from complete gold-entailed families; empty/empty pairs excluded, without filtering to correct labels or valid supports |
| Repeat unanimity | Input-level agreement over three executions; distinguish archived label agreement from valid-label agreement |
| Repeat accuracy | Response-level accuracy across primary plus two repeats; invalid labels count as incorrect |

These measures do not form sequential filtering stages with one denominator. Agreement does not establish correctness or reveal an internal reasoning mechanism. C4-C4S2 disagreement is not an isolated causal estimate of a mapping effect, because execution variability is not removed.

## No new calculations for publication packaging

The deposit copied existing files and verified hashes. It did not run inference, aggregate predictions again, fit regressions, compute intervals, or regenerate figures. Existing numerical results remain unchanged. The article's descriptive reporting and limitations govern interpretation of this evidence, not older unqualified claims in historical planning documents.
