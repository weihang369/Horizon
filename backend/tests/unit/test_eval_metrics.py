"""The evaluation metrics against hand-worked answers (task 7.4; ai-foundation design D34). Each expected value below is
worked out by hand in its comment, not taken from the code under test."""

from __future__ import annotations

import pytest

from horizon.evals.metrics import (
    bootstrap_mean,
    mcnemar_exact,
    mrr,
    ndcg_at_k,
    percentile,
    percentile_ci,
    recall_at_k,
    wilson,
)


def test_wilson_8_of_10() -> None:
    # p = 0.8, z² = 3.8416: centre = (0.8 + 0.19208) / 1.38416 = 0.71673;
    # half = 1.96 · √(0.016 + 0.009604) / 1.38416 = 0.22658 → (0.49015, 0.94331)
    lo, hi = wilson(8, 10)
    assert lo == pytest.approx(0.49015, abs=1e-4) and hi == pytest.approx(0.94331, abs=1e-4)


def test_wilson_edges_stay_inside_0_1() -> None:
    lo, hi = wilson(0, 5)
    assert lo == 0.0 and 0 < hi < 0.5
    assert wilson(0, 0) == (0.0, 1.0)


def test_mcnemar_exact() -> None:
    # n = 10 discordant pairs, min = 1: tail = (C(10,0) + C(10,1)) / 1024 = 11/1024; two-sided = 22/1024
    assert mcnemar_exact(1, 9) == pytest.approx(22 / 1024)
    assert mcnemar_exact(5, 5) == 1.0 and mcnemar_exact(0, 0) == 1.0


def test_percentile_nearest_rank() -> None:
    # 1..10: p50 → rank ⌈5⌉ = 5 → 5; p90 → rank 9 → 9
    assert percentile(range(1, 11), 0.5) == 5 and percentile(range(1, 11), 0.9) == 9   # type: ignore[arg-type]


def test_median_order_statistic_interval() -> None:
    # B ~ Bin(10, ½): P(B ≤ 1) = 11/1024 ≤ 0.025 < P(B ≤ 2) = 56/1024 → l = 2; symmetric → u = 9.
    # Coverage 1 − 22/1024 = 0.9785 ≥ 0.95.
    assert percentile_ci(list(range(1, 11)), 0.5) == (2, 9)
    assert percentile_ci([1.0, 2.0, 3.0], 0.9) is None   # too few values for a 95% p90 interval


def test_bootstrap_over_groups() -> None:
    same = [[1.0, 1.0], [1.0], [1.0, 1.0, 1.0]]
    assert bootstrap_mean(same) == (1.0, 1.0)
    a = bootstrap_mean([[0.0], [1.0], [1.0, 1.0]], seed=7)
    assert a == bootstrap_mean([[0.0], [1.0], [1.0, 1.0]], seed=7)   # seeded: repeatable
    assert 0.0 <= a[0] <= a[1] <= 1.0


def test_ranking_metrics() -> None:
    # relevant {b, d} in [a, b, c, d]: top-2 holds b → 1/2
    assert recall_at_k(["a", "b", "c", "d"], {"b", "d"}, 2) == 0.5
    # first hits at rank 2 and rank 1 → (1/2 + 1) / 2
    assert mrr([(["x", "a"], {"a"}), (["b"], {"b"})]) == 0.75
    # DCG = 0 + 1/log2(3) + 1/log2(4) = 1.13093; IDCG = 1 + 1/log2(3) = 1.63093 → 0.69342
    assert ndcg_at_k(["a", "b", "c"], {"a": 0.0, "b": 1.0, "c": 1.0}, 3) == pytest.approx(0.69342, abs=1e-4)
