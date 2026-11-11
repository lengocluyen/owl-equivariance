"""Loading benchmark items and predictions, grouping orbits, and leakage checking."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

from .schemas import BenchmarkItem, Prediction


def read_jsonl(path: str | Path) -> Iterator[dict]:
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: str | Path, records: Iterable) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            payload = r.model_dump(mode="json") if hasattr(r, "model_dump") else r
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def append_jsonl(path: str | Path, record) -> None:
    """Durably append one record.

    Inference may run for days. Persisting every completed response makes ``--resume``
    useful after an interrupted process instead of losing the whole in-memory batch.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        fh.write("\n")
        fh.flush()


def load_items(path: str | Path) -> list[BenchmarkItem]:
    return [BenchmarkItem.model_validate(r) for r in read_jsonl(path)]


def load_predictions(path: str | Path) -> list[Prediction]:
    return [Prediction.model_validate(r) for r in read_jsonl(path)]


def by_orbit(items: Iterable[BenchmarkItem]) -> dict[str, list[BenchmarkItem]]:
    """Group items into orbits: all variants of one base query."""
    out: dict[str, list[BenchmarkItem]] = defaultdict(list)
    for item in items:
        out[item.base_item_id].append(item)
    return dict(out)


def by_condition(items: Iterable[BenchmarkItem]) -> dict[str, list[BenchmarkItem]]:
    out: dict[str, list[BenchmarkItem]] = defaultdict(list)
    for item in items:
        out[item.condition].append(item)
    return dict(out)


def check_leakage(items: Iterable[BenchmarkItem]) -> list[str]:
    """Every member of an orbit must sit in the same split.

    An orbit split across train and test is the worst failure this dataset can have: the
    test item is the training item with the names changed, so the model has already seen
    the problem and the measured robustness is meaningless (spec section 10.5).
    """
    problems: list[str] = []
    for base_id, members in by_orbit(items).items():
        splits = {m.split for m in members}
        if len(splits) > 1:
            problems.append(f"{base_id}: orbit spans splits {sorted(s or '?' for s in splits)}")
    return problems


def check_orbit_consistency(items: Iterable[BenchmarkItem]) -> list[str]:
    """All orbit members must carry the same label and the same context shape."""
    problems: list[str] = []
    for base_id, members in by_orbit(items).items():
        labels = {m.task.label for m in members}
        if len(labels) > 1:
            problems.append(f"{base_id}: orbit members disagree on the label {sorted(labels)}")
        sizes = {len(m.context.axioms) for m in members}
        if len(sizes) > 1:
            problems.append(f"{base_id}: orbit members differ in context size {sorted(sizes)}")
        id_sequences = {tuple(a.id for a in m.context.axioms) for m in members}
        if len(id_sequences) > 1:
            problems.append(f"{base_id}: axiom id ordering drifted between orbit members")
    return problems


def check_non_empty_contexts(items: Iterable[BenchmarkItem]) -> list[str]:
    """No item may ship with an empty axiom list.

    A zero-axiom context is logically valid -- nothing entails the query, so NOT_ENTAILED is
    correct -- and experimentally worthless, because the model can be right without reading
    anything. Certification checks logic; this checks that the item poses a question.
    """
    empty = [i.orbit_item_id for i in items if not i.context.axioms]
    if not empty:
        return []
    return [
        f"{len(empty)} item(s) have an empty context, e.g. {empty[:5]}; "
        "these are answerable without evidence"
    ]


def check_context_size_balance(
    items: Iterable[BenchmarkItem], tolerance: float = 0.25
) -> list[str]:
    """Entailed and non-entailed items must have comparable context sizes.

    If negatives are systematically shorter, context length alone predicts the label and a
    model can score well without reading the axioms at all.
    """
    items = list(items)
    ref = [i for i in items if i.condition == "C0"] or items
    pos = [len(i.context.axioms) for i in ref if i.task.positive]
    neg = [len(i.context.axioms) for i in ref if not i.task.positive]
    if not pos or not neg:
        return []

    mean_pos = sum(pos) / len(pos)
    mean_neg = sum(neg) / len(neg)
    scale = max(mean_pos, mean_neg, 1.0)
    if abs(mean_pos - mean_neg) / scale > tolerance:
        return [
            f"context size differs by label: entailed mean {mean_pos:.1f} vs "
            f"non-entailed mean {mean_neg:.1f} (tolerance {tolerance:.0%}); "
            "length alone may predict the label"
        ]
    return []


