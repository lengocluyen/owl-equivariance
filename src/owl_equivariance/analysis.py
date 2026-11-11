"""Tidy long-format export for regression analysis (spec sections 24 and 25.2).

The aggregate tables answer "how big is the effect per condition". They cannot answer
"does the effect survive controlling for tokenization and context length", because that
needs a model with the covariates in it and random effects for item and ontology:

    logit P(correct) ~ condition + proof_depth + context_size + token_delta
                       + task_type + (1 | ontology) + (1 | base_item)

This module emits one row per prediction with every covariate attached, so that model can
be fitted in ``statsmodels``, ``lme4`` or ``brms`` without this package taking on a
mixed-effects dependency it would only use once.

Two covariates matter most and are computed here rather than left to the analyst:

* ``context_chars`` / ``context_axioms`` -- context length, the confound that makes a
  shorter negative answerable without reading.
* ``token_delta`` -- this item's prompt token count minus the same base item's count under
  the reference condition. This is the tokenization control of spec section 24: opaque
  identifiers fragment differently from real words, and an effect that vanishes once
  ``token_delta`` is in the model is a tokenization artifact, not a reasoning result.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import prompting
from .schemas import BenchmarkItem, Prediction


@dataclass
class AnalysisRow:
    # Identifiers / grouping factors
    ontology_id: str
    base_item_id: str
    orbit_item_id: str
    model: str
    prompt_style: str
    # Experimental factor
    condition: str
    operator: str
    seed: int | None
    annotation_policy: str | None
    is_reference: bool
    # Outcome
    correct: int
    predicted_label: str | None
    gold_label: str
    parsed: int
    repeat: int = 0
    runner_error: str | None = None
    parse_error: str | None = None
    answer_field: str | None = None
    finish_reason: str | None = None
    # Proof-level outcome, when the symbolic validator has run
    support_valid: int | None = None
    support_minimal: int | None = None
    n_support_cited: int = 0
    n_support_hallucinated: int = 0
    # Item covariates
    task_type: str = ""
    positive: int = 0
    negative_kind: str | None = None
    proof_depth: int | None = None
    explicit: int = 0
    context_axioms: int = 0
    context_chars: int = 0
    distractor_count: int = 0
    n_lexicon_entries: int = 0
    # Prompt covariates
    prompt_chars: int = 0
    prompt_words: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_delta: int | None = None
    latency_ms: float | None = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ExportResult:
    rows: list[AnalysisRow] = field(default_factory=list)
    missing_items: int = 0
    token_source: str = "none"

    def as_dicts(self) -> list[dict]:
        return [r.as_dict() for r in self.rows]


def build_rows(
    items: list[BenchmarkItem],
    predictions: list[Prediction],
    reference: str = "C0",
    prompt_style: str = "structured_proof",
) -> ExportResult:
    by_id = {i.orbit_item_id: i for i in items}
    result = ExportResult()

    # Prompt size per item, so length covariates describe what the model actually saw
    # rather than the raw context.
    prompt_stats: dict[str, tuple[int, int]] = {}
    for item in items:
        prompt = prompting.build(item, prompt_style)
        text = prompt.system + "\n" + prompt.user
        prompt_stats[item.orbit_item_id] = (len(text), len(text.split()))

    # Reference token counts, keyed by base item, for the token_delta covariate. Real
    # tokenizer counts are used when the runner recorded them; otherwise whitespace words
    # stand in, and which was used is reported rather than left ambiguous.
    ref_tokens: dict[str, int] = {}
    used_real_tokens = False
    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is None or item.condition != reference:
            continue
        if pred.input_tokens is not None:
            ref_tokens[item.base_item_id] = pred.input_tokens
            used_real_tokens = True
        else:
            ref_tokens[item.base_item_id] = prompt_stats[item.orbit_item_id][1]
    result.token_source = "tokenizer" if used_real_tokens else "whitespace_proxy"

    for pred in predictions:
        item = by_id.get(pred.orbit_item_id)
        if item is None:
            result.missing_items += 1
            continue

        chars, words = prompt_stats[item.orbit_item_id]
        own_tokens = pred.input_tokens if pred.input_tokens is not None else words
        baseline = ref_tokens.get(item.base_item_id)
        token_delta = (own_tokens - baseline) if baseline is not None else None

        result.rows.append(
            AnalysisRow(
                ontology_id=item.ontology.ontology_id,
                base_item_id=item.base_item_id,
                orbit_item_id=item.orbit_item_id,
                model=pred.model,
                prompt_style=pred.prompt_style,
                condition=item.condition,
                operator=item.transform.operator,
                seed=item.transform.seed,
                annotation_policy=item.transform.annotation_policy,
                is_reference=item.condition == reference,
                correct=int(pred.label == item.task.label),
                predicted_label=pred.label,
                gold_label=item.task.label,
                parsed=int(pred.label is not None),
                repeat=pred.repeat,
                runner_error=pred.runner_error,
                parse_error=pred.parse_error,
                answer_field=pred.runner_metadata.get("selected_answer_field"),
                finish_reason=pred.runner_metadata.get("finish_reason"),
                support_valid=None if pred.support_valid is None else int(pred.support_valid),
                support_minimal=(
                    None if pred.support_minimal is None else int(pred.support_minimal)
                ),
                n_support_cited=len(pred.support_axiom_ids),
                n_support_hallucinated=len(pred.unknown_support_ids),
                task_type=item.task.type,
                positive=int(item.task.positive),
                negative_kind=item.task.negative_kind,
                proof_depth=item.task.proof_depth,
                explicit=int(item.task.explicit),
                context_axioms=len(item.context.axioms),
                context_chars=sum(len(a.text) for a in item.context.axioms),
                distractor_count=item.context.distractor_count,
                n_lexicon_entries=len(item.context.lexicon),
                prompt_chars=chars,
                prompt_words=words,
                input_tokens=pred.input_tokens,
                output_tokens=pred.output_tokens,
                token_delta=token_delta,
                latency_ms=pred.latency_ms,
            )
        )
    return result


ANALYSIS_COLUMNS = [
    "ontology_id",
    "base_item_id",
    "orbit_item_id",
    "model",
    "prompt_style",
    "condition",
    "operator",
    "seed",
    "annotation_policy",
    "is_reference",
    "correct",
    "predicted_label",
    "gold_label",
    "parsed",
    "repeat",
    "runner_error",
    "parse_error",
    "answer_field",
    "finish_reason",
    "support_valid",
    "support_minimal",
    "n_support_cited",
    "n_support_hallucinated",
    "task_type",
    "positive",
    "negative_kind",
    "proof_depth",
    "explicit",
    "context_axioms",
    "context_chars",
    "distractor_count",
    "n_lexicon_entries",
    "prompt_chars",
    "prompt_words",
    "input_tokens",
    "output_tokens",
    "token_delta",
    "latency_ms",
]


MODEL_RECIPE = """\
# Mixed-effects analysis of the exported long-format table (spec section 25.2).
#
# Python (implemented by this package; logistic GEE clustered by base item):
#     owleq model --analysis analysis.csv --estimator gee --output-dir reports/model
#
# Structured-output validity is a separate outcome, not an analysis restricted to valid
# responses:
#     owleq model --analysis analysis.csv --outcome parsed --estimator gee \
#         --output-dir reports/model-validity
#
# Python sensitivity analysis (variational binomial mixed GLM; with >=5 ontologies,
# random intercepts for both ontology and ontology-qualified base item):
#     owleq model --analysis analysis.csv --estimator bayes_mixed \
#         --ontology-effect random --output-dir reports/model-bayes
#
# R (preferred -- crossed random effects for item and ontology):
#     library(lme4)
#     d <- read.csv("analysis.csv")
#     d$condition <- relevel(factor(d$condition), ref = "C0")
#     m <- glmer(correct ~ condition + proof_depth + context_axioms + token_delta +
#                task_type + (1 | base_item_id) + (1 | ontology_id),
#                data = d, family = binomial)
#     summary(m)
#
# The v3.3 confirmatory primary implementation is scripts/analyze_confirmatory_v33.R,
# which requires at least eight ontologies and fits both random intercepts with
# lme4::glmer (Laplace approximation). With fewer than five ontologies, use ontology as a
# fixed effect instead; a variance component is poorly identified from so few levels.
#
# The condition coefficients are the effect of interest. If they lose significance once
# token_delta and context_axioms are included, the effect is a tokenization or length
# artifact rather than a reasoning one -- which is the question section 24 exists to ask.
"""
