"""Statistical tests for paired designs (spec section 25).

Everything here is paired, because the design is paired: an item and its transformed
variant are the same problem in different clothes, so an unpaired test throws away the
matching and understates the effect.

Implemented directly on numpy and the standard library so the evaluation layer has no
scipy dependency; the exact binomial and the bootstrap are both short and are the two
tests the design actually calls for.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb, sqrt

import numpy as np


@dataclass
class PairedTest:
    n_pairs: int
    b: int  # correct under condition A, wrong under B
    c: int  # wrong under A, correct under B
    p_value: float
    odds_ratio: float | None
    note: str = ""


def mcnemar_exact(a_correct: list[bool], b_correct: list[bool]) -> PairedTest:
    """Exact McNemar test on paired binary outcomes.

    Uses the exact binomial rather than the chi-square approximation: discordant-pair
    counts in a per-condition slice are often small, and the approximation is unreliable
    there in exactly the direction that would overstate significance.
    """
    if len(a_correct) != len(b_correct):
        raise ValueError("paired test needs equal-length outcome lists")
    b = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)
    c = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)
    n = b + c
    if n == 0:
        return PairedTest(len(a_correct), b, c, 1.0, None, "no discordant pairs")

    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2**n)
    p = min(1.0, 2 * tail)
    odds = (b / c) if c else None
    return PairedTest(len(a_correct), b, c, p, odds)


def paired_bootstrap_ci(
    a_correct: list[bool],
    b_correct: list[bool],
    n_resamples: int = 10000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Bootstrap CI for the paired accuracy difference (A - B).

    Resamples items, not observations: an item's two outcomes always move together, which
    is what preserves the pairing.
    """
    a = np.asarray(a_correct, dtype=float)
    b = np.asarray(b_correct, dtype=float)
    if a.size == 0:
        return 0.0, 0.0, 0.0

    point = float(a.mean() - b.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, a.size, size=(n_resamples, a.size))
    diffs = a[idx].mean(axis=1) - b[idx].mean(axis=1)

    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(diffs, [alpha, 1.0 - alpha])
    return point, float(lo), float(hi)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval: behaves sensibly at proportions near 0 and 1, where the
    normal approximation produces bounds outside [0, 1]."""
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def orbit_permutation_test(
    orbit_outcomes: list[dict[str, bool]],
    reference: str,
    condition: str,
    n_permutations: int = 10000,
    seed: int = 42,
) -> tuple[float, float]:
    """Permutation test for a paired orbit-level contrast (spec section 25.1).

    Each entry maps condition -> correct for one orbit. Under the null that the condition
    label carries no information, the two outcomes within an orbit are exchangeable, so the
    null distribution is built by flipping each orbit's pair independently.

    Preferred over a normal approximation for orbit metrics because those are counts of
    all-or-nothing events over a few hundred orbits, where asymptotics are unreliable.

    :returns: (observed difference, two-sided p-value)
    """
    pairs = [
        (o[reference], o[condition])
        for o in orbit_outcomes
        if reference in o and condition in o
    ]
    if not pairs:
        return 0.0, 1.0

    a = np.array([p[0] for p in pairs], dtype=float)
    b = np.array([p[1] for p in pairs], dtype=float)
    observed = float(a.mean() - b.mean())

    rng = np.random.default_rng(seed)
    # A swap mask per orbit per permutation: exchange the pair or leave it, which is the
    # exact null the paired design implies.
    swaps = rng.random((n_permutations, a.size)) < 0.5
    permuted_a = np.where(swaps, b, a)
    permuted_b = np.where(swaps, a, b)
    null = permuted_a.mean(axis=1) - permuted_b.mean(axis=1)

    p = float((np.abs(null) >= abs(observed) - 1e-12).mean())
    return observed, max(p, 1.0 / n_permutations)


def holm_correction(p_values: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjustment for a family of secondary comparisons (spec 25.3)."""
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (key, p) in enumerate(ordered):
        value = min(1.0, (m - i) * p)
        running = max(running, value)  # enforce monotonicity
        adjusted[key] = running
    return adjusted
