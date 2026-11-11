"""Regenerate the semantic-consistency manuscript figures from archived results.

Usage:
    python generate_figures.py --input PATH/primary_analysis.csv

The script uses the Python standard library, matplotlib, and numpy. Primary
metrics are recomputed from primary_analysis.csv. Repeat rates are aggregated
from models/<model>/<ontology>/stability/stability.json with item counts as
weights. Their numerators and denominators are exported for traceability.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm


MODEL_LABELS = {
    "gemma-4-26b-a4b-owleq-v33": "Gemma",
    "llama-3.3-70b-owleq-v33": "Llama",
    "mistral-small-3.2-owleq-v33": "Mistral",
    "gpt-oss-120b-owleq-v33": "GPT-OSS-120B",
    "qwen3.6-35b-a3b-owleq-v33": "Qwen",
    "gpt-oss-20b-owleq-v33": "GPT-OSS-20B",
}
MODELS = list(MODEL_LABELS.values())
CONDITIONS = ["C0", "C1", "C2", "C3", "C4", "C4S2", "C5", "C6", "C7", "C8", "C9"]
ONTOLOGIES = ["eco", "envo", "foodon", "go", "hp", "mondo", "obi", "so", "uberon"]

# Okabe--Ito palette; the same mapping is used in every figure.
COLORS = {
    "Gemma": "#0072B2",
    "Llama": "#009E73",
    "Mistral": "#E69F00",
    "GPT-OSS-120B": "#CC79A7",
    "Qwen": "#56B4E9",
    "GPT-OSS-20B": "#D55E00",
}
MARKERS = ["o", "s", "^", "D", "P", "X"]


def ratio(pair: list[int]) -> float:
    return pair[0] / pair[1] if pair[1] else float("nan")


def save_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def load_repeat_metrics(root: Path) -> dict[str, dict[str, int | float]]:
    """Weight each stability cell by its number of complete repeated inputs."""
    metrics = {}
    for key, model in MODEL_LABELS.items():
        paths = sorted((root / key).glob("*/stability/stability.json"))
        expected_sources = {f"{ontology}_" for ontology in ONTOLOGIES}
        observed_sources = {path.parent.parent.name for path in paths}
        if observed_sources != expected_sources or len(paths) != len(ONTOLOGIES):
            raise ValueError(f"Incomplete stability source coverage for {key}: {observed_sources}")
        total = unanimous = valid_unanimous = 0
        for path in paths:
            summary = json.loads(path.read_text(encoding="utf-8"))
            if summary["expected_repeats"] != 3:
                raise ValueError(f"Expected three executions per input in {path}")
            seen = set()
            for row in summary["by_model_condition"]:
                if row["model"] != key or row["condition"] in seen:
                    raise ValueError(f"Unexpected or duplicate stability cell in {path}")
                seen.add(row["condition"])
                n = int(row["complete_items"])
                if n != int(row["n_items"]):
                    raise ValueError(f"Incomplete repeat inputs in {path}")
                counts = []
                for field in ("unanimous_label_rate", "unanimous_valid_label_rate"):
                    count = float(row[field]) * n
                    if abs(count - round(count)) > 1e-6:
                        raise ValueError(f"Rate does not recover an integer count: {path}, {field}")
                    counts.append(round(count))
                total += n
                unanimous += counts[0]
                valid_unanimous += counts[1]
            if seen != set(CONDITIONS):
                raise ValueError(f"Incomplete condition coverage in {path}")
        if total != 3212:
            raise ValueError(f"Expected 3,212 repeated input variants for {key}, got {total}")
        metrics[model] = {
            "n_inputs": total,
            "unanimous_labels": unanimous,
            "unanimous_valid_labels": valid_unanimous,
            "label_unanimity": unanimous / total,
            "valid_label_unanimity": valid_unanimous / total,
        }
    return metrics


def load_metrics(path: Path):
    correct_by_mc = defaultdict(lambda: [0, 0])
    correct_by_mo = defaultdict(lambda: [0, 0])
    correct_by_ml = defaultdict(lambda: [0, 0])
    correct_by_m = defaultdict(lambda: [0, 0])
    orbit_rows = defaultdict(list)

    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            model = MODEL_LABELS[row["model"]]
            condition = row["condition"]
            ontology = row["ontology_id"]
            correct = int(row["correct"])
            gold = row["gold_label"]
            key = row["base_item_id"]
            support_valid = row["support_valid"]

            for bucket, bucket_key in (
                (correct_by_mc, (model, condition)),
                (correct_by_mo, (model, ontology)),
                (correct_by_ml, (model, gold)),
                (correct_by_m, model),
            ):
                bucket[bucket_key][0] += correct
                bucket[bucket_key][1] += 1

            orbit_rows[(model, ontology, key)].append((condition, correct, gold, support_valid))

    robust = defaultdict(lambda: [0, 0])
    proof_orbit = defaultdict(lambda: [0, 0])
    for (model, _, _), rows in orbit_rows.items():
        if len(rows) != len(CONDITIONS) or {r[0] for r in rows} != set(CONDITIONS):
            raise ValueError(f"Incomplete or duplicate problem family for {model}")
        if len({r[2] for r in rows}) != 1:
            raise ValueError(f"Inconsistent family gold labels for {model}")
        robust[model][0] += int(len(rows) == len(CONDITIONS) and all(r[1] == 1 for r in rows))
        robust[model][1] += 1
        if rows[0][2] == "ENTAILED":
            valid = len(rows) == len(CONDITIONS) and all(
                r[1] == 1 and str(r[3]).strip() in {"1", "1.0", "True", "true"}
                for r in rows
            )
            proof_orbit[model][0] += int(valid)
            proof_orbit[model][1] += 1

    return correct_by_mc, correct_by_mo, correct_by_ml, correct_by_m, robust, proof_orbit


def annotate_heatmap(ax, values, fmt="{:.1f}"):
    threshold = 0.62 * np.nanmax(np.abs(values))
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            value = values[i, j]
            color = "white" if abs(value) >= threshold else "black"
            ax.text(j, i, fmt.format(value), ha="center", va="center", fontsize=7.3, color=color)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("figures"))
    parser.add_argument("--stability-root", type=Path, help="Model summary root; defaults to INPUT.parent/models")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data_dir = args.output / "figure_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    mc, mo, ml, overall, robust, proof_orbit = load_metrics(args.input)
    repeats = load_repeat_metrics(args.stability_root or args.input.parent / "models")
    for model in MODELS:
        if overall[model][1] != 16060 or robust[model][1] != 1460 or proof_orbit[model][1] != 730:
            raise ValueError(f"Primary metric denominator mismatch for {model}")

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    # Figure 2: within-model accuracy changes relative to C0.
    delta_conditions = CONDITIONS[1:]
    delta = np.array(
        [
            [100 * (ratio(mc[(m, c)]) - ratio(mc[(m, "C0")])) for c in delta_conditions]
            for m in MODELS
        ]
    )
    fig, ax = plt.subplots(figsize=(7.35, 3.25), constrained_layout=True)
    norm = TwoSlopeNorm(vmin=-18, vcenter=0, vmax=6)
    image = ax.imshow(delta, cmap="PuOr", norm=norm, aspect="auto")
    ax.set_xticks(range(len(delta_conditions)), delta_conditions)
    ax.set_yticks(range(len(MODELS)), MODELS)
    ax.set_xlabel("Presentation condition (same entailment label)")
    ax.set_title("Change in answer accuracy relative to C0 (percentage points)", loc="left", weight="bold")
    annotate_heatmap(ax, delta)
    cbar = fig.colorbar(image, ax=ax, shrink=0.88, pad=0.02)
    cbar.set_label("Δ accuracy (pp)")
    fig.savefig(args.output / "condition_delta_heatmap.pdf", bbox_inches="tight")
    plt.close(fig)
    save_csv(
        data_dir / "condition_delta.csv",
        ["model", *delta_conditions],
        [[m, *[f"{v:.4f}" for v in row]] for m, row in zip(MODELS, delta)],
    )

    # Figure 3: label profiles and repeatability versus all-condition correctness.
    fig, axes = plt.subplots(1, 2, figsize=(7.35, 3.15), constrained_layout=True)
    ax = axes[0]
    label_offsets_a = {
        "Gemma": (-40, -13),
        "Llama": (-42, 6),
        "Mistral": (5, -9),
        "GPT-OSS-120B": (-58, 5),
        "Qwen": (-33, -15),
        "GPT-OSS-20B": (-50, 5),
    }
    for idx, model in enumerate(MODELS):
        x = ratio(ml[(model, "NOT_ENTAILED")])
        y = ratio(ml[(model, "ENTAILED")])
        ax.scatter(x, y, s=54, color=COLORS[model], marker=MARKERS[idx], edgecolor="black", linewidth=0.4, label=model)
        ax.annotate(
            model.replace("GPT-OSS-", "GPT-"),
            (x, y),
            xytext=label_offsets_a[model],
            textcoords="offset points",
            fontsize=7,
        )
    ax.plot([0, 1], [0, 1], color="0.45", lw=0.9, ls="--")
    ax.set_xlim(0.08, 1.02)
    ax.set_ylim(0.08, 1.02)
    ax.set_xlabel("Accuracy: not-entailed queries")
    ax.set_ylabel("Accuracy: entailed queries")
    ax.set_title("(a) Opposite decision biases", loc="left", weight="bold")
    ax.grid(alpha=0.18)

    ax = axes[1]
    label_offsets_b = {
        "Gemma": (6, 7),
        "Llama": (6, -7),
        "Mistral": (6, 0),
        "GPT-OSS-120B": (-26, -17),
        "Qwen": (5, 8),
        "GPT-OSS-20B": (6, -9),
    }
    for idx, model in enumerate(MODELS):
        x = repeats[model]["label_unanimity"]
        y = ratio(robust[model])
        ax.scatter(x, y, s=54, color=COLORS[model], marker=MARKERS[idx], edgecolor="black", linewidth=0.4)
        ax.annotate(
            model.replace("GPT-OSS-", "GPT-"),
            (x, y),
            xytext=label_offsets_b[model],
            textcoords="offset points",
            fontsize=7,
        )
    ax.set_xlim(0.925, 1.045)
    ax.set_ylim(0.44, 0.71)
    ax.set_xlabel("Repeat label agreement")
    ax.set_ylabel("All-condition accuracy")
    ax.set_title("(b) Repeats and equivalent variants", loc="left", weight="bold")
    ax.grid(alpha=0.18)
    fig.savefig(args.output / "behavioral_profiles.pdf", bbox_inches="tight")
    plt.close(fig)

    save_csv(
        data_dir / "model_profiles.csv",
        ["model", "entailed_accuracy", "not_entailed_accuracy", "robust_orbit_accuracy", "repeat_unanimity"],
        [
            [
                m,
                f"{ratio(ml[(m, 'ENTAILED')]):.6f}",
                f"{ratio(ml[(m, 'NOT_ENTAILED')]):.6f}",
                f"{ratio(robust[m]):.6f}",
                f"{repeats[m]['label_unanimity']:.6f}",
            ]
            for m in MODELS
        ],
    )
    save_csv(
        data_dir / "repeat_agreement.csv",
        ["model", "n_inputs", "unanimous_labels", "unanimous_valid_labels", "label_unanimity", "valid_label_unanimity"],
        [[m, *[repeats[m][field] for field in ("n_inputs", "unanimous_labels", "unanimous_valid_labels", "label_unanimity", "valid_label_unanimity")]] for m in MODELS],
    )

    # Figure 4: ontology-by-model accuracy.
    ontology_matrix = np.array([[100 * ratio(mo[(m, o)]) for o in ONTOLOGIES] for m in MODELS])
    fig, ax = plt.subplots(figsize=(7.35, 3.35), constrained_layout=True)
    image = ax.imshow(ontology_matrix, cmap="YlGnBu", vmin=50, vmax=100, aspect="auto")
    ax.set_xticks(range(len(ONTOLOGIES)), [o.upper() if o in {"eco", "go", "hp", "obi", "so"} else o.title() for o in ONTOLOGIES])
    ax.set_yticks(range(len(MODELS)), MODELS)
    ax.set_xlabel("Ontology source")
    ax.set_title("Answer accuracy by model and ontology (%)", loc="left", weight="bold")
    for i in range(ontology_matrix.shape[0]):
        for j in range(ontology_matrix.shape[1]):
            value = ontology_matrix[i, j]
            ax.text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=7.1, color="white" if value > 82 else "black")
    cbar = fig.colorbar(image, ax=ax, shrink=0.88, pad=0.02)
    cbar.set_label("Accuracy (%)")
    fig.savefig(args.output / "ontology_model_heatmap.pdf", bbox_inches="tight")
    plt.close(fig)
    save_csv(
        data_dir / "ontology_model_accuracy.csv",
        ["model", *ONTOLOGIES],
        [[m, *[f"{v:.4f}" for v in row]] for m, row in zip(MODELS, ontology_matrix)],
    )

    # Figure 5: different evaluation criteria; denominators are not identical.
    x = np.arange(len(MODELS))
    width = 0.23
    answer = np.array([ratio(overall[m]) for m in MODELS])
    orbit = np.array([ratio(robust[m]) for m in MODELS])
    proof = np.array([ratio(proof_orbit[m]) for m in MODELS])
    fig, ax = plt.subplots(figsize=(7.35, 3.35), constrained_layout=True)
    ax.bar(x - width, answer, width, label="Answer accuracy", color="#0072B2")
    ax.bar(x, orbit, width, label="All-condition accuracy", color="#E69F00")
    ax.bar(x + width, proof, width, label="Proof-valid family accuracy", color="#009E73")
    ax.set_xticks(x, [m.replace("GPT-OSS-", "GPT-") for m in MODELS], rotation=20, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Proportion")
    ax.set_title("Model comparison across answer and support measures", loc="left", weight="bold")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.23), frameon=False, fontsize=7)
    fig.savefig(args.output / "evaluation_ladder.pdf", bbox_inches="tight")
    plt.close(fig)
    save_csv(
        data_dir / "evaluation_ladder.csv",
        ["model", "answer_accuracy", "robust_orbit_accuracy", "proof_valid_orbit_accuracy"],
        [[m, f"{a:.6f}", f"{o:.6f}", f"{p:.6f}"] for m, a, o, p in zip(MODELS, answer, orbit, proof)],
    )

    print(f"Generated four PDF figures and trace data in {args.output.resolve()}")


if __name__ == "__main__":
    main()

