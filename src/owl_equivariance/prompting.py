"""Prompt construction (spec section 17).

Two design rules, both load-bearing for the study:

1. **The system prompt is identical for every item.** It is the shared prefix that prompt
   caching keys on, and it is also an experimental control: a system prompt that varied by
   condition would be a second manipulation confounded with the renaming.

2. **Only machine-verifiable fields are requested.** The model returns a label and a set of
   context axiom ids. Free-form reasoning is not solicited and is not scored, because a
   prose chain of thought cannot be checked symbolically and grading it with another model
   would import exactly the unreliability under study (spec section 17.4).
"""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import BenchmarkItem

DIRECT_SYSTEM = """\
You decide OWL 2 entailment questions.

You are given a list of OWL axioms and one query axiom. Decide whether the query is \
entailed by the supplied axioms under the OWL 2 Direct Semantics.

Rules:
- Use only the supplied axioms. Do not use outside knowledge.
- Reason under the open-world assumption. An axiom that is not entailed is NOT_ENTAILED; \
this does not mean its negation holds.
- Entity names are arbitrary identifiers. They may be meaningless, or misleading. Decide \
from the logical structure alone.

Reply with a single JSON object and nothing else:
{"label": "ENTAILED" | "NOT_ENTAILED"}\
"""

STRUCTURED_SYSTEM = """\
You decide OWL 2 entailment questions and cite the axioms that support your decision.

You are given a list of OWL axioms, each with an identifier, and one query axiom. Decide \
whether the query is entailed by the supplied axioms under the OWL 2 Direct Semantics.

Rules:
- Use only the supplied axioms. Do not use outside knowledge.
- Reason under the open-world assumption. An axiom that is not entailed is NOT_ENTAILED; \
this does not mean its negation holds.
- Entity names are arbitrary identifiers. They may be meaningless, or misleading. Decide \
from the logical structure alone.
- If the query is entailed, list exactly the axiom identifiers that together entail it: \
every axiom needed, and no axiom that is not needed.
- If the query is not entailed, return an empty support list.

Reply with a single JSON object and nothing else:
{"label": "ENTAILED" | "NOT_ENTAILED", "support_axiom_ids": ["A1", "A2"]}\
"""

# The "ignore names" ablation (spec section 17.3): identical task, one added sentence.
# Comparing it against DIRECT_SYSTEM tests whether the effect survives simply telling the
# model that names carry no information.
IGNORE_NAMES_SUFFIX = (
    "\n\nImportant: the entity names in this problem have been replaced with arbitrary "
    "identifiers. Any apparent meaning in them is accidental and may be actively "
    "misleading. Ignore the names entirely and use only the logical structure."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["ENTAILED", "NOT_ENTAILED"]},
        "support_axiom_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["label", "support_axiom_ids"],
    "additionalProperties": False,
}

DIRECT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": ["ENTAILED", "NOT_ENTAILED"]}},
    "required": ["label"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    style: str
    schema: dict

    @property
    def wants_support(self) -> bool:
        return self.style.startswith("structured")


def _render_axioms(item: BenchmarkItem, use_verbal: bool) -> str:
    lines = []
    for ax in item.context.axioms:
        text = ax.text
        if use_verbal:
            # Functional syntax carries full IRIs; the verbal rendering is local names only.
            text = _shorten(text)
        lines.append(f"[{ax.id}] {text}")
    return "\n".join(lines)


def _shorten(functional: str) -> str:
    """Strip IRIs down to local names for the compact rendering."""
    out: list[str] = []
    i = 0
    while i < len(functional):
        if functional[i] == "<":
            close = functional.find(">", i)
            if close == -1:
                out.append(functional[i:])
                break
            iri = functional[i + 1 : close]
            local = iri.rsplit("#", 1)[-1] if "#" in iri else iri.rsplit("/", 1)[-1]
            out.append(local)
            i = close + 1
        else:
            out.append(functional[i])
            i += 1
    return "".join(out)


def _render_lexicon(item: BenchmarkItem) -> str:
    """The vocabulary block: whatever lexical annotations the condition left in place.

    This is not decoration. OBO ontologies name entities with opaque accession numbers
    (``CL_0000540``), so all their human-readable meaning lives in the annotations. Omitting
    this block would make the label and definition channels invisible to the model and
    collapse C0, C1 and C2 into the same prompt -- the channel decomposition would be
    measuring nothing at all.

    An empty string is the correct rendering for a fully de-lexicalized condition.
    """
    lines = []
    for entry in item.context.lexicon:
        parts = []
        if entry.label:
            parts.append(f'label "{entry.label}"')
        if entry.synonyms:
            parts.append("synonyms " + ", ".join(f'"{s}"' for s in entry.synonyms))
        if entry.definition:
            definition = entry.definition.strip().replace("\n", " ")
            if len(definition) > 300:
                definition = definition[:297] + "..."
            parts.append(f'definition "{definition}"')
        if parts:
            lines.append(f"  {entry.entity}: " + "; ".join(parts))
    return "\n".join(lines)


def build(item: BenchmarkItem, style: str = "structured_proof") -> Prompt:
    """Build the prompt for one item.

    Styles: ``direct``, ``direct_ignore_names``, ``structured_proof``,
    ``structured_proof_short`` (local names instead of full IRIs).
    """
    if style not in _STYLES:
        raise ValueError(f"unknown prompt style {style!r}; known: {sorted(_STYLES)}")
    system, schema, use_verbal = _STYLES[style]

    query = item.task.query_functional
    if use_verbal:
        query = item.task.query_text or _shorten(query)

    sections = []
    vocabulary = _render_lexicon(item)
    if vocabulary:
        sections.append(f"Vocabulary:\n{vocabulary}")
    sections.append(f"Axioms:\n{_render_axioms(item, use_verbal)}")
    sections.append(f"Query:\n{query}")
    sections.append("Is the query entailed by the axioms above?")

    return Prompt(system=system, user="\n\n".join(sections), style=style, schema=schema)


_STYLES: dict[str, tuple[str, dict, bool]] = {
    "direct": (DIRECT_SYSTEM, DIRECT_RESPONSE_SCHEMA, False),
    "direct_ignore_names": (
        DIRECT_SYSTEM + IGNORE_NAMES_SUFFIX,
        DIRECT_RESPONSE_SCHEMA,
        False,
    ),
    "structured_proof": (STRUCTURED_SYSTEM, RESPONSE_SCHEMA, False),
    "structured_proof_short": (STRUCTURED_SYSTEM, RESPONSE_SCHEMA, True),
}


def styles() -> list[str]:
    return sorted(_STYLES)
