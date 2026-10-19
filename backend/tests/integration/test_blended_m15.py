"""`horizon eval latency --part blended` (images-music design D15; evaluation-harness "The must-pass latency run";
task 6.6). The fake, no network, $0."""

from __future__ import annotations

from pathlib import Path

from horizon.evals import blended as B
from horizon.evals.latency import Latency
from horizon.evals.runner import Options
from tests.integration.test_eval_runner import runner


def test_the_warm_up_turns_are_kept_but_never_counted() -> None:
    rows = B.mark([{"to_token_ms": float(i)} for i in range(105)], B.WARMUP)
    assert [r["warmup"] for r in rows[:6]] == [True] * 5 + [False]
    assert B.measured([{**r, "part": "quick"} for r in rows], "quick", "to_token_ms") == [float(i) for i in range(5, 105)]


def test_the_blend_is_the_mixtures_quantile_by_hand() -> None:
    quick, deep = [1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]
    # F(4) = ½·1 + ½·0 = 0.5 → p50 is 4; F reaches 0.9 only once ½ + ½·k/4 ≥ 0.9, k = 4 → p90 is 40
    assert B.mixture_quantile(quick, deep, 0.5, 0.5) == 4.0
    assert B.mixture_quantile(quick, deep, 0.5, 0.9) == 40.0
    assert B.mixture_quantile(quick, deep, 0.0, 0.9) == 4.0 and B.mixture_quantile(quick, deep, 1.0, 0.5) == 20.0
    b = B.blended(quick, deep, 0.25)
    assert b["p50_ci"][0] <= b["p50"] <= b["p50_ci"][1] and b["p90_ci"][0] <= b["p90"] <= b["p90_ci"][1]


def test_the_rate_is_fixed_before_the_run_and_agent_only() -> None:
    lat = Latency()
    assert lat.refuse(Options("latency", profile="agent", part="blended", arm="rate=0.3")) is None
    assert "between 0 and 1" in (lat.refuse(Options("latency", profile="agent", part="blended", arm="rate=1.5")) or "")
    assert "--profile agent" in (lat.refuse(Options("latency", profile="naive", part="blended")) or "")
    assert B.rate_of(Options("latency", arm="rate=0.31")) == 0.31 and B.rate_of(Options("latency")) is None


async def test_limit_1_per_part_on_the_fake(tmp_path: Path) -> None:
    r, out = runner(tmp_path)
    assert await r.run(Options("latency", profile="agent", part="blended", arm="rate=0.3", limit=1, yes=True)) == 0, out
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    rep = (run / "agent" / "report.md").read_text(encoding="utf-8")
    assert "## Blended latency" in rep and "- window: " in rep and "warm-up turns left out" in rep
    assert "blended at deep rate 0.30" in rep or "blended:" in rep
    assert "### Per purpose (the ledger)" in rep and (run / "agent" / "turns.jsonl").is_file()
