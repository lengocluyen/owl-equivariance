"""Local open-weight backend via transformers.

Kept minimal and optional. The pilot's open-weight arm exists so results are reproducible
without API access (spec section 18.1); anything more elaborate belongs in the fine-tuning
stage, not the evaluation harness.
"""

from __future__ import annotations

import time

from ..prompting import Prompt
from ..schemas import BenchmarkItem
from .base import RunResult


class HuggingFaceRunner:
    def __init__(
        self,
        model_id: str,
        max_new_tokens: int = 512,
        device: str | None = None,
        dtype: str = "auto",
    ):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "transformers and torch are required for this runner; "
                "install with: pip install 'owl-equivariance[local]'"
            ) from exc

        self._torch = torch
        self.name = model_id
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            device_map=device or ("cuda" if torch.cuda.is_available() else "cpu"),
        )
        self.model.eval()

    def run(self, item: BenchmarkItem, prompt: Prompt) -> RunResult:
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)

        started = time.perf_counter()
        with self._torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                # Greedy: the primary runs are one deterministic response per item
                # (spec section 18.3). Sampled robustness runs are a separate condition.
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000

        generated = output[0][inputs["input_ids"].shape[-1] :]
        return RunResult(
            raw_output=self.tokenizer.decode(generated, skip_special_tokens=True),
            latency_ms=elapsed_ms,
            input_tokens=int(inputs["input_ids"].shape[-1]),
            output_tokens=int(generated.shape[-1]),
        )

    def token_count(self, text: str) -> int:
        """Exposed for the tokenization controls of spec section 24."""
        return len(self.tokenizer(text)["input_ids"])