def check_condition_leakage(items: Iterable[BenchmarkItem]) -> list[str]:
    """No condition id or seed may be visible in the text shown to the model.

    An IRI like ``urn:owleq:c7:42:c#X`` tells the model which experimental cell it is in --
    that the names are adversarial, or that two variants are the same problem under
    different seeds.
    """
    problems: list[str] = []
    pattern = re.compile(r"\bC\d+(S\d+)?\b", re.IGNORECASE)
    for item in items:
        condition = item.condition.lower()
        seed = str(item.transform.seed) if item.transform.seed is not None else None
        blobs = [a.text for a in item.context.axioms] + [item.task.query_functional]
        for blob in blobs:
            lowered = blob.lower()
            if f":{condition}:" in lowered or f"/{condition}/" in lowered:
                problems.append(f"{item.orbit_item_id}: condition id appears in context text")
                break
            if seed and (f":{seed}:" in lowered and pattern.search(blob)):
                problems.append(f"{item.orbit_item_id}: condition and seed appear in context text")
                break
    return problems[:10]


def check_distinct_seed_mappings(items: Iterable[BenchmarkItem]) -> list[str]:
    """Conditions meant to be *replicate seeds* must produce different renamings.

    Two conditions are replicates when they share an operator **and** an annotation policy
    but differ in seed -- C4/C4S2/C4S3. If their renamings coincide, the self-consistency
    contrast compares a run against itself and reports 0% disagreement regardless of the
    model's behaviour.

    Conditions that share an operator and seed but differ in annotation policy (C1 vs C4)
    are *supposed* to have identical renamings: holding the vocabulary fixed is exactly what
    isolates the annotation channel. Flagging those would be a false alarm.
    """
    by_cond_base: dict[tuple[str, str], BenchmarkItem] = {}
    families: dict[tuple[str, str], dict[str, int | None]] = defaultdict(dict)

    for item in items:
        by_cond_base[(item.condition, item.base_item_id)] = item
        if item.transform.operator == "none":
            continue
        key = (item.transform.operator, item.transform.annotation_policy or "")
        families[key][item.condition] = item.transform.seed

    problems: list[str] = []
    for (operator, policy), conditions in sorted(families.items()):
        ordered = sorted(conditions)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if conditions[a] == conditions[b]:
                    continue  # same seed: identical renamings are the intended behaviour
                compared = identical = 0
                for (cond, base_id) in by_cond_base:
                    if cond != a:
                        continue
                    ia = by_cond_base[(a, base_id)]
                    ib = by_cond_base.get((b, base_id))
                    if ib is None:
                        continue
                    compared += 1
                    if ia.task.query_functional == ib.task.query_functional:
                        identical += 1
                if compared and identical == compared:
                    problems.append(
                        f"conditions {a} (seed {conditions[a]}) and {b} (seed {conditions[b]}) "
                        f"share operator {operator}/{policy} but produce identical renamings "
                        f"on all {compared} items; they are the same condition twice"
                    )
    return problems


def check_mapping_manifests(items: Iterable[BenchmarkItem], dataset_path: str | Path) -> list[str]:
    """Every ``mapping_id`` must resolve to a manifest that exists on disk."""
    root = Path(dataset_path).parent / "mappings"
    missing: set[str] = set()
    for item in items:
        if not item.transform.mapping_id:
            continue
        candidate = root / f"{item.condition}.mapping.json"
        if not candidate.exists():
            missing.add(str(candidate))
    if missing:
        return [
            f"{len(missing)} mapping manifest(s) referenced by the dataset do not exist, "
            f"e.g. {sorted(missing)[:3]}"
        ]
    return []


def validate_dataset(
    items: list[BenchmarkItem],
    dataset_path: str | Path | None = None,
    expected_conditions: list[str] | None = None,
) -> list[str]:
    """Every gate that must pass before the dataset is worth spending inference on.

    Split into two kinds of check. The *logical* ones (certification, support ids) ask
    whether the labels are right. The *experimental* ones (empty contexts, size balance,
    condition leakage, distinct seeds) ask whether the items measure what they claim. A
    dataset can pass the first set completely and still be worthless, which is exactly what
    happened here before these gates existed.
    """
    problems = check_leakage(items) + check_orbit_consistency(items)
    problems += check_non_empty_contexts(items)
    problems += check_context_size_balance(items)
    problems += check_condition_leakage(items)
    problems += check_distinct_seed_mappings(items)
    if dataset_path is not None:
        problems += check_mapping_manifests(items, dataset_path)

    if expected_conditions:
        present = {i.condition for i in items}
        missing = sorted(set(expected_conditions) - present)
        if missing:
            problems.append(f"expected conditions absent from the dataset: {missing}")
        for base_id, members in by_orbit(items).items():
            got = {m.condition for m in members}
            absent = sorted(set(expected_conditions) - got)
            if absent:
                problems.append(f"{base_id}: incomplete orbit, missing {absent}")
                break

    for item in items:
        if not item.context.label_preservation_certified:
            problems.append(f"{item.orbit_item_id}: context is not label-preservation certified")
        known = item.axiom_ids
        for support_set in item.reference.support_axiom_sets:
            unknown = [s for s in support_set if s not in known]
            if unknown:
                problems.append(
                    f"{item.orbit_item_id}: reference support cites unknown ids {unknown}"
                )
    return problems
