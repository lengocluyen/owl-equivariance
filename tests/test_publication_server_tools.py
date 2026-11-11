from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from owl_equivariance.prompting import Prompt
from owl_equivariance.runners.lmstudio_api import (
    LMStudioRunner,
    extract_answer_from_response,
)


def test_repeat_subset_is_deterministic_and_keeps_complete_orbits(tmp_path):
    source = tmp_path / "benchmark.jsonl"
    rows = []
    for n in range(20):
        for condition in ("C0", "C4"):
            rows.append(
                {
                    "base_item_id": f"b{n:02}",
                    "orbit_item_id": f"b{n:02}:{condition}",
                    "ontology": {"ontology_id": "toy"},
                    "task": {
                        "type": "ATOMIC_SUBSUMPTION",
                        "label": "ENTAILED" if n % 2 else "NOT_ENTAILED",
                        "proof_depth": n % 3,
                    },
                    "transform": {"lexical_condition": condition},
                }
            )
    source.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    script = Path(__file__).parents[1] / "scripts" / "make_repeat_subset.py"
    outputs = []
    for suffix in ("a", "b"):
        output = tmp_path / f"{suffix}.jsonl"
        manifest = tmp_path / f"{suffix}.manifest.json"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--dataset",
                str(source),
                "--output",
                str(output),
                "--manifest",
                str(manifest),
                "--fraction",
                "0.20",
                "--seed",
                "7",
            ],
            check=True,
        )
        outputs.append(output.read_text(encoding="utf-8"))

    assert outputs[0] == outputs[1]
    selected = [json.loads(line) for line in outputs[0].splitlines()]
    assert len({row["base_item_id"] for row in selected}) == 4
    assert len(selected) == 8


def test_lmstudio_runner_sends_and_records_seed(monkeypatch):
    captured = {}
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"label":"NOT_ENTAILED","support_axiom_ids":[]}'
                ),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        model="served-model",
        id="response-1",
        model_extra=None,
    )

    class FakeCompletions:
        def create(self, **request):
            captured.update(request)
            return response

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = SimpleNamespace(
        OpenAI=FakeOpenAI,
        APIStatusError=RuntimeError,
        APIConnectionError=ConnectionError,
    )
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    runner = LMStudioRunner(
        model="test-model",
        recorded_model_id="frozen-study-label",
        reasoning_effort=None,
        seed=123,
    )
    result = runner.run(
        SimpleNamespace(),
        Prompt(system="system", user="user", style="structured_proof", schema={}),
    )

    assert captured["seed"] == 123
    assert captured["model"] == "test-model"
    assert runner.name == "frozen-study-label"
    assert result.metadata["request_parameters"]["model"] == "test-model"
    assert "reasoning_effort" not in captured
    assert result.metadata["seed"] == 123
    assert result.metadata["selected_answer_field"] == "content"
    assert result.response_payload["id"] == "response-1"


def test_lmstudio_runner_can_audit_reasoning_channel_without_losing_payload(monkeypatch):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    reasoning_content='{"label":"ENTAILED","support_axiom_ids":["A1"]}',
                ),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        model="served-model",
        id="response-2",
        model_extra=None,
    )

    class FakeCompletions:
        def create(self, **_request):
            return response

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_module = SimpleNamespace(
        OpenAI=FakeOpenAI,
        APIStatusError=RuntimeError,
        APIConnectionError=ConnectionError,
    )
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    runner = LMStudioRunner(model="test-model", answer_field="auto")
    result = runner.run(
        SimpleNamespace(),
        Prompt(system="system", user="user", style="structured_proof", schema={}),
    )

    assert result.raw_output.startswith('{"label":"ENTAILED"')
    assert result.metadata["selected_answer_field"] == "reasoning_content"
    assert result.metadata["available_text_fields"]["reasoning_content"] > 0
    assert result.response_payload["id"] == "response-2"
    raw, selected, available = extract_answer_from_response(
        result.response_payload,
        "reasoning_content",
    )
    assert raw == result.raw_output
    assert selected == "reasoning_content"
    assert available["reasoning_content"] == len(raw)
