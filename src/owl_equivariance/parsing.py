"""Strict response parsing (spec section 19).

Two rules keep the invalid-output rate an honest statistic:

* **No LLM repair.** Asking another model to fix malformed output would make the parse rate
  depend on the very machinery under study.
* **Deterministic repair only, and recorded.** Fenced code blocks and surrounding prose are
  stripped, because those are formatting habits rather than reasoning failures. Every such
  repair is logged in ``repairs`` so metrics can be recomputed with repair disabled.

A cited axiom id that does not exist in the item's context is not silently dropped: it is
recorded in ``unknown_support_ids``, because a model inventing axiom identifiers is a
finding, not noise.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .schemas import BenchmarkItem

VALID_LABELS = {"ENTAILED", "NOT_ENTAILED"}


class ParseErrorKind:
    NO_JSON = "no_json"
    MALFORMED_JSON = "malformed_json"
    MISSING_LABEL = "missing_label"
    INVALID_LABEL = "invalid_label"
    NOT_AN_OBJECT = "not_an_object"
    EMPTY = "empty_output"
    REFUSAL = "refusal"


@dataclass
class ParsedResponse:
    label: str | None = None
    support_axiom_ids: list[str] = field(default_factory=list)
    unknown_support_ids: list[str] = field(default_factory=list)
    error: str | None = None
    repairs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.label is not None


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse(raw: str, item: BenchmarkItem | None = None, allow_repair: bool = True) -> ParsedResponse:
    """Parse one raw model response into a label and a support set."""
    if raw is None or not raw.strip():
        return ParsedResponse(error=ParseErrorKind.EMPTY)

    text = raw.strip()
    repairs: list[str] = []

    if allow_repair:
        fenced = _FENCE.search(text)
        if fenced:
            text = fenced.group(1).strip()
            repairs.append("stripped_code_fence")

    obj, err = _load_object(text, allow_repair, repairs)
    if obj is None:
        return ParsedResponse(error=err, repairs=repairs)
    if not isinstance(obj, dict):
        return ParsedResponse(error=ParseErrorKind.NOT_AN_OBJECT, repairs=repairs)

    if "label" not in obj:
        return ParsedResponse(error=ParseErrorKind.MISSING_LABEL, repairs=repairs)

    label = obj["label"]
    if not isinstance(label, str):
        return ParsedResponse(error=ParseErrorKind.INVALID_LABEL, repairs=repairs)
    normalized = label.strip().upper().replace(" ", "_").replace("-", "_")
    if normalized not in VALID_LABELS:
        return ParsedResponse(error=ParseErrorKind.INVALID_LABEL, repairs=repairs)
    if normalized != label and allow_repair:
        repairs.append("normalized_label")

    support_raw = obj.get("support_axiom_ids") or []
    if not isinstance(support_raw, list):
        support_raw = []
        repairs.append("dropped_non_list_support")

    support: list[str] = []
    unknown: list[str] = []
    known = item.axiom_ids if item is not None else None
    seen: set[str] = set()
    for entry in support_raw:
        if not isinstance(entry, str):
            continue
        sid = entry.strip().strip("[]")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        if known is not None and sid not in known:
            unknown.append(sid)
        else:
            support.append(sid)

    return ParsedResponse(
        label=normalized,
        support_axiom_ids=support,
        unknown_support_ids=unknown,
        repairs=repairs,
    )


def _load_object(text: str, allow_repair: bool, repairs: list[str]):
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        pass

    if not allow_repair:
        return None, ParseErrorKind.MALFORMED_JSON

    # Take the first balanced {...} span: models often wrap the object in prose.
    start = text.find("{")
    if start == -1:
        return None, ParseErrorKind.NO_JSON
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    obj = json.loads(candidate)
                except json.JSONDecodeError:
                    return None, ParseErrorKind.MALFORMED_JSON
                repairs.append("extracted_embedded_object")
                return obj, None
    return None, ParseErrorKind.MALFORMED_JSON
