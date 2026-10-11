"""The evaluation metrics (docs/ai/02 B3–B5; ai-foundation design D34; task 7.4). Pure functions, no dependencies.

- `wilson(k, n)`: the Wilson score interval for a proportion (small samples, never outside [0, 1]).
- `mcnemar_exact(b, c)`: the two-sided exact McNemar p-value from the discordant counts (binomial, p = ½).
- `bootstrap_mean(groups)`: a percentile bootstrap over GROUPS (conversations), never over pooled items, so turns of
  one conversation stay together.
- `percentile(values, q)` and `percentile_ci(values, q)`: the nearest-rank percentile and its distribution-free
  order-statistic interval (None when n is too small for the coverage asked).
- `recall_at_k`, `mrr`, `ndcg_at_k`: ranking metrics for retrieval.
"""

from __future__ import annotations

import math
import random
from collections.abc import Hashable, Mapping, Sequence
from math import comb


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
    """b: pairs only A got right; c: pairs only B got right."""
    n = b + c
    if n == 0:
        return 1.0
    tail = float(sum(comb(n, i) for i in range(min(b, c) + 1))) / float(1 << n)
    return min(1.0, 2.0 * tail)


def bootstrap_mean(groups: Sequence[Sequence[float]], *, n_boot: int = 2000, alpha: float = 0.05,
                   seed: int = 0) -> tuple[float, float]:
    """A (1 − alpha) percentile interval for the pooled mean, resampling whole groups with replacement."""
    groups = [list(g) for g in groups if g]
    if not groups:
        return 0.0, 0.0
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_boot):
        pick = [groups[rng.randrange(len(groups))] for _ in groups]
        total = sum(len(g) for g in pick)
        means.append(sum(sum(g) for g in pick) / total)
    means.sort()
    lo = means[max(0, math.floor(alpha / 2 * n_boot))]
    hi = means[min(n_boot - 1, math.ceil((1 - alpha / 2) * n_boot) - 1)]
    return lo, hi


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank: the smallest value with at least q of the data at or below it."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def _binom_cdf(k: int, n: int, q: float) -> float:
    return sum(comb(n, i) * q**i * (1 - q) ** (n - i) for i in range(0, k + 1)) if k >= 0 else 0.0


def percentile_ci(values: Sequence[float], q: float, alpha: float = 0.05) -> tuple[float, float] | None:
    """The order-statistic interval [x(l), x(u)] (1-based ranks) covering the q-quantile with ≥ 1 − alpha:
    B ~ Bin(n, q); l is the largest rank with P(B ≤ l − 1) ≤ alpha/2, u the smallest with P(B ≥ u) ≤ alpha/2."""
    s = sorted(values)
    n = len(s)
    lo = 0
    for rank in range(1, n + 1):
        if _binom_cdf(rank - 1, n, q) <= alpha / 2:
            lo = rank
    hi = 0
    for rank in range(n, 0, -1):
        if 1 - _binom_cdf(rank - 1, n, q) <= alpha / 2:
            hi = rank
    if lo < 1 or hi < 1 or hi > n or lo > hi:
        return None
    return s[lo - 1], s[hi - 1]


def recall_at_k(ranked: Sequence[Hashable], relevant: set[Hashable], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(runs: Sequence[tuple[Sequence[Hashable], set[Hashable]]]) -> float:
    """Mean reciprocal rank over (ranked, relevant) pairs; a run with no hit scores 0."""
    if not runs:
        return 0.0
    total = 0.0
    for ranked, relevant in runs:
        total += next((1 / (i + 1) for i, x in enumerate(ranked) if x in relevant), 0.0)
    return total / len(runs)


def ndcg_at_k(ranked: Sequence[Hashable], gains: Mapping[Hashable, float], k: int) -> float:
    dcg = sum(gains.get(x, 0.0) / math.log2(i + 2) for i, x in enumerate(ranked[:k]))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0
