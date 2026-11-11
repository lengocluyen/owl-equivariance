# Recover a completed inference run after post-processing failure

Use this procedure only when every model prediction finished and the publication runner
failed later in pooled analysis or finalization. It never starts LM Studio, loads a model,
or sends an inference request.

The recovery gate reconstructs the run exclusively from its frozen provenance. It checks:

- the protocol, dataset list, and exact model matrix;
- one raw and one support-validated primary prediction for every expected model/item pair;
- the full two-repeat subset when the frozen stage requires it;
- response payload presence, model identity, repeat indices, invalid-response ceilings,
  API-error ceilings, and support-validation coverage;
- the three deterministic baselines and all six model-artifact hash records;
- exact reproduction of `primary_analysis.csv` from the frozen validated predictions.

It then generates only the missing derived products: pooled correctness and response-
validity interaction models, paired power simulations, recovery provenance,
`RUN_COMPLETE.json`, and `SHA256SUMS`. The original `RUN_FAILED.txt` is retained.

## 1. Read-only check

Run this first on the inference server, from the repository root:

```bash
RUN_ID=owleq-jws-2026-08-v32-exact-discovery-01 \
  bash scripts/recover_lmstudio_publication.sh check
```

If the prediction directory is stored elsewhere, supply its exact path:

```bash
RUN_ID=owleq-jws-2026-08-v32-exact-discovery-01 \
PREDICTION_ROOT=/absolute/path/to/data/predictions/owleq-jws-2026-08-v32-exact-discovery-01 \
  bash scripts/recover_lmstudio_publication.sh check
```

The command must print `"status": "PASS"`. Check mode performs no writes.

## 2. Finalize without inference

Only after check mode passes:

```bash
RECOVERY_APPROVED=YES \
RUN_ID=owleq-jws-2026-08-v32-exact-discovery-01 \
  bash scripts/recover_lmstudio_publication.sh finalize
```

The default power calculation uses 1,200 planned paired base items, a 5 percentage-point
C0-C4 target gap, a 10-contrast family, 10,000 simulations, and the frozen inference seed.
These match the publication runner. `PLANNED_PAIRS` and `POWER_SIMULATIONS` are exposed for
methodological sensitivity runs, but changing them for the official recovery requires a
new documented protocol amendment.

## 3. Verify the immutable release

```bash
sha256sum -c \
  reports/owleq-jws-2026-08-v32-exact-discovery-01/SHA256SUMS

cat reports/owleq-jws-2026-08-v32-exact-discovery-01/RUN_COMPLETE.json
cat reports/owleq-jws-2026-08-v32-exact-discovery-01/RUN_RECOVERY.json
```

`logs/run.log` is intentionally excluded because the original runner kept it open while
constructing its checksum manifest. All prediction files, frozen provenance, scientific
tables, recovery metadata, and completion metadata are covered.

## Interpretation of sparse response validity

When almost all responses parse successfully, the response-validity interaction model may
be non-identifiable through complete or quasi-complete separation. Recovery records this as
`fit_status: NON_IDENTIFIABLE` and preserves the descriptive invalid-response tables. This
is a valid result and must not be converted into finite coefficients by adding arbitrary
pseudocounts.

