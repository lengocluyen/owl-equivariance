"""OpenAI Responses API backend with frozen reasoning and structured output settings."""

from __future__ import annotations

import time

from ..prompting import Prompt
from ..schemas import BenchmarkItem
from .base import RunResult

DEFAULT_MODEL = "gpt-5.6-terra"


class OpenAIRunner:
    """Run one certified item through the Responses API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_output_tokens: int = 1024,
        reasoning_effort: str | None = "medium",
        api_key: str | None = None,
    ):
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "the openai package is required for this runner; "
                "install with: pip install 'owl-equivariance[api]'"
            ) from exc

        self._openai = openai
        self._client = openai.OpenAI(api_key=api_key, max_retries=2)
        self.model = model
        self.name = model
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        request: dict = {
            "model": self.model,
            "instructions": prompt.system,
            "input": prompt.user,
            "max_output_tokens": self.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "owl_equivariance_answer",
                    "strict": True,
                    "schema": prompt.schema,
                }
            },
        }
        if self.reasoning_effort:
            request["reasoning"] = {"effort": self.reasoning_effort}

        started = time.perf_counter()
        try:
            response = self._client.responses.create(**request)
        except self._openai.APIStatusError as exc:
            return RunResult(raw_output="", error=f"{type(exc).__name__}: {exc}")
        except self._openai.APIConnectionError as exc:
            return RunResult(raw_output="", error=f"connection error: {exc}")
        elapsed_ms = (time.perf_counter() - started) * 1000

        usage = getattr(response, "usage", None)
        status = getattr(response, "status", None)
        error = None
        if status not in (None, "completed"):
            error = f"response_status:{status}"

        return RunResult(
            raw_output=getattr(response, "output_text", "") or "",
            latency_ms=elapsed_ms,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            error=error,
            metadata={
                "served_model": getattr(response, "model", self.model),
                "response_id": getattr(response, "id", None),
                "status": status,
                "reasoning_effort": self.reasoning_effort,
            },
        )
