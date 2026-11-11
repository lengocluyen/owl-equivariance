"""Reference baselines (spec section 30).

These are not stand-ins for a model — each one measures a specific property of the
dataset, and the pilot is not interpretable without them.

* :class:`OracleRunner` is the symbolic upper bound. It reports the verified label, so any
  gap between it and a model is the model's, not the benchmark's.
* :class:`LexicalRunner` is the diagnostic that gives the whole study its teeth. It sees
  **only the two entity names in the query** -- never the axioms -- and guesses from their
  surface similarity. If it scores well on C0 and collapses under renaming, that is a
  direct measurement of how much of the task is solvable by lexical shortcut, and it
  calibrates how much of a model's C0 score could be shortcut rather than reasoning.
* :class:`MajorityRunner` is the floor: it checks that the label balance is not itself
  enough to score well.
"""

from __future__ import annotations

import json
import random
import re

from ..prompting import Prompt
from ..schemas import BenchmarkItem
from .base import RunResult


def _emit(label: str, support: list[str], wants_support: bool) -> str:
    payload: dict[str, object] = {"label": label}
    if wants_support:
        payload["support_axiom_ids"] = support
    return json.dumps(payload)


class OracleRunner:
    """Always correct: the symbolic reasoner's own answer, wearing a model's interface."""

    name = "oracle"

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        support: list[str] = []
        if item.task.positive and item.reference.support_axiom_sets:
            support = list(item.reference.support_axiom_sets[0])
        return RunResult(raw_output=_emit(item.task.label, support, prompt.wants_support))


class MajorityRunner:
    """Constant answer. Establishes the accuracy obtainable from label priors alone."""

    name = "majority"

    def __init__(self, label: str = "ENTAILED"):
        self.label = label

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        return RunResult(raw_output=_emit(self.label, [], prompt.wants_support))


class LexicalRunner:
    """Guesses from the query's two entity names alone, ignoring every axiom.

    The heuristic mirrors how a reader skims an ontology question: names that share
    tokens, or where one contains the other, tend to be related, so guess ENTAILED.
    On the original vocabulary this does surprisingly well; on opaque or adversarial
    names it has nothing to work with and degrades to a coin flip -- which is the point.
    """

    name = "lexical"

    def __init__(self, threshold: float = 0.2, seed: int = 0):
        self.threshold = threshold
        self._rng = random.Random(seed)

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        names = _display_names(item)
        if len(names) < 2:
            label = "NOT_ENTAILED"
        else:
            score = _similarity(names[0], names[-1])
            if abs(score - self.threshold) < 1e-9:
                # Exactly on the boundary: break deterministically per item so the
                # baseline is reproducible rather than order-dependent.
                label = "ENTAILED" if self._rng.random() < 0.5 else "NOT_ENTAILED"
            else:
                label = "ENTAILED" if score > self.threshold else "NOT_ENTAILED"
        # Never cites support: it has not looked at a single axiom, and pretending
        # otherwise would corrupt the proof-level metrics.
        return RunResult(raw_output=_emit(label, [], prompt.wants_support))


_IRI = re.compile(r"<([^>]+)>")


def _query_names(functional: str) -> list[str]:
    out = []
    for iri in _IRI.findall(functional):
        local = iri.rsplit("#", 1)[-1] if "#" in iri else iri.rsplit("/", 1)[-1]
        out.append(local)
    return out


def _display_names(item: BenchmarkItem) -> list[str]:
    """The names as the *prompt* presents them: label where one survives, else local name.

    Reading the IRI alone would understate the shortcut badly on OBO ontologies, whose IRIs
    are accession numbers in every condition. The lexical signal a reader actually gets is
    the label, so that is what this baseline must read to measure the shortcut honestly.
    """
    labels = {e.entity: e.label for e in item.context.lexicon if e.label}
    return [labels.get(local, local) for local in _query_names(item.task.query_functional)]


_MIN_ALPHA = 3


def _alpha(name: str) -> str:
    """Lowercased alphabetic content, camelCase split into words.

    Digits and punctuation are discarded before any similarity is computed. Without this,
    identifiers like ``C_000012`` and ``C_000734`` -- or OBO ids like ``CL_0000540`` and
    ``CL_0000541`` -- share most of their character bigrams and a shared ``cl`` token, and
    the baseline reports high similarity for entities that have no lexical content at all.
    That would be fatal to its purpose: this baseline exists to *collapse* under renaming,
    and spurious structural overlap would hide the collapse.
    """
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return re.sub(r"[^a-z ]+", " ", spaced.lower()).strip()


def _tokens(name: str) -> set[str]:
    return {p for p in _alpha(name).split() if p}


def _similarity(a: str, b: str) -> float:
    sa, sb = _alpha(a), _alpha(b)
    # An identifier with essentially no letters carries no lexical signal. Saying so is
    # the honest answer; guessing from digit patterns is not.
    if len(sa.replace(" ", "")) < _MIN_ALPHA or len(sb.replace(" ", "")) < _MIN_ALPHA:
        return 0.0

    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    if sa in sb or sb in sa:
        return 1.0

    union = ta | tb
    jaccard = len(ta & tb) / len(union) if union else 0.0

    ca, cb = sa.replace(" ", ""), sb.replace(" ", "")
    bigrams_a = {ca[i : i + 2] for i in range(len(ca) - 1)}
    bigrams_b = {cb[i : i + 2] for i in range(len(cb) - 1)}
    bi_union = bigrams_a | bigrams_b
    bigram = len(bigrams_a & bigrams_b) / len(bi_union) if bi_union else 0.0
    return 0.6 * jaccard + 0.4 * bigram


BASELINES = {
    "oracle": OracleRunner,
    "majority": MajorityRunner,
    "lexical": LexicalRunner,
}
