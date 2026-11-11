# v3.3 post-failure continuation

This procedure exists only for a frozen `owleq-jws-2026-08-v33` confirmatory run that
already stopped at a response-validity threshold. It must not be described as an
unmodified preregistered confirmatory run.

The continuation preserves `RUN_FAILED.txt`, freezes the byte prefix of every existing
prediction file, and stores the amendment at
`reports/<run-id>/provenance/post_failure/continuation_amendment.json`. It leaves the
frozen manifest, panel, datasets, models, prompts, seeds, response fields, context length,
and output-token ceiling unchanged.

Immediately before each `run` invocation, the wrapper also freezes every prediction then
present into a new `provenance/post_failure/attempts/*.json` snapshot. Consequently,
outputs appended during an interrupted continuation become protected inputs to the next
attempt as well.

During continuation:

- complete model/dataset cells are verified and skipped without loading their model;
- incomplete files resume only missing `(orbit_item_id, repeat)` keys;
- a protected prediction may only receive an append; its existing bytes cannot change;
- invalid responses remain in the data and count as incorrect;
- response-validity threshold failures are recorded but are nonfatal for data collection;
- API errors, missing or duplicate keys, model-hash changes, and support-coverage failures
  remain fatal;
- original provenance is not overwritten; continuation runtime provenance is written
  under `provenance/post_failure/runtime/`.

Prepare and inspect the amendment before any new request:

```bash
RUN_ID=owleq-jws-2026-08-v33-confirmatory-01 \
  bash scripts/run_v33_post_failure_continuation.sh prepare

RUN_ID=owleq-jws-2026-08-v33-confirmatory-01 \
  bash scripts/run_v33_post_failure_continuation.sh check
```

After inspection, resume inside the existing tmux session:

```bash
CONTINUATION_APPROVED=YES \
RUN_ID=owleq-jws-2026-08-v33-confirmatory-01 \
  bash scripts/run_v33_post_failure_continuation.sh run
```

The wrapper does not use `set -e`, so a child failure returns control to the parent tmux
shell. A failed attempt writes `POST_FAILURE_CONTINUATION_FAILED.txt`; it never replaces
the original `RUN_FAILED.txt`. A completed collection writes
`POST_FAILURE_CONTINUATION_COMPLETE.json`, not `RUN_COMPLETE.json`.

The manuscript and artifact README must disclose:

1. where the original run stopped and the exact failed gate;
2. that already-produced responses and the failure were known before continuation;
3. that the continuation policy was adopted post-failure;
4. that no existing response was retried, removed, or repaired;
5. both the preregistered stopped-run result and the post-failure full-panel analysis.

The full-panel analysis can be useful as transparently labelled secondary/sensitivity
evidence. It cannot retroactively restore the preregistered confirmatory status.
