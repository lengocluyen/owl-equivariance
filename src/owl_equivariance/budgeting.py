"""No-call budget calculation for a frozen experiment manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .dataset import load_items
from .prompting import build

BUDGET_COLUMNS = ["provider", "model_id", "calls", "input_mtok", "output_mtok", "cost_usd"]


@dataclass
class BudgetReport:
    protocol_id: str
    stage: str
    total_calls: int
    input_tokens_per_model: int
    output_tokens_per_model: int
    rows: list[dict]
    total_cost_usd: float
    hard_cap_usd: float


def _prompt_inventory(stage: dict, style: str, root: Path) -> tuple[int, int, float]:
    """Return primary rows, frozen-repeat rows and mean input-token estimate."""
    planned = stage.get("planned_base_items")
    if planned is not None:
        rows = int(planned) * len(stage["conditions"])
        repeated = round(rows * float(stage.get("repeat_subset_fraction", 0.0)))
        return rows, repeated, float(stage["mean_input_tokens"])

    prompts: list[int] = []
    repeated_rows = 0
    max_orbits = int(stage.get("max_orbits_per_dataset", 0))
    repeat_fraction = float(stage.get("repeat_subset_fraction", 0.0))
    for relative in stage["datasets"]:
        items = load_items(root / relative)
        if max_orbits:
            keep = sorted({x.base_item_id for x in items})[:max_orbits]
            selected = set(keep)
            items = [x for x in items if x.base_item_id in selected]
        if repeat_fraction:
            n_orbits = len({x.base_item_id for x in items})
            conditions = len({x.condition for x in items})
            repeated_rows += round(n_orbits * repeat_fraction) * conditions
        for item in items:
            prompt = build(item, style)
            prompts.append(len(prompt.system) + len(prompt.user))
    if not prompts:
        raise ValueError("stage has no prompts")
    chars_per_token = float(stage.get("characters_per_token", 4.0))
    return len(prompts), repeated_rows, sum(prompts) / len(prompts) / chars_per_token


def estimate(manifest_path: str | Path, stage_name: str, *, ceiling: bool) -> BudgetReport:
    path = Path(manifest_path)
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    stage = config["stages"][stage_name]
    primary_rows, repeated_rows, mean_input = _prompt_inventory(
        stage, config["inference"]["prompt_style"], path.parent.parent
    )
    primary_repeats = int(stage.get("primary_repeats", 1))
    extra_repeats = int(stage.get("extra_repeats", 0))
    calls_per_model = primary_rows * primary_repeats + repeated_rows * extra_repeats

    safety = float(stage.get("input_safety_factor", 1.25))
    input_tokens = round(calls_per_model * mean_input * safety)
    output_per_call = (
        int(config["inference"]["max_output_tokens"])
        if ceiling
        else int(stage["expected_output_tokens"])
    )
    output_tokens = calls_per_model * output_per_call

    rows: list[dict] = []
    total = 0.0
    for model in config["models"]:
        cost = (
            input_tokens * float(model["input_usd_per_mtok"])
            + output_tokens * float(model["output_usd_per_mtok"])
        ) / 1_000_000
        total += cost
        rows.append(
            {
                "provider": model["provider"],
                "model_id": model["model_id"],
                "calls": calls_per_model,
                "input_mtok": f"{input_tokens / 1_000_000:.3f}",
                "output_mtok": f"{output_tokens / 1_000_000:.3f}",
                "cost_usd": f"{cost:.2f}",
            }
        )

    return BudgetReport(
        protocol_id=config["protocol_id"],
        stage=stage_name,
        total_calls=calls_per_model * len(config["models"]),
        input_tokens_per_model=input_tokens,
        output_tokens_per_model=output_tokens,
        rows=rows,
        total_cost_usd=total,
        hard_cap_usd=float(stage.get("hard_cap_usd", 0.0)),
    )
