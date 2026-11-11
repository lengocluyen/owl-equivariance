"""Model backends, resolved by name."""

from __future__ import annotations

from .base import Runner, RunResult, run_batch
from .baselines import BASELINES, LexicalRunner, MajorityRunner, OracleRunner

__all__ = [
    "BASELINES",
    "LexicalRunner",
    "MajorityRunner",
    "OracleRunner",
    "Runner",
    "RunResult",
    "build_runner",
    "run_batch",
]


def build_runner(spec: str, **kwargs) -> Runner:
    """Resolve a runner from a short spec string.

    ``oracle`` / ``majority`` / ``lexical``  -> reference baselines (no dependencies)
    ``anthropic:<model-id>``                 -> Claude via the Messages API
    ``openai:<model-id>``                    -> OpenAI via the Responses API
    ``google:<model-id>``                    -> Gemini via generateContent
    ``lmstudio:<model-id>``                  -> an LM Studio OpenAI-compatible server
    ``hf:<model-id>``                        -> local open-weight model via transformers
    """
    if spec in BASELINES:
        return BASELINES[spec]()

    backend, _, model_id = spec.partition(":")
    max_output_tokens = kwargs.pop("max_output_tokens", None)
    reasoning_effort = kwargs.pop("reasoning_effort", None)
    seed = kwargs.pop("seed", None)
    answer_field = kwargs.pop("answer_field", None)
    request_timeout = kwargs.pop("request_timeout", None)
    recorded_model_id = kwargs.pop("recorded_model_id", None)
    if backend == "anthropic":
        from .anthropic_api import DEFAULT_MODEL, AnthropicRunner

        return AnthropicRunner(
            model=model_id or DEFAULT_MODEL,
            max_tokens=max_output_tokens or 1024,
            effort=reasoning_effort,
            **kwargs,
        )
    if backend == "openai":
        from .openai_api import DEFAULT_MODEL, OpenAIRunner

        return OpenAIRunner(
            model=model_id or DEFAULT_MODEL,
            max_output_tokens=max_output_tokens or 1024,
            reasoning_effort=reasoning_effort,
            **kwargs,
        )
    if backend == "google":
        from .google_api import DEFAULT_MODEL, GoogleRunner

        return GoogleRunner(
            model=model_id or DEFAULT_MODEL,
            max_output_tokens=max_output_tokens or 1024,
            thinking_level=reasoning_effort,
            **kwargs,
        )
    if backend == "lmstudio":
        from .lmstudio_api import DEFAULT_MODEL, LMStudioRunner

        return LMStudioRunner(
            model=model_id or DEFAULT_MODEL,
            recorded_model_id=recorded_model_id,
            max_output_tokens=max_output_tokens or 1024,
            reasoning_effort=reasoning_effort,
            seed=seed,
            answer_field=answer_field or "content",
            request_timeout=request_timeout or 600.0,
            **kwargs,
        )
    if backend == "hf":
        from .hf_runner import HuggingFaceRunner

        if not model_id:
            raise ValueError("hf runner needs a model id, e.g. hf:Qwen/Qwen2.5-7B-Instruct")
        return HuggingFaceRunner(
            model_id=model_id,
            max_new_tokens=max_output_tokens or 512,
            **kwargs,
        )

    raise ValueError(
        f"unknown runner {spec!r}; expected one of {sorted(BASELINES)} "
        "or anthropic:<model>, openai:<model>, google:<model>, "
        "lmstudio:<model>, or hf:<model>"
    )
