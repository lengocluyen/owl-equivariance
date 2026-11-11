# Publication experiment protocol

**Frozen draft:** 2026-07-25  
**Study type:** certified benchmark, controlled intervention, and robustness defense  
**Primary venue fit:** Journal of Web Semantics benchmark or regular paper  
**Status:** infrastructure pilot complete; confirmatory LLM experiment not yet run

This document is the preregistration-style contract for the full study. It separates what
the repository currently demonstrates from what must be measured before a journal claim is
allowed. It should be frozen, versioned, and included in the release before confirmatory
model inference begins.

## Proposed contribution

The defensible novelty claim is:

> A certified OWL-specific equivariance benchmark that combines typed signature
> isomorphisms, controlled lexical-channel interventions, orbit-level consistency, and
> symbolically validated support equivariance.

The claim is deliberately narrower than “names matter” or “LLMs are not invariant.”
Variable-renaming sensitivity is already studied in general reasoning benchmarks. Existing
ontology benchmarks also test DL/OWL reasoning and proof generation. The contribution here
is their intersection: a semantics-preserving intervention over real OWL ontologies, with
reasoner-certified labels and mechanically checkable cited supports.

Closest work that must be discussed includes:

- Wang et al., *Can Large Language Models Understand DL-Lite Ontologies?* (Findings of
  EMNLP 2024): <https://aclanthology.org/2024.findings-emnlp.141/>
- Yang, Chen, and Sattler, *Large Language Model for OWL Proofs* (WWW 2026):
  <https://arxiv.org/abs/2601.12444>
- Oluçoğlu and Bursa, *DL-ReasonSuite* (Applied Sciences 2026):
  <https://doi.org/10.3390/app16041821>
- *InvariantBench* (2026), which includes symbol and variable-renaming invariants:
  <https://openreview.net/pdf?id=YWMnpol8i1>
- Işık and Li, *Names Don't Matter: Symbol-Invariant Transformer for Open-Vocabulary
  Learning* (2026): <https://arxiv.org/abs/2601.23169>

Journal of Web Semantics explicitly welcomes robust KG-AI evaluation, benchmarking,
auditing, provenance, LLM/KG integration, and benchmark papers with extensive evaluation:
<https://www.sciencedirect.com/journal/journal-of-web-semantics/publish/guide-for-authors>.

## Research questions and hypotheses

### Confirmatory question

**RQ1.** Does removing all lexical information through a typed OWL signature isomorphism
change model correctness even though the entailment problem is unchanged?

**H1.** For at least one preregistered model family, accuracy under C4 is lower than under
C0 on the same base items. The estimand is
`P(correct | C0) - P(correct | C4)`.

**Falsification.** H1 is not supported if the Holm-adjusted paired test is not significant
and the 95% paired interval excludes no practically important degradation. A null result is
publishable only as a well-powered invariance finding, not re-described as “partial
sensitivity.”

### Key secondary questions

**RQ2.** Which channel carries the effect: IRI local names, labels, definitions, token
morphology, or misleading semantics?

**H2.** Single-channel contrasts differ: C0–C1, C0–C2, C0–C3, C4–C5, C6–C7, and C4–C8.
These form one preregistered family and receive Holm correction.

**RQ3.** Are answers and cited supports equivariant at orbit level?

**H3.** Robust orbit accuracy and proof-validity orbit accuracy are lower than the
corresponding C0 accuracy. Support equivariance is computed only when both compared
supports are valid and non-empty; coverage is always reported.

**RQ4.** Can a correct answer conceal an invalid proof?

**H4.** `caip_joint = P(correct ∧ invalid support)` is non-zero for at least one model and
condition, and `caip_given_correct` increases under at least one lexical intervention.
Both quantities must be reported because they answer different questions.

**RQ5.** Does the effect survive tokenization, context length, proof depth, ontology, task
type, and model family controls?

**H5.** The preregistered condition effect remains directionally stable in a clustered
logistic model with these covariates.

**RQ6.** Does an equivariance defense transfer to unseen ontologies and unseen renaming
families?

**H6.** The defense improves robust orbit accuracy on held-out ontologies without reducing
C0 accuracy by more than 2 percentage points.

## Experimental units and scope

The independent experimental unit is a **base item**. Its condition variants form one
orbit and must never be split across train, validation, or test.

Minimum confirmatory scope:

