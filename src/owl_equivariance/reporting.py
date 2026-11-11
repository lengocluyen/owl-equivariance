"""Result tables (spec section 38), as CSV, Markdown or LaTeX."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence


def write_csv(path: str | Path, rows: Sequence[dict], columns: list[str] | None = None) -> None:
    if not rows:
        return
    cols = columns or list(rows[0].keys())
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return "-"
    return str(value)


def markdown_table(rows: Sequence[dict], columns: list[str], headers: list[str] | None = None) -> str:
    head = headers or columns
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(c)) for c in columns) + " |")
    return "\n".join(lines)


def latex_table(
    rows: Sequence[dict],
    columns: list[str],
    headers: list[str] | None = None,
    caption: str = "",
    label: str = "",
) -> str:
    head = headers or columns
    spec = "l" + "r" * (len(columns) - 1)
    out = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\begin{{tabular}}{{{spec}}}",
        "\\toprule",
        " & ".join(_escape(h) for h in head) + " \\\\",
        "\\midrule",
    ]
    for row in rows:
        out.append(" & ".join(_escape(_fmt(row.get(c))) for c in columns) + " \\\\")
    out += ["\\bottomrule", "\\end{tabular}"]
    if caption:
        out.append(f"\\caption{{{_escape(caption)}}}")
    if label:
        out.append(f"\\label{{{label}}}")
    out.append("\\end{table}")
    return "\n".join(out)


def _escape(text: str) -> str:
    for char in ("_", "%", "&", "#"):
        text = text.replace(char, "\\" + char)
    return text


# Column sets for the tables the paper needs.
ANSWER_COLUMNS = [
    "condition",
    "n",
    "accuracy",
    "accuracy_ci_low",
    "accuracy_ci_high",
    "macro_f1",
    "entailed_precision",
    "entailed_recall",
    "not_entailed_precision",
    "not_entailed_recall",
    "invalid_rate",
    "valid_only_accuracy",
]

COMPARISON_COLUMNS = [
    "condition",
    "n_pairs",
    "invariance_gap",
    "invariance_gap_ci_low",
    "invariance_gap_ci_high",
    "correct_to_wrong_flip_rate",
    "wrong_to_correct_flip_rate",
    "pair_consistency",
    "mcnemar_p",
    "mcnemar_p_holm",
    "discordant_correct_only_in_reference",
    "discordant_correct_only_in_condition",
    "discordant_odds_ratio_ref_over_condition",
]

VALIDITY_COMPARISON_COLUMNS = [
    "condition",
    "n_pairs",
    "validity_gap",
    "validity_gap_ci_low",
    "validity_gap_ci_high",
    "valid_to_invalid",
    "invalid_to_valid",
    "pair_consistency",
    "mcnemar_p",
    "mcnemar_p_holm",
    "discordant_odds_ratio_ref_over_condition",
]

PROOF_COLUMNS = [
    "condition",
    "n_positive",
    "n_validated",
    "answer_accuracy_on_positives",
    "support_validity_rate",
    "caip_joint",
    "caip_given_correct",
    "minimality_rate",
    "hallucinated_axiom_id_count",
]
