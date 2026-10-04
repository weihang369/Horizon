"""Cost estimates (task 3.1, budget-caps "Cost estimates per category")."""

from __future__ import annotations

from pathlib import Path

import pytest

from horizon.domain import pricing as pr

SEED = Path(__file__).resolve().parents[3] / "seed"
T = pr.load_price_table(SEED)


def test_table_loads_from_seed() -> None:
    assert T.decision.model == "typesafe/jev-1.13" and T.decision.input_per_m == 0.042 and T.decision.output_per_m == 0
    assert T.embedding.input_per_m == 0.01
    assert T.generation["portrait"] == 0.018
    assert T.peak.multiplier == 2 and T.peak.tz == "Asia/Kuala_Lumpur"
    assert T.gateway["embedBatch"] == 32


def test_decision_estimate() -> None:
    assert pr.estimate_decision(T, 10_000) == pytest.approx(0.00042)


def test_peak_doubles_chat() -> None:
    kw = {"prefix_tokens": 1500, "warm": False, "other_in": 300, "expected_out_tokens": 220}
    off = pr.estimate_chat(T, period="off_peak", **kw)  # type: ignore[arg-type]
    peak = pr.estimate_chat(T, period="peak", **kw)  # type: ignore[arg-type]
    assert peak == pytest.approx(2 * off)
    assert off == pytest.approx((1500 * 0.15 + 300 * 0.15 + 220 * 0.6) / 1e6)


def test_warm_prefix_uses_cached_rate() -> None:
    cold = pr.estimate_chat(T, prefix_tokens=1000, warm=False, other_in=0, expected_out_tokens=0, period="off_peak")
    warm = pr.estimate_chat(T, prefix_tokens=1000, warm=True, other_in=0, expected_out_tokens=0, period="off_peak")
    assert cold == pytest.approx(1000 * 0.15 / 1e6)
    assert warm == pytest.approx(1000 * 0.003 / 1e6)


@pytest.mark.parametrize(("max_tokens", "recent", "expected"), [
    (512, [], 220),                                       # no history: 220 stands in
    (100, [], 100),                                       # max_tokens caps it
    (512, [50, 60, 70, 80], 70),                          # nearest-rank p75
    (512, [10] * 10 + [400, 400], 10),                    # only the last 10 count (eight 10s + 400, 400)
    (512, [300, 310, 320, 330, 340, 350, 360, 370, 380, 390], 370),
    (200, [300, 310, 320, 330], 200),
])
def test_expected_out(max_tokens: int, recent: list[int], expected: int) -> None:
    assert pr.expected_out(max_tokens, recent) == expected


def test_image_and_embedding() -> None:
    assert pr.estimate_image(T) == 0.018
    assert pr.estimate_embedding(T, 1_000_000) == pytest.approx(0.01)


def test_token_count_is_conservative() -> None:
    assert pr.count_tokens("") == 0
    assert pr.count_tokens("ping") == 2
    english = "The quick brown fox jumps over the lazy dog. " * 20
    assert pr.count_tokens(english) >= len(english) / 4  # never under the ~4 chars/token rule of thumb


# ── task 3.2: the peak window is the provider's (MYT), whatever HORIZON_TZ says (OQ-G) ──
def test_clock_defaults_match_pricing_json() -> None:
    from horizon.domain.clock import PEAK_TZ, PEAK_WINDOWS

    assert T.peak.tz == PEAK_TZ
    assert T.peak.windows == tuple(PEAK_WINDOWS)


def test_peak_is_myt_even_when_horizon_tz_is_utc() -> None:
    from datetime import UTC, datetime

    from horizon.domain.clock import calendar_for

    cal = calendar_for("UTC", peak_tz=T.peak.tz, windows=T.peak.windows)
    tue_1030_myt = datetime(2026, 10, 6, 2, 30, tzinfo=UTC)  # Tuesday 10:30 +08:00
    assert cal.period(tue_1030_myt) == "peak"
    assert cal.next_change(tue_1030_myt) == datetime(2026, 10, 6, 4, 0, tzinfo=UTC)  # 12:00 MYT
    assert cal.today(datetime(2026, 10, 6, 20, 0, tzinfo=UTC)).isoformat() == "2026-10-06"  # day boundary stays UTC
