#!/usr/bin/env python3
"""Freeze a deterministic, stratified subset of complete benchmark orbits."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_rank(seed: int, base_item_id: str) -> str:
    return hashlib.sha256(f"{seed}|{base_item_id}".encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--fraction", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=20260725)
    args = parser.parse_args()

    if not 0 < args.fraction < 1:
        parser.error("--fraction must be strictly between 0 and 1")

    rows = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_base: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_base[row["base_item_id"]].append(row)
    if not by_base:
        raise SystemExit("dataset contains no base-item orbits")

    condition_sets = {
        base: frozenset(row["transform"]["lexical_condition"] for row in orbit)
        for base, orbit in by_base.items()
    }
    expected = next(iter(condition_sets.values()))
    incomplete = [base for base, conditions in condition_sets.items() if conditions != expected]
    if incomplete:
        raise SystemExit(f"incomplete/inconsistent orbits: {incomplete[:5]}")

    strata: dict[tuple, list[str]] = defaultdict(list)
    for base, orbit in by_base.items():
        item = orbit[0]
        task = item["task"]
        key = (
            item["ontology"]["ontology_id"],
            task["type"],
            task["label"],
            task.get("proof_depth"),
        )
        strata[key].append(base)

    target = max(1, round(len(by_base) * args.fraction))
    quotas = {key: math.floor(len(ids) * args.fraction) for key, ids in strata.items()}
    remaining = target - sum(quotas.values())
    order = sorted(
        strata,
        key=lambda key: (
            -(len(strata[key]) * args.fraction - quotas[key]),
            json.dumps(key, sort_keys=True),
        ),
    )
    for key in order:
        if remaining <= 0:
            break
        if quotas[key] < len(strata[key]):
            quotas[key] += 1
            remaining -= 1

    selected: set[str] = set()
    stratum_manifest: list[dict] = []
    for key in sorted(strata, key=lambda value: json.dumps(value, sort_keys=True)):
        ranked = sorted(strata[key], key=lambda base: stable_rank(args.seed, base))
        chosen = ranked[: quotas[key]]
        selected.update(chosen)
        stratum_manifest.append(
            {
                "ontology_id": key[0],
                "task_type": key[1],
                "label": key[2],
                "proof_depth": key[3],
                "available_orbits": len(ranked),
                "selected_orbits": len(chosen),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            if row["base_item_id"] in selected:
                handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")

    manifest = {
        "source": str(args.dataset),
        "source_sha256": sha256_file(args.dataset),
        "output": str(args.output),
        "output_sha256": sha256_file(args.output),
        "seed": args.seed,
        "fraction": args.fraction,
        "available_orbits": len(by_base),
        "selected_orbits": len(selected),
        "conditions": sorted(expected),
        "selected_base_item_ids": sorted(selected),
        "strata": stratum_manifest,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"selected {len(selected)}/{len(by_base)} complete orbits "
        f"({len(selected) / len(by_base):.1%})"
    )
    print(f"subset:   {args.output}")
    print(f"manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