| Dimension | Minimum | Preferred journal target |
|---|---:|---:|
| public ontologies | 5 | 6–8 |
| non-OBO modelling styles | 2 | 3 |
| ontologies with ABox assertions | 2 | 3 |
| base items per ontology | 200 | 300–500 |
| task families | 3 | 4+ |
| model families | 3 | 3–4 |
| exact model checkpoints/endpoints | 6 | 8–10 |
| lexical conditions | 10 | all C0–C9 plus two C4 seeds |

Candidate ontologies must first pass license, profile, consistency, and prompt-size
screening. The final list is frozen before confirmatory inference. It must include
meaningful-IRI ontologies; an all-OBO study cannot identify the IRI-name channel because
OBO IRIs are already accession codes.

Required task families are atomic subsumption, EL expression subsumption, and instance
checking. A fourth family may be consistency or property-oriented reasoning only if the
chosen reasoner completely decides it. Unsupported tasks are omitted, never weakly
labelled by another model.

## Model sampling

The hosted primary audit uses the six exact endpoints frozen in
`configs/publication_experiment.yaml`: `gpt-5.6-terra`, `gpt-5.6-luna`,
`claude-opus-4-8`, `claude-sonnet-5`, `gemini-3.6-flash`, and
`gemini-3.5-flash-lite`. This is a two-tier comparison within each of three independent
providers. The symbolic oracle, majority baseline, and lexical-only baseline are
calibration, not evidence about LLMs.

The defense experiment remains open-weight and is reported as a separate intervention arm.
Its checkpoint and revision must be frozen before training. It is not silently substituted
into the six-model hosted audit, because local/cloud inference engines and quantization
would otherwise confound the primary provider comparison.

Record endpoint/checkpoint, provider-returned served version, revision where available,
inference engine, context limit, system prompt, reasoning/thinking level, output ceiling,
structured-output mode, token usage, response id, and execution date.
Moving aliases such as “latest” are prohibited.

Use one greedy-intent run for the complete matrix. On a preregistered 20% stratified subset,
run three repeats to estimate residual nondeterminism. The subset is stratified by
ontology, task, label, proof depth, and condition and selected before inference.

## Conditions and controls

The confirmatory matrix includes:

- C0: original IRIs and lexical annotations;
- C1: opaque IRIs, annotations retained;
- C2: labels removed;
- C3: definitions removed;
- C4 and C4S2: all lexical content removed under two distinct mappings;
- C5: pseudoword tokenization control;
- C6: irrelevant real-word names;
- C7: semantically misleading names;
- C8: misleading labels on opaque identifiers;
- C9: adversarial IRI names with annotations retained.

C4/C4S2 is a self-consistency test. C4/C5 and C6/C7 are interpretable only after
model-specific tokenizer checks. If a matched pair exceeds the preregistered 10% median
token difference, its semantic contrast becomes exploratory or the generator must be
rebalanced before any model run.

The prompt contains only the certified context, query, surviving vocabulary annotations,
and output schema. Condition names, seeds, mapping identifiers, gold labels, and source
ontology identifiers must not be visible to the model.

## Sampling and adequacy

Discovery and confirmatory data are separated by ontology:

1. Use CL and PO only for generator debugging, effect-size simulation, and cost estimation.
2. Freeze code, conditions, prompts, exclusions, and model versions.
3. Build at least three new held-out public ontologies for the confirmatory analysis.
4. Never use confirmatory outcomes to change negative sampling, context construction, or
   the primary contrast.

Per ontology, sample balanced positives and matched negatives. Negatives retain the
positive subject and use a reasoner-rejected sibling or nearby alternative. Every context
must:

- contain at least one logical axiom;
- preserve the full-ontology label;
- contain the positive justification when applicable;
- be within 25% mean size between labels, with per-item pairing preferred;
- respect the prompt token budget;
- have all expected orbit members and mapping manifests.

Power is determined by simulation after the discovery pilot and before confirmatory
inference. The simulation resamples complete base-item orbits and preserves observed
discordance. The target is at least 80% power for a 5 percentage-point C0–C4 paired
accuracy gap after multiplicity correction. The resulting base-item count is rounded up
and frozen; no optional stopping is allowed.

## Outcomes

Primary outcome:

- paired C0–C4 correctness difference with a 95% item-clustered interval.

Key secondary outcomes:

- exact McNemar p-value and Holm-adjusted p-value;
- correct-to-wrong and wrong-to-correct flip rates;
- robust orbit accuracy and orbit consistency;
- C4/C4S2 answer disagreement;
- proof-validity orbit accuracy;
- `caip_joint` and `caip_given_correct`;
- support-set Jaccard under the shared axiom identifiers, with valid-pair coverage;
- invalid-output and hallucinated-axiom-ID rates;
- latency and input/output tokens as cost outcomes.

