"""Command-line entry point for the Python experiment layer (spec section 34)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import analysis, budgeting, diagnostics, modeling, parsing, power, prompting, protocol
from . import reporting
from . import stability
from . import tokens
from .dataset import append_jsonl, load_items, load_predictions, validate_dataset, write_jsonl
from .metrics import answer as answer_metrics
from .metrics import orbit as orbit_metrics
from .metrics import proof as proof_metrics
from .metrics import stats
from .runners import build_runner
from .schemas import Prediction


def cmd_validate(args) -> int:
    items = load_items(args.dataset)
    expected = args.expect_conditions.split(",") if args.expect_conditions else None
    problems = validate_dataset(items, dataset_path=args.dataset, expected_conditions=expected)

    ref = [i for i in items if i.condition == "C0"] or items
    pos = [len(i.context.axioms) for i in ref if i.task.positive]
    neg = [len(i.context.axioms) for i in ref if not i.task.positive]
    print(f"{len(items)} items, {len({i.base_item_id for i in items})} orbits, "
          f"conditions: {sorted({i.condition for i in items})}")
    if pos:
        print(f"  entailed     n={len(pos):4d}  context axioms "
              f"min={min(pos)} max={max(pos)} mean={sum(pos) / len(pos):.1f}")
    if neg:
        print(f"  not entailed n={len(neg):4d}  context axioms "
              f"min={min(neg)} max={max(neg)} mean={sum(neg) / len(neg):.1f}")

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for p in problems[:25]:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("dataset OK: labels certified, orbits complete and consistent, contexts non-empty "
          "and size-balanced, no condition leakage, seeds distinct")
    return 0


def cmd_prompts(args) -> int:
    items = load_items(args.dataset)
    for item in items[: args.limit]:
        prompt = prompting.build(item, args.style)
        print("=" * 78)
        print(f"{item.orbit_item_id}  [{item.condition}]  gold={item.task.label}")
        print("-" * 78)
        print(prompt.user)
    return 0


def cmd_infer(args) -> int:
    items = load_items(args.dataset)
    if args.conditions:
        wanted = set(args.conditions.split(","))
        items = [i for i in items if i.condition in wanted]
    if args.limit_orbits:
        selected = set(sorted({i.base_item_id for i in items})[: args.limit_orbits])
        items = [i for i in items if i.base_item_id in selected]
    if args.limit:
        items = items[: args.limit]

    reasoning_effort = args.reasoning_effort.strip()
    if reasoning_effort.lower() in {"none", "omit"}:
        reasoning_effort = ""
    runner = build_runner(
        args.model,
        max_output_tokens=args.max_output_tokens,
        reasoning_effort=reasoning_effort or None,
        seed=args.seed,
        answer_field=args.answer_field,
        request_timeout=args.request_timeout,
        recorded_model_id=args.record_model_id or None,
    )
    predictions: list[Prediction] = []
    completed: set[tuple[str, int]] = set()
    if args.resume and Path(args.output).exists():
        predictions = load_predictions(args.output)
        allowed_ids = {item.orbit_item_id for item in items}
        allowed_repeats = set(range(args.repeat_offset, args.repeat_offset + args.repeats))
        resume_problems = []
        if any(p.orbit_item_id not in allowed_ids for p in predictions):
            resume_problems.append("saved output contains items outside this dataset selection")
        if any(p.repeat not in allowed_repeats for p in predictions):
            resume_problems.append("saved output contains repeat indices outside this run")
        if any(p.model != getattr(runner, "name", args.model) for p in predictions):
            resume_problems.append("saved output was produced by a different model identifier")
        if any(p.prompt_style != args.style for p in predictions):
            resume_problems.append("saved output used a different prompt style")
        recorded_fields = {
            p.runner_metadata.get("requested_answer_field")
            for p in predictions
            if p.runner_metadata.get("requested_answer_field") is not None
        }
        if recorded_fields and recorded_fields != {args.answer_field}:
            resume_problems.append(
                f"saved output answer field {sorted(recorded_fields)} differs from "
                f"{args.answer_field!r}"
            )
        recorded_seeds = {
            p.runner_metadata.get("seed")
            for p in predictions
            if "seed" in p.runner_metadata
        }
        if recorded_seeds and recorded_seeds != {args.seed}:
            resume_problems.append(
                f"saved output seed {sorted(recorded_seeds, key=str)} differs from "
                f"{args.seed!r}"
            )
        expected_request = {
            "model": getattr(runner, "model", None),
            "max_tokens": args.max_output_tokens,
            "reasoning_effort": reasoning_effort or None,
            "request_timeout_seconds": args.request_timeout,
        }
        for key, expected_value in expected_request.items():
            recorded_values = {
                p.runner_metadata.get("request_parameters", {}).get(key)
                for p in predictions
                if key in p.runner_metadata.get("request_parameters", {})
            }
            if recorded_values and recorded_values != {expected_value}:
                resume_problems.append(
                    f"saved output {key}={sorted(recorded_values, key=str)} differs "
                    f"from {expected_value!r}"
                )
        if resume_problems:
            print("refusing unsafe resume:", file=sys.stderr)
            for problem in resume_problems:
                print(f"  {problem}", file=sys.stderr)
            return 2
        completed = {(p.orbit_item_id, p.repeat) for p in predictions}
        print(f"resuming with {len(predictions)} saved predictions")
    else:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("", encoding="utf-8")
    total = len(items) * args.repeats
    spent_usd = sum(
        ((p.input_tokens or 0) * args.input_price_per_mtok
         + (p.output_tokens or 0) * args.output_price_per_mtok) / 1_000_000
        for p in predictions
    )
    stopped_for_budget = False

    for repeat in range(args.repeat_offset, args.repeat_offset + args.repeats):
        for n, item in enumerate(items, start=1):
            if (item.orbit_item_id, repeat) in completed:
                continue
            prompt = prompting.build(item, args.style)
            # Reserve the next request at its full output ceiling. The input estimate is
            # deliberately conservative; actual provider usage replaces it after the call.
            estimated_input = int(
                (len(prompt.system) + len(prompt.user))
                / args.characters_per_token
                * args.input_safety_factor
            )
            reserved = (
                estimated_input * args.input_price_per_mtok
                + args.max_output_tokens * args.output_price_per_mtok
            ) / 1_000_000
            if args.max_cost_usd and spent_usd + reserved > args.max_cost_usd:
                stopped_for_budget = True
                break

            request_started_utc = datetime.now(timezone.utc).isoformat()
            result = runner.run(item, prompt)
            response_received_utc = datetime.now(timezone.utc).isoformat()
            parsed = parsing.parse(result.raw_output, item, allow_repair=not args.no_repair)

            runner_metadata = dict(result.metadata)
            runner_metadata.update(
                {
                    "request_started_utc": request_started_utc,
                    "response_received_utc": response_received_utc,
                    "system_prompt_sha256": hashlib.sha256(
                        prompt.system.encode("utf-8")
                    ).hexdigest(),
                    "user_prompt_sha256": hashlib.sha256(
                        prompt.user.encode("utf-8")
                    ).hexdigest(),
                    "response_schema_sha256": hashlib.sha256(
                        json.dumps(
                            prompt.schema,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                }
            )
            prediction = Prediction(
                orbit_item_id=item.orbit_item_id,
                base_item_id=item.base_item_id,
                condition=item.condition,
                model=getattr(runner, "name", args.model),
                prompt_style=args.style,
                label=parsed.label,
                support_axiom_ids=parsed.support_axiom_ids,
                unknown_support_ids=parsed.unknown_support_ids,
                # Raw outputs are kept by default: they are a required release artifact and
                # the only way to re-parse a run without paying for it twice.
                raw_output="" if args.drop_raw else result.raw_output,
                runner_error=result.error,
                parse_error=parsed.error,
                parse_repairs=parsed.repairs,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                runner_metadata=runner_metadata,
                response_payload=(
                    None if args.drop_response_payload else result.response_payload
                ),
            )
            # Repeats are tagged rather than averaged, so run-to-run variation on a
            # nondeterministic API can be measured instead of assumed away.
            prediction.repeat = repeat
            predictions.append(prediction)
            append_jsonl(args.output, prediction)
            spent_usd += (
                (result.input_tokens or estimated_input) * args.input_price_per_mtok
                + (result.output_tokens or args.max_output_tokens)
                * args.output_price_per_mtok
            ) / 1_000_000

            done = (repeat - args.repeat_offset) * len(items) + n
            if args.progress and done % args.progress == 0:
                print(f"  {done}/{total}", file=sys.stderr)
        if stopped_for_budget:
            break

    parsed_ok = sum(1 for p in predictions if p.label is not None)
    print(f"wrote {len(predictions)} predictions to {args.output}")
    print(f"  parsed: {parsed_ok} ({parsed_ok / max(len(predictions), 1):.1%})")
    if args.input_price_per_mtok or args.output_price_per_mtok:
        print(f"  estimated/recorded spend: ${spent_usd:.2f}")
    if stopped_for_budget:
        print(
            f"  STOPPED before the next request to respect --max-cost-usd "
            f"${args.max_cost_usd:.2f}; rerun with --resume after review",
            file=sys.stderr,
        )

    if args.repeats > 1:
        by_item: dict[str, set] = {}
        for p in predictions:
            by_item.setdefault(p.orbit_item_id, set()).add(p.label)
        unstable = sum(1 for labels in by_item.values() if len(labels) > 1)
        print(f"  repeats: {args.repeats}; {unstable}/{len(by_item)} items "
              f"({unstable / max(len(by_item), 1):.1%}) changed answer across repeats")
    return 3 if stopped_for_budget else 0


def cmd_diagnose(args) -> int:
    items = load_items(args.dataset)
    predictions = load_predictions(args.predictions)
    result = diagnostics.analyze(
        items,
        predictions,
        max_invalid_rate=args.max_invalid_rate,
        max_overall_invalid_rate=args.max_overall_invalid_rate,
        max_api_error_rate=args.max_api_error_rate,
        require_response_payload=args.require_response_payload,
        require_answer_field=args.require_answer_field or None,
    )
    diagnostics.write_report(result, args.output_dir)
    print(diagnostics.render_markdown(result))
    return 0 if result.passed or args.advisory else 1


def cmd_stability(args) -> int:
    items = load_items(args.dataset)
    predictions = []
    for path in args.predictions:
        predictions.extend(load_predictions(path))
    result = stability.analyze(
        items,
        predictions,
        expected_repeats=args.expected_repeats,
    )
    stability.write_report(result, args.output_dir)
    print(stability.render_markdown(result))
    return 0 if result.passed else 1


def cmd_reparse(args) -> int:
    from .runners.lmstudio_api import extract_answer_from_response

    input_path = Path(args.predictions).resolve()
    output_path = Path(args.output).resolve()
    if input_path == output_path:
        print("reparse requires a new --output path; the source artifact is immutable",
              file=sys.stderr)
        return 2

    items = {item.orbit_item_id: item for item in load_items(args.dataset)}
    predictions = load_predictions(args.predictions)
    missing_payload = sum(pred.response_payload is None for pred in predictions)
    if missing_payload:
        print(
            f"cannot reparse: {missing_payload}/{len(predictions)} predictions lack "
            "a stored response payload",
            file=sys.stderr,
        )
        return 2

    reparsed_predictions = []
    for prediction in predictions:
        item = items.get(prediction.orbit_item_id)
        if item is None:
            print(
                f"cannot reparse: no dataset item for {prediction.orbit_item_id}",
                file=sys.stderr,
            )
            return 2
        raw, selected, available = extract_answer_from_response(
            prediction.response_payload or {},
            args.answer_field,
        )
        parsed = parsing.parse(raw, item, allow_repair=not args.no_repair)
        updated = prediction.model_copy(deep=True)
        updated.raw_output = raw
        updated.label = parsed.label
        updated.support_axiom_ids = parsed.support_axiom_ids
        updated.unknown_support_ids = parsed.unknown_support_ids
        updated.parse_error = parsed.error
        updated.parse_repairs = parsed.repairs
        updated.answer_correct = None
        updated.support_valid = None
        updated.support_minimal = None
        updated.redundant_support_ids = []
        updated.runner_metadata["selected_answer_field"] = selected
        updated.runner_metadata["available_text_fields"] = available
        updated.runner_metadata["reparsed_answer_field"] = args.answer_field
        updated.runner_metadata["reparsed_utc"] = datetime.now(timezone.utc).isoformat()
        reparsed_predictions.append(updated)

    write_jsonl(args.output, reparsed_predictions)
    valid = sum(pred.label is not None for pred in reparsed_predictions)
    print(
        f"reparsed {len(reparsed_predictions)} stored responses from "
        f"{args.answer_field!r}; valid={valid}/{len(reparsed_predictions)} "
        f"({valid / max(len(reparsed_predictions), 1):.1%})"
    )
    print("run `owleq diagnose`, then the Java support validator, on the new artifact")
    return 0


def cmd_power(args) -> int:
    items = []
    for path in args.dataset:
        items.extend(load_items(path))
    predictions = []
    for path in args.predictions:
        predictions.extend(load_predictions(path))
    result = power.analyze(
        items,
        predictions,
        reference=args.reference,
        condition=args.condition,
        outcome=args.outcome,
        planned_pairs=args.planned_pairs,
        target_gap=args.target_gap,
        family_size=args.family_size,
        alpha=args.alpha,
        simulations=args.simulations,
        min_power=args.min_power,
        seed=args.seed,
    )
    power.write_report(result, args.output_dir)
    print(power.render_markdown(result))
    return 0 if result.passed or args.advisory else 1


def cmd_budget(args) -> int:
    report = budgeting.estimate(args.manifest, args.stage, ceiling=args.ceiling)
    print(f"protocol: {report.protocol_id}")
    print(f"stage:    {report.stage}")
    print(f"mode:     {'ceiling' if args.ceiling else 'expected'}")
    print(f"calls:    {report.total_calls:,}")
    print(f"input:    {report.input_tokens_per_model / 1_000_000:.3f} MTok/model")
    print(f"output:   {report.output_tokens_per_model / 1_000_000:.3f} MTok/model")
    print()
    print(reporting.markdown_table(report.rows, budgeting.BUDGET_COLUMNS))
    print(f"\ntotal estimated cost: ${report.total_cost_usd:.2f}")
    if report.hard_cap_usd:
        verdict = "PASS" if report.total_cost_usd <= report.hard_cap_usd else "FAIL"
        print(f"hard cap: ${report.hard_cap_usd:.2f} [{verdict}]")
        if verdict == "FAIL":
            return 1
    return 0


def cmd_lmstudio_preflight(args) -> int:
    base_url = (
        args.base_url
        or os.getenv("LM_STUDIO_BASE_URL")
        or "http://localhost:1234/v1"
    ).rstrip("/")
    root_url = base_url[:-3] if base_url.endswith("/v1") else base_url
    token = os.getenv("LM_STUDIO_API_TOKEN", "")
    request = urllib.request.Request(root_url + "/api/v0/models")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            payload = json.load(response)
    except Exception as exc:
        print(f"LM Studio preflight failed for {root_url}: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2

    models = payload.get("data", [])
    selected = [m for m in models if m.get("id") == args.model] if args.model else models
    if args.weights_sha256:
        digest = args.weights_sha256.lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            print("--weights-sha256 must be exactly 64 hexadecimal characters",
                  file=sys.stderr)
            return 2
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(
                {
                    "base_url": base_url,
                    "requested_model": args.model or None,
                    "weights_sha256": args.weights_sha256.lower() or None,
                    "models": selected,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if not selected:
        available = ", ".join(str(m.get("id")) for m in models) or "(none)"
        print(f"requested model {args.model!r} not found; available: {available}",
              file=sys.stderr)
        return 1

    for model in selected:
        print(json.dumps(model, indent=2))
    if args.model and not any(m.get("state") == "loaded" for m in selected):
        print(f"model {args.model!r} exists but is not loaded", file=sys.stderr)
        return 1
    print("LM Studio preflight OK; no inference request was sent")
    return 0


def cmd_evaluate(args) -> int:
    items = load_items(args.dataset)
    predictions = load_predictions(args.predictions)
    if any(pred.repeat != 0 for pred in predictions):
        print(
            "evaluate accepts primary repeat-0 predictions only; use `owleq stability` "
            "for the frozen repeat subset",
            file=sys.stderr,
        )
        return 2

    per_cond = answer_metrics.per_condition(items, predictions)
    rows = [m.as_dict() for m in sorted(per_cond.values(), key=lambda m: m.condition)]

    comparisons = answer_metrics.compare_to_reference(
        items, predictions, reference=args.reference, n_resamples=args.bootstrap
    )
    comparison_rows = [c.as_dict() for c in comparisons]
    validity_comparisons = answer_metrics.compare_validity_to_reference(
        items, predictions, reference=args.reference, n_resamples=args.bootstrap
    )
    validity_rows = [c.as_dict() for c in validity_comparisons]

    orbits = orbit_metrics.compute(items, predictions, reference=args.reference)
    proofs = proof_metrics.per_condition(items, predictions)
    proof_rows = [m.as_dict() for m in sorted(proofs.values(), key=lambda m: m.condition)]
    proof_orbit = proof_metrics.orbit_level(items, predictions, reference=args.reference)

    seed_pairs = []
    for a, b in (("C4", "C4S2"), ("C4S2", "C4S3"), ("C4", "C4S3")):
        result = answer_metrics.seed_disagreement(items, predictions, a, b)
        if result:
            seed_pairs.append(result.as_dict())

    print("\n== Answer accuracy by condition ==")
    print(reporting.markdown_table(rows, reporting.ANSWER_COLUMNS))

    if comparison_rows:
        print(f"\n== Paired comparison against {args.reference} ==")
        print(reporting.markdown_table(comparison_rows, reporting.COMPARISON_COLUMNS))
    if validity_rows:
        print(f"\n== Paired response-validity comparison against {args.reference} ==")
        print(
            reporting.markdown_table(
                validity_rows,
                reporting.VALIDITY_COMPARISON_COLUMNS,
            )
        )

    print("\n== Orbit level ==")
    for key, value in orbits.as_dict().items():
        print(f"  {key}: {value}")

    if any(r["n_validated"] for r in proof_rows):
        print("\n== Proof level ==")
        print("  caip_joint = P(answer correct AND proof invalid); "
              "caip_given_correct = P(proof invalid | answer correct)")
        print(reporting.markdown_table(proof_rows, reporting.PROOF_COLUMNS))
        print("\n  " + json.dumps(proof_orbit.as_dict()))
        if proof_orbit.support_equivariance_mean is None:
            print("  support equivariance: undefined "
                  f"({proof_orbit.n_support_pairs_undefined} pairs cited nothing on both sides)")
    else:
        print("\n== Proof level ==")
        print("  no validated support; run the Java validate-support command first")

    if seed_pairs:
        print("\n== Self-inconsistency across seeds of the same operator ==")
        for row in seed_pairs:
            print(
                f"  {row['condition_a']} vs {row['condition_b']}: "
                f"disagree on {row['disagreement_rate']:.1%} of {row['n_pairs']} items"
            )

    if args.output_dir:
        out = Path(args.output_dir)
        reporting.write_csv(out / "answer_by_condition.csv", rows, reporting.ANSWER_COLUMNS)
        reporting.write_csv(
            out / "paired_comparisons.csv", comparison_rows, reporting.COMPARISON_COLUMNS
        )
        reporting.write_csv(
            out / "paired_validity_comparisons.csv",
            validity_rows,
            reporting.VALIDITY_COMPARISON_COLUMNS,
        )
        reporting.write_csv(out / "proof_by_condition.csv", proof_rows, reporting.PROOF_COLUMNS)
        if seed_pairs:
            reporting.write_csv(out / "seed_disagreement.csv", seed_pairs)
        (out / "orbit_metrics.json").write_text(
            json.dumps(
                {"answer_orbit": orbits.as_dict(), "proof_orbit": proof_orbit.as_dict()},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if args.format == "latex":
            (out / "table_answer.tex").write_text(
                reporting.latex_table(
                    rows,
                    reporting.ANSWER_COLUMNS,
                    caption="Answer accuracy by lexical-channel condition.",
                    label="tab:answer",
                )
                + "\n",
                encoding="utf-8",
            )
        print(f"\nwrote tables to {out}")
    return 0


def cmd_export_analysis(args) -> int:
    items = []
    for path in args.dataset:
        items.extend(load_items(path))
    predictions = []
    for path in args.predictions:
        predictions.extend(load_predictions(path))

    result = analysis.build_rows(
        items, predictions, reference=args.reference, prompt_style=args.style
    )
    out = Path(args.output)
    reporting.write_csv(out, result.as_dicts(), analysis.ANALYSIS_COLUMNS)
    out.with_suffix(".model-recipe.txt").write_text(analysis.MODEL_RECIPE, encoding="utf-8")

    print(f"wrote {len(result.rows)} rows to {out}")
    print(f"  models:     {sorted({r.model for r in result.rows})}")
    print(f"  conditions: {sorted({r.condition for r in result.rows})}")
    print(f"  ontologies: {sorted({r.ontology_id for r in result.rows})}")
    print(f"  token covariate source: {result.token_source}")
    if result.missing_items:
        print(f"  WARNING: {result.missing_items} predictions had no matching dataset item")
    print(f"  fitting recipe: {out.with_suffix('.model-recipe.txt')}")

    # Orbit-level permutation tests, which the aggregate tables do not cover. Run per model:
    # orbits keyed on the base item alone would let one model's outcomes overwrite another's
    # and every contrast would collapse to zero.
    by_id = {i.orbit_item_id: i for i in items}
    per_model: dict[str, dict[str, dict[str, bool]]] = {}
    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is not None:
            per_model.setdefault(pred.model, {}).setdefault(item.base_item_id, {})[
                item.condition
            ] = (pred.label == item.task.label)

    for model, orbits in sorted(per_model.items()):
        outcomes = list(orbits.values())
        conditions = sorted({c for o in outcomes for c in o} - {args.reference})
        if not conditions:
            continue
        print(f"\n== Orbit permutation tests vs {args.reference} -- {model} ==")
        raw = {}
        for condition in conditions:
            diff, p = stats.orbit_permutation_test(
                outcomes, args.reference, condition, n_permutations=args.permutations
            )
            raw[condition] = p
            print(f"  {condition:6s} diff={diff:+.3f}  p={p:.4f}")
        adjusted = stats.holm_correction(raw)
        print("  Holm-adjusted: " + ", ".join(f"{k}={v:.4f}" for k, v in sorted(adjusted.items())))
    return 0


def cmd_tokens(args) -> int:
    items = load_items(args.dataset)
    counter = tokens.Counter(args.tokenizer)
    report = tokens.analyse(
        items,
        counter=counter,
        reference=args.reference,
        prompt_style=args.style,
        tolerance=args.tolerance,
    )

    print(f"counter: {report.counter_kind}")
    print(f"  counts cover the user prompt only; the system prompt is identical across all "
          f"conditions ({report.system_overhead} constant overhead)")
    if report.counter_kind.endswith("proxy"):
        print("  NOTE: a proxy, not a token count. Fine for relative comparison across")
        print("        conditions; do not report these as tokens. Use --tokenizer hf:<model>.")
    print()
    print(reporting.markdown_table(
        [c.as_dict() for c in report.per_condition], tokens.TOKEN_COLUMNS
    ))

    if report.length_warnings:
        print("\n== Prompt-length confounds vs " + args.reference + " ==")
        for warning in report.length_warnings:
            print(f"  [WARN] {warning}")

    if report.match_checks:
        print("\n== Token-matching checks ==")
        for check in report.match_checks:
            mark = "N/A " if not check.assessable else ("OK  " if check.matched else "FAIL")
            print(f"  [{mark}] {check.verdict()}")

    if args.output_dir:
        out = Path(args.output_dir)
        reporting.write_csv(
            out / "token_counts.csv",
            [c.as_dict() for c in report.per_condition],
            tokens.TOKEN_COLUMNS,
        )
        (out / "token_report.json").write_text(
            json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nwrote token tables to {out}")

    assessed = [c for c in report.match_checks if c.assessable]
    if not assessed:
        print("\nNo matching check was assessable; re-run with --tokenizer hf:<model-id> "
              "before claiming the tokenization control holds.")
        return 2
    return 0 if all(c.matched for c in assessed) else 1


def cmd_model(args) -> int:
    try:
        result = modeling.fit(
            args.analysis,
            estimator=args.estimator,
            reference=args.reference,
            terms=args.terms.split(",") if args.terms else None,
            model_filter=args.model,
            outcome=args.outcome,
            condition_model_interaction=args.condition_model_interaction,
            ontology_effect=args.ontology_effect,
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        print("\nFalling back to the printed recipe:\n", file=sys.stderr)
        print(analysis.MODEL_RECIPE)
        return 1

    print(f"estimator: {result.estimator}")
    print(f"fit status: {result.fit_status}")
    print(f"formula:   {result.formula}")
    print(f"n = {result.n_observations} observations in {result.n_groups} "
          f"{result.group_var} clusters")
    for note in result.notes:
        print(f"  note: {note}")
    print()
    print(result.summary_text)

    if args.output_dir:
        out = Path(args.output_dir)
        if result.coefficients:
            reporting.write_csv(
                out / "model_coefficients.csv",
                result.coefficients,
                modeling.COEFFICIENT_COLUMNS,
            )
        else:
            out.mkdir(parents=True, exist_ok=True)
        (out / "model_fit.json").write_text(
            json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        (out / "model_summary.txt").write_text(result.summary_text + "\n", encoding="utf-8")
        print(f"\nwrote model output to {out}")
    return 0


def cmd_freeze_confirmatory_panel(args) -> int:
    try:
        payload = protocol.freeze_panel(
            args.manifest,
            args.dataset,
            args.output,
            acknowledge_no_confirmatory_outcomes=args.acknowledge_no_confirmatory_outcomes,
        )
    except protocol.PanelValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    totals = payload["totals"]
    print(
        f"FROZEN: {totals['sources']} sources, {totals['base_items']} base items, "
        f"{totals['rows']} rows"
    )
    print(f"panel: {args.output}")
    return 0


def cmd_verify_confirmatory_panel(args) -> int:
    try:
        payload = protocol.verify_panel(
            args.manifest,
            args.panel,
            args.dataset or None,
        )
    except protocol.PanelValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_split(args) -> int:
    """Assign splits by ontology, so no ontology appears in more than one split."""
    items = load_items(args.dataset)
    ontologies = sorted({i.ontology.ontology_id for i in items})

    assignment: dict[str, str] = {}
    for spec in args.assign:
        name, _, split = spec.partition("=")
        assignment[name] = split
    for ontology in ontologies:
        assignment.setdefault(ontology, args.default)

    for item in items:
        item.split = assignment[item.ontology.ontology_id]

    write_jsonl(args.output, items)
    counts: dict[str, int] = {}
    for item in items:
        counts[item.split] = counts.get(item.split, 0) + 1
    print(f"wrote {len(items)} items to {args.output}")
    for split, n in sorted(counts.items()):
        holders = sorted({o for o, s in assignment.items() if s == split})
        print(f"  {split:6s} {n:5d} items  ontologies: {holders}")
    if len(ontologies) < 2:
        print("  WARNING: one ontology only -- an ontology-disjoint split is not possible, "
              "and generalization claims are not supported")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="owleq", description="OWL signature-isomorphism equivariance audit."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Structural and experimental-adequacy gates.")
    p.add_argument("--dataset", required=True)
    p.add_argument(
        "--expect-conditions",
        default="",
        help="Comma-separated conditions every orbit must contain, e.g. C0,C1,C2,C4,C4S2,C7,C8",
    )
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("prompts", help="Print rendered prompts for inspection.")
    p.add_argument("--dataset", required=True)
    p.add_argument("--style", default="structured_proof", choices=prompting.styles())
    p.add_argument("--limit", type=int, default=3)
    p.set_defaults(func=cmd_prompts)

    p = sub.add_parser("infer", help="Run a model over the benchmark.")
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    p.add_argument(
        "--model",
        required=True,
        help=("oracle | majority | lexical | anthropic:<model> | openai:<model> | "
              "google:<model> | lmstudio:<model> | hf:<model>"),
    )
    p.add_argument("--style", default="structured_proof", choices=prompting.styles())
    p.add_argument("--conditions", default="", help="Comma-separated condition ids to run.")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument(
        "--limit-orbits",
        type=int,
        default=0,
        help=(
            "Select this many complete base-item orbits; use this instead of --limit "
            "for smoke tests."
        ),
    )
    p.add_argument("--repeats", type=int, default=1,
                   help="Responses per item. Use >1 on nondeterministic APIs to measure "
                        "run-to-run variation rather than assume it away.")
    p.add_argument(
        "--repeat-offset",
        type=int,
        default=0,
        help="First repeat index. Use 1 when adding two repeat responses after a primary "
             "repeat-0 run.",
    )
    p.add_argument("--drop-raw", action="store_true",
                   help="Omit raw responses. They are kept by default: a required release "
                        "artifact, and the only way to re-parse a run without re-paying.")
    p.add_argument("--no-repair", action="store_true", help="Disable deterministic JSON repair.")
    p.add_argument("--progress", type=int, default=0)
    p.add_argument("--max-output-tokens", type=int, default=1024)
    p.add_argument(
        "--reasoning-effort",
        default="medium",
        help="Provider reasoning/thinking level; use 'none' to omit the parameter.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Inference sampling seed where the backend supports it (LM Studio currently).",
    )
    p.add_argument(
        "--answer-field",
        default="content",
        choices=["content", "reasoning_content", "reasoning", "auto"],
        help=(
            "LM Studio assistant-message field to parse. 'auto' prefers content then "
            "reasoning_content/reasoning and records the selected field. Freeze this "
            "choice before confirmatory inference."
        ),
    )
    p.add_argument(
        "--record-model-id",
        default="",
        help=(
            "Publication-facing model label. For LM Studio, --model remains the exact "
            "loaded instance id sent to the API; this separate label is stored in "
            "predictions."
        ),
    )
    p.add_argument(
        "--drop-response-payload",
        action="store_true",
        help="Do not retain the complete provider response. Forbidden by the publication runner.",
    )
    p.add_argument(
        "--request-timeout",
        type=float,
        default=600.0,
        help="Per-request timeout in seconds for LM Studio; no automatic retry is made.",
    )
    p.add_argument("--resume", action="store_true",
                   help="Keep existing output rows and skip completed item/repeat pairs.")
    p.add_argument("--max-cost-usd", type=float, default=0.0,
                   help="Stop before the next conservatively reserved request exceeds this cap.")
    p.add_argument("--input-price-per-mtok", type=float, default=0.0)
    p.add_argument("--output-price-per-mtok", type=float, default=0.0)
    p.add_argument("--characters-per-token", type=float, default=4.0)
    p.add_argument("--input-safety-factor", type=float, default=1.25)
    p.set_defaults(func=cmd_infer)

    p = sub.add_parser("budget", help="Cost the frozen model/dataset protocol without inference.")
    p.add_argument("--manifest", default="configs/publication_experiment.yaml")
    p.add_argument(
        "--stage",
        default="discovery",
        choices=["diagnostic", "smoke", "discovery", "confirmatory"],
    )
    p.add_argument("--ceiling", action="store_true",
                   help="Assume every response reaches max_output_tokens.")
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser(
        "lmstudio-preflight",
        help="Read LM Studio model/runtime metadata without sending an inference request.",
    )
    p.add_argument("--base-url", default="",
                   help="OpenAI-compatible base URL; defaults to LM_STUDIO_BASE_URL or localhost.")
    p.add_argument("--model", default="", help="Exact LM Studio model id to require.")
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument(
        "--weights-sha256",
        default="",
        help="Server-computed SHA-256 of the exact GGUF/model artifact.",
    )
    p.add_argument("--output", default="",
                   help="Optional JSON path for the frozen model/quantization record.")
    p.set_defaults(func=cmd_lmstudio_preflight)

    p = sub.add_parser(
        "diagnose",
        help="Audit API, parser, answer-channel and structured-output validity.",
    )
    p.add_argument("--dataset", required=True)
    p.add_argument("--predictions", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-invalid-rate", type=float, default=0.02)
    p.add_argument(
        "--max-overall-invalid-rate",
        type=float,
        default=None,
        help="Optional aggregate invalid-response ceiling across all conditions.",
    )
    p.add_argument("--max-api-error-rate", type=float, default=0.0)
    p.add_argument("--require-response-payload", action="store_true")
    p.add_argument(
        "--advisory",
        action="store_true",
        help="Write a failing diagnostic but return zero; used only to survey all models.",
    )
    p.add_argument(
        "--require-answer-field",
        default="",
        choices=["", "content", "reasoning_content", "reasoning"],
    )
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser(
        "stability",
        help="Analyze the frozen three-response repeat subset without pseudoreplication.",
    )
    p.add_argument("--dataset", required=True, help="Frozen repeat-subset benchmark.")
    p.add_argument("--predictions", required=True, nargs="+")
    p.add_argument("--expected-repeats", type=int, default=3)
    p.add_argument("--output-dir", required=True)
    p.set_defaults(func=cmd_stability)

    p = sub.add_parser(
        "reparse",
        help="Deterministically reparse a stored LM Studio response field without inference.",
    )
    p.add_argument("--dataset", required=True)
    p.add_argument("--predictions", required=True)
    p.add_argument("--output", required=True)
    p.add_argument(
        "--answer-field",
        required=True,
        choices=["content", "reasoning_content", "reasoning", "auto"],
    )
    p.add_argument("--no-repair", action="store_true")
    p.set_defaults(func=cmd_reparse)

    p = sub.add_parser(
        "power",
        help="Simulate paired McNemar power from discovery discordance.",
    )
    p.add_argument("--dataset", required=True, nargs="+")
    p.add_argument("--predictions", required=True, nargs="+")
    p.add_argument("--reference", default="C0")
    p.add_argument("--condition", default="C4")
    p.add_argument("--outcome", default="correct", choices=["correct", "parsed"])
    p.add_argument("--planned-pairs", type=int, default=1200)
    p.add_argument("--target-gap", type=float, default=0.05)
    p.add_argument("--family-size", type=int, default=10)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--simulations", type=int, default=10000)
    p.add_argument("--min-power", type=float, default=0.80)
    p.add_argument("--seed", type=int, default=20260725)
    p.add_argument("--output-dir", required=True)
    p.add_argument(
        "--advisory",
        action="store_true",
        help="Write a failing power report without marking the completed discovery run failed.",
    )
    p.set_defaults(func=cmd_power)

    p = sub.add_parser("evaluate", help="Compute answer, orbit and proof metrics.")
    p.add_argument("--dataset", required=True)
    p.add_argument("--predictions", required=True)
    p.add_argument("--reference", default="C0")
    p.add_argument("--bootstrap", type=int, default=10000)
    p.add_argument("--output-dir", default="")
    p.add_argument("--format", default="csv", choices=["csv", "latex"])
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser(
        "export-analysis",
        help="Tidy long-format CSV with covariates, for mixed-effects analysis.",
    )
    p.add_argument(
        "--dataset",
        required=True,
        nargs="+",
        help="One or more certified benchmark JSONL files; use multiple paths to pool ontologies.",
    )
    p.add_argument("--predictions", required=True, nargs="+",
                   help="One or more prediction files; pool models and ontologies here.")
    p.add_argument("--output", required=True)
    p.add_argument("--reference", default="C0")
    p.add_argument("--style", default="structured_proof", choices=prompting.styles())
    p.add_argument("--permutations", type=int, default=10000)
    p.set_defaults(func=cmd_export_analysis)

    p = sub.add_parser("tokens", help="Tokenization controls (spec section 24).")
    p.add_argument("--dataset", required=True)
    p.add_argument("--tokenizer", default="words",
                   help="hf:<model-id> for real counts; 'words' or 'chars' for a proxy.")
    p.add_argument("--reference", default="C0")
    p.add_argument("--style", default="structured_proof", choices=prompting.styles())
    p.add_argument("--tolerance", type=float, default=0.10,
                   help="Relative length difference allowed between matched conditions.")
    p.add_argument("--output-dir", default="")
    p.set_defaults(func=cmd_tokens)

    p = sub.add_parser("model", help="Fit the condition effect with covariates.")
    p.add_argument("--analysis", required=True, help="CSV from export-analysis.")
    p.add_argument("--estimator", default="gee", choices=["gee", "bayes_mixed"])
    p.add_argument("--reference", default="C0")
    p.add_argument("--terms", default="", help="Comma-separated override of the covariates.")
    p.add_argument("--model", default="", help="Fit one model at a time.")
    p.add_argument(
        "--outcome",
        default="correct",
        choices=["correct", "parsed"],
        help="Model task correctness or structured-output validity as separate outcomes.",
    )
    p.add_argument(
        "--condition-model-interaction",
        action="store_true",
        help="For pooled models, estimate condition-by-model heterogeneity.",
    )
    p.add_argument(
        "--ontology-effect",
        default="auto",
        choices=["auto", "fixed", "random", "none"],
        help=(
            "How ontology enters the model. 'random' is available for bayes_mixed and "
            "requires at least five ontologies; v3.3 confirmatory analysis uses it."
        ),
    )
    p.add_argument("--output-dir", default="")
    p.set_defaults(func=cmd_model)

    p = sub.add_parser(
        "freeze-confirmatory-panel",
        help="Validate and immutably freeze a pre-outcome confirmatory dataset panel.",
    )
    p.add_argument("--manifest", required=True)
    p.add_argument("--dataset", required=True, nargs="+")
    p.add_argument("--output", required=True)
    p.add_argument(
        "--acknowledge-no-confirmatory-outcomes",
        action="store_true",
        help="Required assertion that no confirmatory model outcome has been inspected.",
    )
    p.set_defaults(func=cmd_freeze_confirmatory_panel)

    p = sub.add_parser(
        "verify-confirmatory-panel",
        help="Recompute all hashes and capacity gates for a frozen panel.",
    )
    p.add_argument("--manifest", required=True)
    p.add_argument("--panel", required=True)
    p.add_argument(
        "--dataset",
        nargs="*",
        default=[],
        help="Optional runtime dataset list; order must exactly match the frozen panel.",
    )
    p.set_defaults(func=cmd_verify_confirmatory_panel)

    p = sub.add_parser("split", help="Assign ontology-disjoint splits.")
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--assign", nargs="*", default=[],
                   help="ontology=split pairs, e.g. cl=train po=test")
    p.add_argument("--default", default="test")
    p.set_defaults(func=cmd_split)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
