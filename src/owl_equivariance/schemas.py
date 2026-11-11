"""Typed mirrors of the JSON the Java layer emits, plus the prediction record.

The Java side is the authority on the benchmark format; these models exist so that a
malformed dataset fails loudly at load time rather than producing quietly wrong metrics
several stages later.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Label = Literal["ENTAILED", "NOT_ENTAILED"]


class Axiom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str


class OntologyInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    ontology_id: str
    version: str | None = None
    profile: str | None = None
    source_hash: str | None = None
    transformed_hash: str | None = None


class TaskInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    query_functional: str
    query_text: str | None = None
    label: Label
    positive: bool
    proof_depth: int | None = None
    explicit: bool = False
    negative_kind: str | None = None


class TransformInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    operator: str
    seed: int | None = None
    mapping_id: str | None = None
    lexical_condition: str
    annotation_policy: str | None = None


class LexiconEntry(BaseModel):
    """Surviving lexical annotations for one entity, as the condition left them."""

    model_config = ConfigDict(extra="allow")

    entity: str
    iri: str | None = None
    label: str | None = None
    definition: str | None = None
    synonyms: list[str] | None = None


class ContextInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    axioms: list[Axiom] = Field(default_factory=list)
    lexicon: list[LexiconEntry] = Field(default_factory=list)
    serialization: str = "FUNCTIONAL"
    strategy: str | None = None
    distractor_count: int = 0
    label_preservation_certified: bool = False


class ReferenceInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    support_axiom_sets: list[list[str]] = Field(default_factory=list)
    reasoner: str | None = None
    verified: bool = False


class BenchmarkItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    base_item_id: str
    orbit_item_id: str
    ontology: OntologyInfo
    task: TaskInfo
    transform: TransformInfo
    context: ContextInfo
    reference: ReferenceInfo = Field(default_factory=ReferenceInfo)
    split: str | None = None

    @property
    def condition(self) -> str:
        return self.transform.lexical_condition

    @property
    def axiom_ids(self) -> set[str]:
        return {a.id for a in self.context.axioms}


class Prediction(BaseModel):
    """One model response, after parsing.

    ``label`` is ``None`` when the response could not be parsed. That is deliberately
    distinct from a wrong label: an unparseable answer counts as incorrect in the headline
    metric but is also reported separately, because a model that cannot emit the required
    JSON is failing for a different reason than one that reasons badly (spec section 19.2).
    """

    model_config = ConfigDict(extra="allow")

    orbit_item_id: str
    base_item_id: str
    condition: str
    model: str
    prompt_style: str
    label: Label | None = None
    support_axiom_ids: list[str] = Field(default_factory=list)
    raw_output: str = ""
    # ``runner_error`` and ``parse_error`` are deliberately separate.  A transport/API
    # failure is not the same measurement as a syntactically invalid model response.
    runner_error: str | None = None
    parse_error: str | None = None
    parse_repairs: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    runner_metadata: dict = Field(default_factory=dict)
    # Full JSON response returned by the provider. Required for publication runs so a
    # later parser audit does not require another expensive inference call.
    response_payload: dict | None = None
    # Which repetition this response is, for nondeterministic backends.
    repeat: int = 0

    # Filled in by the Java support validator.
    answer_correct: bool | None = None
    support_valid: bool | None = None
    support_minimal: bool | None = None
    unknown_support_ids: list[str] = Field(default_factory=list)
    redundant_support_ids: list[str] = Field(default_factory=list)