Accuracy, macro F1, classwise precision/recall, effect sizes, raw p-values, adjusted
p-values, and confidence intervals are all released. A p-value without its paired effect
size is not a reportable result.

## Statistical analysis

The confirmatory analysis is paired throughout.

1. Use exact McNemar tests for each condition against C0.
2. Apply Holm correction within each preregistered condition family and model.
3. Use paired bootstrap intervals that resample base items, not condition rows.
4. Use orbit-level permutation tests as a sensitivity analysis.
5. Fit a logistic GEE clustered by base item for population-averaged effects.
6. Fit an R `lme4::glmer` sensitivity model with crossed item and ontology intercepts once
   there are enough ontology levels. With fewer than five ontologies, ontology is fixed.
7. Include condition, proof depth, context axioms, model-specific token delta, task type,
   ontology, and model family; test prespecified condition × model-family and condition ×
   task-type interactions.
8. Do not pool repeated model samples as independent observations. Add run as a repeated
   factor or summarize instability on the repeated subset.

Proof metrics are defined over positive queries. Negative answers do not have an
entailing support and must not be credited as “valid empty proofs.”

## Defense experiment

The journal version requires one modest, testable defense:

- **training condition:** ordinary examples versus typed-isomorphism augmentation;
- **augmentation:** randomly sample a fresh typed mapping per epoch on training
  ontologies, with an optional consistency loss across orbit members;
- **held-out tests:** unseen ontologies, unseen opaque seeds, and the unseen adversarial
  C7/C9 family;
- **comparison:** same base model, training budget, number of examples, and decoding;
- **success criterion:** at least +5 points robust orbit accuracy, C0 loss no worse than
  2 points, and no increase in `caip_given_correct`.

A deterministic symbolic canonicalizer may be included as a non-learning upper-control,
but it is not a substitute for evaluating a transferable model defense.

## Exclusions and stopping rules

Exclude an item only for a preregistered, machine-detectable reason:

- reasoner cannot decide the query;
- full ontology or context fails certification;
- context is empty or exceeds the token limit;
- orbit incomplete, mapping non-bijective, or mapping manifest absent;
- prompt contains condition/seed leakage;
- API returns no billable response after the fixed retry policy.

Model parse failures remain in the denominator as incorrect. Do not remove difficult
items, outlier latencies, or models because their results weaken the hypothesis.

Stop a run only for a documented budget cap, provider outage, corrupted artifact, or
failed preregistered gate. Resume from the saved item IDs. Changing the prompt, parser,
dataset, or model version creates a new run identifier and invalidates pooling with the
old run.

## Material Passport

| Component | Required record |
|---|---|
| source ontologies | download URL, version IRI, license, raw SHA-256, canonical SHA-256 |
| generated data | builder configuration, seed, condition list, context distributions |
| mappings | full typed mapping manifest per condition |
| Java software | JDK, Maven, OWLAPI, ELK, jar hash, test report |
| Python software | Python version, exact dependency lock, test report |
| models | immutable endpoint/checkpoint and all inference settings |
| hardware | CPU, RAM, GPU, driver, precision, quantization |
| prompts | exact system/user templates and serialization |
| outputs | raw response, parse result, support-validation result, tokens, latency |
| analysis | frozen script, bootstrap/permutation seed, tables, figures, model summaries |

The complete artifact bundle is released where model-provider terms permit. If raw text
cannot be redistributed, release hashes, parsed outputs, aggregate counts, and a script
that authorized users can rerun.

## Current readiness and go/no-go

| Requirement | Current state | Journal gate |
|---|---|---|
| symbolic construction and transformations | implemented and tested | pass |
| non-empty, label-balanced contexts | CL and PO pass | pass |
| mapping/provenance manifests | CL and PO pass | pass |
| answer/orbit/proof metrics | implemented | pass |
| multiplicity and clustered modeling | implemented | pass |
| public ontology coverage | two, both OBO | fail |
| task-family coverage | atomic subsumption only on public data | fail |
| real LLM matrix | not run | fail |
| model-specific token controls | not run | fail |
| transferable defense | not implemented/evaluated | fail |

The present repository supports a rigorous pilot and a benchmark/tool paper artifact. It
does **not yet support a top-tier journal empirical claim**. Proceed to paid inference only
after the ontology/task expansion, tokenizer checks, power simulation, and protocol freeze.
