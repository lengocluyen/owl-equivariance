"""Runner protocol shared by every backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..prompting import Prompt
from ..schemas import BenchmarkItem


@dataclass
class RunResult:
    """A raw model response, before parsing."""

    raw_output: str
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    # Complete provider response, converted to JSON-compatible primitives.  This is kept
    # separately from ``raw_output`` because OpenAI-compatible servers can place useful
    # diagnostics (reasoning channels, finish reasons and runtime data) outside the final
    # assistant content.
    response_payload: dict | None = None


@runtime_checkable
class Runner(Protocol):
    """Anything that can answer a benchmark item.

    The item is passed alongside the prompt so that reference baselines (the symbolic
    oracle, the lexical shortcut classifier) can be implemented behind the same interface
    as a real model and go through the identical parsing and metrics path.
    """

    name: str

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult: ...


def run_batch(runner: Runner, pairs: list[tuple[BenchmarkItem, Prompt]]) -> list[RunResult]:
    """Sequential fallback. Backends with real batching override this."""
    batched = getattr(runner, "run_many", None)
    if callable(batched):
        return batched(pairs)
    return [runner.run(item, prompt) for item, prompt in pairs]
