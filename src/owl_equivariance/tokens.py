"""Tokenization controls (spec section 24).

Renaming changes how text tokenizes. ``C_000012`` fragments into several tokens where
``macrophage`` may be one or two, so a drop from C0 to C4 could be a tokenization effect
rather than a reasoning one. Section 24 asks two distinct questions and this module answers
both, because a single "token count" column answers neither cleanly:

1. **Is the pseudoword condition actually token-matched to the opaque one?** C5 exists as
   the control for C4's tokenization. If C5's prompts are the same length as C4's, then any
   C4-vs-C5 difference is about *word-likeness*, not fragmentation. If they are not matched,
   that comparison is confounded and must not be made.

2. **How large is the per-condition token shift relative to C0?** This is the covariate the
   regression needs, reported here per condition so the size of the confound is visible
   before any model is fitted.

Counting is done with a real tokenizer when one is available, and with a whitespace proxy
otherwise. Which was used is always reported: a proxy is fine for relative comparison across
conditions but must not be presented as a token count.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from . import prompting
from .schemas import BenchmarkItem


class Counter:
    """A tokenizer, or an honest stand-in for one.

    ``sees_subword`` is the property that matters for the matching check. Fragmentation
    happens *inside* a whitespace token -- ``C_000012`` may be five pieces where
    ``Tavrine`` is two -- so a word count cannot see it at all and will report every
    de-lexicalized condition as identical. A proxy is adequate for prompt *length*, and
    useless for the C4-vs-C5 control.
    """

    def __init__(self, spec: str = "words"):
        self.spec = spec
        self.kind = "whitespace_proxy"
        self.sees_subword = False
        self._encode = None

        if spec.startswith("hf:"):
            try:
                from transformers import AutoTokenizer
            except ImportError as exc:  # pragma: no cover - optional extra
                raise RuntimeError(
                    "transformers is required for tokenizer-based counts; "
                    "install with: pip install 'owl-equivariance[local]'"
                ) from exc
            tokenizer = AutoTokenizer.from_pretrained(spec[3:])
            self._encode = lambda text: len(tokenizer(text)["input_ids"])
            self.kind = f"tokenizer:{spec[3:]}"
            self.sees_subword = True
        elif spec == "chars":
            self._encode = len
            self.kind = "character_proxy"
            # Characters do vary within a word, so this is a crude but non-blind stand-in.
            self.sees_subword = True

    def count(self, text: str) -> int:
        if self._encode is not None:
            return self._encode(text)
        return len(text.split())


@dataclass
class ConditionTokens:
    condition: str
    n: int = 0
    mean: float = 0.0
    median: float = 0.0
    minimum: int = 0
    maximum: int = 0
    mean_delta_vs_reference: float = 0.0
    ratio_vs_reference: float = 1.0

    def as_dict(self) -> dict:
        return {
            "condition": self.condition,
            "n": self.n,
            "mean_tokens": self.mean,
            "median_tokens": self.median,
            "min_tokens": self.minimum,
            "max_tokens": self.maximum,
            "mean_delta_vs_reference": self.mean_delta_vs_reference,
            "ratio_vs_reference": self.ratio_vs_reference,
        }


@dataclass
class MatchCheck:
    """Whether two conditions are close enough in length to be compared as a control."""

    condition_a: str
    condition_b: str
    n_pairs: int
    mean_a: float
    mean_b: float
    mean_abs_difference: float
    relative_difference: float
    matched: bool | None
    tolerance: float
    assessable: bool = True

    def verdict(self) -> str:
        if not self.assessable:
            return (
                f"{self.condition_a} vs {self.condition_b}: NOT ASSESSABLE with this "
                "counter. Fragmentation happens inside a whitespace token, so a word count "
                "reports every de-lexicalized condition as identical regardless of the "
                "truth. Re-run with --tokenizer hf:<model-id>."
            )
        if self.matched:
            return (
                f"{self.condition_a} and {self.condition_b} are token-matched "
                f"({self.relative_difference:.1%} apart): a difference between them is "
                "about word-likeness, not fragmentation"
            )
        return (
            f"{self.condition_a} and {self.condition_b} differ by "
            f"{self.relative_difference:.1%} in length (tolerance {self.tolerance:.0%}): "
            "the comparison is confounded by tokenization and should not be reported as a "
            "meaning effect"
        )

    def as_dict(self) -> dict:
        return {
            "condition_a": self.condition_a,
            "condition_b": self.condition_b,
            "n_pairs": self.n_pairs,
            "mean_tokens_a": self.mean_a,
            "mean_tokens_b": self.mean_b,
            "mean_abs_difference": self.mean_abs_difference,
            "relative_difference": self.relative_difference,
            "matched": self.matched,
            "tolerance": self.tolerance,
            "assessable": self.assessable,
        }


@dataclass
class TokenReport:
    counter_kind: str
    prompt_style: str
    reference: str
    system_overhead: int = 0
    per_condition: list[ConditionTokens] = field(default_factory=list)
    match_checks: list[MatchCheck] = field(default_factory=list)
    length_warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "counter": self.counter_kind,
            "prompt_style": self.prompt_style,
            "reference": self.reference,
            "counts_cover": "user prompt only",
            "system_prompt_overhead": self.system_overhead,
            "per_condition": [c.as_dict() for c in self.per_condition],
            "match_checks": [m.as_dict() for m in self.match_checks],
            "length_warnings": self.length_warnings,
        }


# The two contrasts that only mean something if the pair is token-matched (spec 23.1).
#
#   C4 vs C5 -- opaque identifier vs pseudoword: isolates identifier *morphology*, holding
#               meaning at zero. Requires matched length, or it measures length instead.
#   C6 vs C7 -- irrelevant real word vs actively misleading one: isolates *semantics*,
#               holding word-likeness constant.
#
# C5 vs C6 is deliberately absent. It is not a primary contrast, and the two are matched to
# different targets by design (C5 to the opaque format, C6 to the label), so requiring them
# to match would flag a false confound.
DEFAULT_MATCH_PAIRS = [("C4", "C5"), ("C6", "C7")]


def analyse(
    items: list[BenchmarkItem],
    counter: Counter | None = None,
    reference: str = "C0",
    prompt_style: str = "structured_proof",
    match_pairs: list[tuple[str, str]] | None = None,
    tolerance: float = 0.10,
) -> TokenReport:
    counter = counter or Counter()

    # Counts cover the *user* prompt only. The system prompt is byte-identical for every
    # item and condition, so including it adds a large constant to both sides of every
    # comparison and shrinks relative differences toward zero -- diluting exactly the
    # signal the matching check exists to detect. It is reported once, as overhead.
    counts: dict[str, dict[str, int]] = {}
    system_overhead = 0
    for item in items:
        prompt = prompting.build(item, prompt_style)
        system_overhead = counter.count(prompt.system)
        counts.setdefault(item.condition, {})[item.base_item_id] = counter.count(prompt.user)

    reference_counts = counts.get(reference, {})
    report = TokenReport(
        counter_kind=counter.kind,
        prompt_style=prompt_style,
        reference=reference,
        system_overhead=system_overhead,
    )

    for condition in sorted(counts):
        values = list(counts[condition].values())
        if not values:
            continue
        deltas = [
            counts[condition][b] - reference_counts[b]
            for b in counts[condition]
            if b in reference_counts
        ]
        mean = statistics.fmean(values)
        ref_mean = statistics.fmean(reference_counts.values()) if reference_counts else mean
        report.per_condition.append(
            ConditionTokens(
                condition=condition,
                n=len(values),
                mean=mean,
                median=statistics.median(values),
                minimum=min(values),
                maximum=max(values),
                mean_delta_vs_reference=statistics.fmean(deltas) if deltas else 0.0,
                ratio_vs_reference=(mean / ref_mean) if ref_mean else 1.0,
            )
        )

    for a, b in match_pairs or DEFAULT_MATCH_PAIRS:
        if a not in counts or b not in counts:
            continue
        shared = sorted(set(counts[a]) & set(counts[b]))
        if not shared:
            continue
        mean_a = statistics.fmean(counts[a][k] for k in shared)
        mean_b = statistics.fmean(counts[b][k] for k in shared)
        abs_diff = statistics.fmean(abs(counts[a][k] - counts[b][k]) for k in shared)
        scale = max(mean_a, mean_b, 1.0)
        relative = abs(mean_a - mean_b) / scale
        report.match_checks.append(
            MatchCheck(
                condition_a=a,
                condition_b=b,
                n_pairs=len(shared),
                mean_a=mean_a,
                mean_b=mean_b,
                mean_abs_difference=abs_diff,
                relative_difference=relative,
                matched=(relative <= tolerance) if counter.sees_subword else None,
                tolerance=tolerance,
                assessable=counter.sees_subword,
            )
        )

    # Length differences against the reference are visible to any counter, and on this
    # design they are large: removing the vocabulary block makes a de-lexicalized prompt a
    # fraction of C0's length. That is inherent to the manipulation, not a bug -- but it
    # means the C0 contrast is confounded with prompt length and must be modelled, which is
    # what the token_delta covariate is for.
    for entry in report.per_condition:
        if entry.condition != reference and abs(1.0 - entry.ratio_vs_reference) > tolerance:
            report.length_warnings.append(
                f"{entry.condition} prompts are {entry.ratio_vs_reference:.2f}x the length of "
                f"{reference} ({entry.mean_delta_vs_reference:+.0f} on average); control for "
                "length before attributing the difference to meaning"
            )
    return report


TOKEN_COLUMNS = [
    "condition",
    "n",
    "mean_tokens",
    "median_tokens",
    "min_tokens",
    "max_tokens",
    "mean_delta_vs_reference",
    "ratio_vs_reference",
]
