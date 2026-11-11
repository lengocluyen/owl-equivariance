"""Google Gemini backend using structured JSON generation."""

from __future__ import annotations

import time

from ..prompting import Prompt
from ..schemas import BenchmarkItem
from .base import RunResult

DEFAULT_MODEL = "gemini-3.6-flash"


class GoogleRunner:
    """Run one certified item through the Gemini Generate Content API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_output_tokens: int = 1024,
        thinking_level: str | None = "medium",
        api_key: str | None = None,
    ):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "the google-genai package is required for this runner; "
                "install with: pip install 'owl-equivariance[api]'"
            ) from exc

        self._genai = genai
        self._types = types
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self.model = model
        self.name = model
        self.max_output_tokens = max_output_tokens
        self.thinking_level = thinking_level

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        thinking = None
        if self.thinking_level:
            thinking = self._types.ThinkingConfig(thinking_level=self.thinking_level)
        config = self._types.GenerateContentConfig(
            system_instruction=prompt.system,
            response_mime_type="application/json",
            response_json_schema=prompt.schema,
            max_output_tokens=self.max_output_tokens,
            thinking_config=thinking,
        )

        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt.user,
                config=config,
            )
        except Exception as exc:  # SDK exception classes vary between major releases
            return RunResult(raw_output="", error=f"{type(exc).__name__}: {exc}")
        elapsed_ms = (time.perf_counter() - started) * 1000

        usage = getattr(response, "usage_metadata", None)
        candidate = (getattr(response, "candidates", None) or [None])[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        return RunResult(
            raw_output=getattr(response, "text", "") or "",
            latency_ms=elapsed_ms,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            metadata={
                "served_model": self.model,
                "response_id": getattr(response, "response_id", None),
                "model_version": getattr(response, "model_version", None),
                "finish_reason": str(finish_reason) if finish_reason is not None else None,
                "thoughts_tokens": getattr(usage, "thoughts_token_count", None),
                "total_tokens": getattr(usage, "total_token_count", None),
                "thinking_level": self.thinking_level,
            },
        )
