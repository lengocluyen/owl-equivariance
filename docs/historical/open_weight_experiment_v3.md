# Open-weight journal experiment v3

**Protocol:** `owleq-jws-2026-08-v3`  
**Manifest:** `configs/open_weight_experiment_v3.yaml`  
**Model matrix:** `configs/lmstudio_models_v3.tsv`

V3 is a pre-discovery amendment based only on the v2 response-channel diagnostics. No
full-discovery or held-out confirmatory outcome was inspected when it was frozen.

Changes from v2:

- Qwen's explicit answer channel is `reasoning_content`; its 360 stored final answers were
  valid there and exactly reproduced in the targeted rerun.
- Gemma omits the unsupported/ineffective reasoning control and keeps `content`.
- A 20-item diagnostic cell permits one invalid response (5%, inclusive), while each
  complete model/dataset diagnostic must remain at or below 1% invalid overall.
- Discovery and confirmatory cells retain the 2% per-condition and overall invalid-output
  ceilings. Invalid outputs are always counted as incorrect task answers.
- Exact model artifact hashes are required for the official v3 diagnostic and later runs.
- Models are loaded through LM Studio's exact `POST /api/v1/models/load` endpoint. The
  runner verifies the returned instance id and the live `modelKey`, identifier, and
  context length before the first inference request. Frozen study labels remain separate
  from the exact API instance ids.

Never reuse a `RUN_ID` after an identity failure or a mixed-model run. Preserve such a
directory as an invalidated diagnostic artifact and choose a new run id.

Run the diagnostic only after setting `LM_STUDIO_MODELS_DIR` to the real model root:

```bash
PROTOCOL_ID=owleq-jws-2026-08-v3 \
MANIFEST=configs/open_weight_experiment_v3.yaml \
MODEL_MATRIX_FILE=configs/lmstudio_models_v3.tsv \
REQUIRE_WEIGHTS_HASH=1 \
RUN_ID=owleq-jws-2026-08-v3-diagnostic \
  bash scripts/run_lmstudio_publication.sh diagnostic
```

Do not start discovery unless this run records `status: PASS` and all twelve diagnostic
reports pass their frozen gates.

If a complete discovery/confirmatory inference run fails only during pooled analysis, do
not rerun the models. Follow
[`recover_failed_publication_run.md`](recover_failed_publication_run.md) to verify every
stored prediction and finish the derived analysis without contacting LM Studio.
