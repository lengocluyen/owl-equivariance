"""LM Studio OpenAI-compatible backend for reproducible open-weight inference."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from ..prompting import Prompt
from ..schemas import BenchmarkItem
from .base import RunResult

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_BASE_URL = "http://localhost:1234/v1"
ANSWER_FIELDS = {"content", "reasoning_content", "reasoning", "auto"}


def _json_payload(value: Any) -> dict | None:
    """Convert an SDK response object to release-safe JSON primitives."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    elif isinstance(value, dict):
        payload = value
    elif hasattr(value, "__dict__"):
        payload = json.loads(json.dumps(vars(value), default=lambda obj: vars(obj)))
    else:
        try:
            payload = json.loads(json.dumps(value, default=str))
        except (TypeError, ValueError):
            return {"unserializable_response": repr(value)}
    return payload if isinstance(payload, dict) else {"value": payload}


def _text_value(value: Any) -> str:
    """Normalize OpenAI-compatible string or content-part fields."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        pieces = []
        for part in value:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    pieces.append(text)
        return "".join(pieces)
    return ""


def extract_answer(
    message_payload: dict,
    answer_field: str,
) -> tuple[str, str, dict[str, int]]:
    """Select an explicit assistant field and report every available text channel."""
    if answer_field not in ANSWER_FIELDS:
        raise ValueError(
            f"answer_field must be one of {sorted(ANSWER_FIELDS)}, got {answer_field!r}"
        )
    candidates = {
        "content": _text_value(message_payload.get("content")),
        "reasoning_content": _text_value(message_payload.get("reasoning_content")),
        "reasoning": _text_value(message_payload.get("reasoning")),
    }
    if answer_field == "auto":
        selected = next(
            (
                name
                for name in ("content", "reasoning_content", "reasoning")
                if candidates[name].strip()
            ),
            "content",
        )
    else:
        selected = answer_field
    available = {key: len(value) for key, value in candidates.items() if value}
    return candidates[selected], selected, available


def extract_answer_from_response(
    response_payload: dict,
    answer_field: str,
) -> tuple[str, str, dict[str, int]]:
    """Extract an answer from a stored Chat Completions response."""
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", answer_field if answer_field != "auto" else "content", {}
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    return extract_answer(message, answer_field)


class LMStudioRunner:
    """Run a loaded LM Studio model through `/v1/chat/completions`.

    Chat Completions is used because LM Studio documents JSON-schema constrained output on
    this endpoint. The model identifier is never guessed after construction: preflight must
    confirm that the exact id is loaded, and every response records the served id.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        recorded_model_id: str | None = None,
        max_output_tokens: int = 1024,
        reasoning_effort: str | None = "medium",
        seed: int | None = None,
        answer_field: str = "content",
        request_timeout: float = 600.0,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "the openai package is required for the LM Studio runner; "
                "install with: pip install 'owl-equivariance[api]'"
            ) from exc

        self._openai = openai
        self.base_url = (
            base_url or os.getenv("LM_STUDIO_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        token = api_key or os.getenv("LM_STUDIO_API_TOKEN") or "lm-studio"
        self._client = openai.OpenAI(
            base_url=self.base_url,
            api_key=token,
            # A retry would turn one frozen item into an undocumented variable number of
            # model executions and could hide transient failures from the API-error rate.
            max_retries=0,
            timeout=request_timeout,
        )
        # ``model`` is the exact LM Studio instance id sent to the server.  The
        # publication-facing id may be a frozen study label, but it must never be
        # used as a fuzzy catalog lookup key during loading.
        self.model = model
        self.name = recorded_model_id or model
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.seed = seed
        if answer_field not in ANSWER_FIELDS:
            raise ValueError(
                f"answer_field must be one of {sorted(ANSWER_FIELDS)}, got {answer_field!r}"
            )
        self.answer_field = answer_field
        self.request_timeout = request_timeout

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        request: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "max_tokens": self.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "owl_equivariance_answer",
                    "strict": True,
                    "schema": prompt.schema,
                },
            },
        }
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort
        if self.seed is not None:
            request["seed"] = self.seed

        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**request)
        except self._openai.APIStatusError as exc:
            return RunResult(
                raw_output="",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
                metadata=self._request_metadata(selected_answer_field=self.answer_field),
                response_payload={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "status_code": getattr(exc, "status_code", None),
                    "body": getattr(exc, "body", None),
                },
            )
        except self._openai.APIConnectionError as exc:
            return RunResult(
                raw_output="",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=f"connection error: {exc}",
                metadata=self._request_metadata(selected_answer_field=self.answer_field),
                response_payload={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "provider_response_received": False,
                },
            )
        elapsed_ms = (time.perf_counter() - started) * 1000

        choice = response.choices[0] if response.choices else None
        message = choice.message if choice is not None else None
        response_payload = _json_payload(response)
        message_payload = _json_payload(message) or {}
        # Some LM Studio model adapters expose reasoning fields through ``model_extra``.
        extra = getattr(message, "model_extra", None)
        if isinstance(extra, dict):
            for key, value in extra.items():
                message_payload.setdefault(key, value)
        raw_output, selected_field, available_fields = extract_answer(
            message_payload,
            self.answer_field,
        )
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        return RunResult(
            raw_output=raw_output,
            latency_ms=elapsed_ms,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            error=None if choice is not None else "empty_choices",
            metadata={
                "served_model": getattr(response, "model", self.model),
                "response_id": getattr(response, "id", None),
                "finish_reason": getattr(choice, "finish_reason", None),
                "reasoning_tokens": getattr(details, "reasoning_tokens", None),
                "available_text_fields": available_fields,
                # LM Studio may attach model_info/runtime/stats beyond the OpenAI schema.
                "lmstudio_extra": getattr(response, "model_extra", None),
                **self._request_metadata(selected_answer_field=selected_field),
            },
            response_payload=response_payload,
        )

    def _request_metadata(self, *, selected_answer_field: str) -> dict:
        return {
            "reasoning_effort": self.reasoning_effort,
            "seed": self.seed,
            "base_url": self.base_url,
            "requested_answer_field": self.answer_field,
            "selected_answer_field": selected_answer_field,
            "request_parameters": {
                "model": self.model,
                "max_tokens": self.max_output_tokens,
                "reasoning_effort": self.reasoning_effort,
                "seed": self.seed,
                "response_format": "json_schema_strict",
                "request_timeout_seconds": self.request_timeout,
            },
        }
