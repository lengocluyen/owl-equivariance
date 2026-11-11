"""Claude backend for the Messages API.

Three choices worth stating, because each is forced by the experiment rather than by taste:

**No sampling parameters.** The spec asks for temperature 0. Current Claude models reject
``temperature``/``top_p``/``top_k`` outright (HTTP 400), so that lever does not exist.
Determinism is pursued instead through a fixed prompt, a constrained output schema, and a
single response per item; residual nondeterminism is reported rather than assumed away.
Runs are labelled deterministic only in the sense of one greedy-intent sample per item.

**Structured outputs, not prose parsing.** ``output_config.format`` constrains the reply to
the response schema, so an unparseable answer is a genuine model failure rather than a
formatting accident -- which keeps the invalid-output rate a meaningful statistic.

**Prompt caching on the system prompt.** The system prompt is byte-identical across every
item in a run, so one ``cache_control`` breakpoint turns it into a cache read on all but
the first request. Nothing volatile is allowed above that breakpoint.
"""

from __future__ import annotations

import time

from ..prompting import Prompt
from ..schemas import BenchmarkItem
from .base import RunResult

DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicRunner:
    """Runs benchmark items against a Claude model."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 4096,
        effort: str | None = "medium",
        thinking: str = "adaptive",
        api_key: str | None = None,
    ):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "the anthropic package is required for this runner; "
                "install with: pip install 'owl-equivariance[api]'"
            ) from exc

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model
        self.name = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.thinking = thinking

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        request: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # One breakpoint on the system prompt: it is the entire shared prefix, and it
            # is identical for every item in the run.
            "system": [
                {
                    "type": "text",
                    "text": prompt.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": prompt.user}],
            "output_config": {"format": {"type": "json_schema", "schema": prompt.schema}},
        }
        if self.effort:
            request["output_config"]["effort"] = self.effort
        if self.thinking == "disabled":
            # Only legal at effort `high` or below; the caller is responsible for the pair.
            request["thinking"] = {"type": "disabled"}
        elif self.thinking == "adaptive":
            request["thinking"] = {"type": "adaptive"}

        started = time.perf_counter()
        try:
            response = self._client.messages.create(**request)
        except self._anthropic.APIStatusError as exc:
            return RunResult(raw_output="", error=f"{type(exc).__name__}: {exc}")
        except self._anthropic.APIConnectionError as exc:
            return RunResult(raw_output="", error=f"connection error: {exc}")
        elapsed_ms = (time.perf_counter() - started) * 1000

        if response.stop_reason == "refusal":
            # A safety decline is not a reasoning failure; recorded distinctly so it can be
            # excluded rather than silently counted as a wrong answer.
            return RunResult(
                raw_output="",
                latency_ms=elapsed_ms,
                error="refusal",
                metadata={"stop_reason": "refusal"},
            )

        text = "".join(b.text for b in response.content if b.type == "text")
        return RunResult(
            raw_output=text,
            latency_ms=elapsed_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            metadata={
                "served_model": getattr(response, "model", self.model),
                "response_id": getattr(response, "id", None),
                "stop_reason": response.stop_reason,
                "cache_read_input_tokens": getattr(
                    response.usage, "cache_read_input_tokens", None
                ),
                "cache_creation_input_tokens": getattr(
                    response.usage, "cache_creation_input_tokens", None
                ),
            },
        )
