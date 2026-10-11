"""`horizon eval` in test mode (evaluation-harness spec; ai-foundation design D33–D35; tasks 7.3, 7.5–7.7). Everything
runs on the in-process fake; the socket guard stays on."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from horizon.config import load_config
from horizon.domain.clock import calendar_for
from horizon.evals import canary as canary_mod
from horizon.evals.runner import EVALS_DIR, Options, Runner, overlaps_peak, prune_runs, store_for

SATURDAY = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)


def base(tmp: Path) -> Any:
    return load_config({"HORIZON_DATA_DIR": str(tmp), "HORIZON_TEST": "1"})


def runner(tmp: Path, answer: str = "y") -> tuple[Runner, list[str]]:
    out: list[str] = []
    return Runner(base(tmp), stdin=lambda _p: answer, out=out.append, now=lambda: SATURDAY), out


async def test_declined_prompt_sends_nothing_and_keeps_no_folder(tmp_path: Path) -> None:
    r, out = runner(tmp_path, "n")
    assert await r.run(Options("smoke", limit=1)) == 1
    assert not (tmp_path / "evals").exists() and any("cancelled" in line for line in out)


async def test_paid_suites_refuse_in_test_mode(tmp_path: Path) -> None:
    r, out = runner(tmp_path)
    assert await r.run(Options("canary", yes=True)) == 2
    assert await r.run(Options("decisions", yes=True)) == 2
    assert not (tmp_path / "evals").exists() and all("test mode" in line for line in out)


async def test_smoke_runs_isolated_and_reports_the_agent_ports(tmp_path: Path) -> None:
    user_db = tmp_path / "horizon.db"
    user_db.write_bytes(b"not touched")
    r, _out = runner(tmp_path)
    rc = await r.run(Options("smoke", profile="agent", limit=2, yes=True))
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    report = (run / "agent" / "report.md").read_text(encoding="utf-8")
    assert rc == 0, report
    assert user_db.read_bytes() == b"not touched"          # the user's database is never opened
    assert "turn=naive" in report and "router=naive" in report   # agent resolves to naive per port in M7
    assert "smoke only" in report and "never a measurement" in report
    rows = [json.loads(x) for x in (run / "agent" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["mode"] for r in rows if "mode" in r} == {"one_on_one", "group", "watch", "debate"}
    assert all(r["replies"] > 0 for r in rows if "mode" in r)
    assert not (tmp_path / "evals" / "spend.jsonl").exists()   # the fake costs nothing real


async def test_a_forced_cap_ends_the_run_incomplete(tmp_path: Path) -> None:
    r, _out = runner(tmp_path)
    assert await r.run(Options("smoke", limit=2, yes=True, max_usd=1e-9)) == 1
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    assert "incomplete" in (run / "naive" / "report.md").read_text(encoding="utf-8")


def test_the_21st_run_prunes_the_oldest(tmp_path: Path) -> None:
    for i in range(21):
        (tmp_path / f"20261003T0300{i:02d}-smoke-x").mkdir()
    assert prune_runs(tmp_path) == ["20261003T030000-smoke-x"]
    assert len(list(tmp_path.iterdir())) == 20


def test_peak_check() -> None:
    cal = calendar_for("Asia/Kuala_Lumpur")
    monday_0850 = datetime(2026, 10, 5, 0, 50, tzinfo=UTC)          # 08:50 MYT, peak at 09:00
    assert overlaps_peak(cal, monday_0850, 15 * 60) and not overlaps_peak(cal, monday_0850, 5 * 60)
    assert not overlaps_peak(cal, SATURDAY, 3600)


@pytest.mark.parametrize(("suite", "flags", "stored"), [
    ("canary", {}, False), ("capture", {}, False), ("import", {}, False), ("decisions", {"latency": True}, False),
    ("decisions", {"repeat": True}, False), ("decisions", {}, True), ("smoke", {}, True)])
def test_the_store_is_never_attached_to_bypassed_runs(tmp_path: Path, suite: str, flags: dict[str, bool],
                                                      stored: bool) -> None:
    assert (store_for(Options(suite, **flags), tmp_path, None) is not None) is stored


# ── 7.5: the canary on canned answers ──
def test_canary_copy_is_byte_identical_to_group_a() -> None:
    src = EVALS_DIR.parent / "docs/ai/checks/group-a/results/canary.json"
    assert (EVALS_DIR / "canary.json").read_bytes() == src.read_bytes()


def test_canary_rule() -> None:
    b = canary_mod.load_baseline(EVALS_DIR / "canary.json")
    assert all(canary_mod.compare(i["answers"], i["answers"]) == [] for i in b.items)
    choice = next(i for i in b.items if any("choice" in a for a in i["answers"].values()))
    qid, a = next((k, v) for k, v in choice["answers"].items() if "choice" in v)
    other = next(k for k in a["probabilities"] if k != a["choice"])
    flipped = {**choice["answers"], qid: {**a, "choice": other}}
    assert any("choice" in d for d in canary_mod.compare(choice["answers"], flipped))
    noul = next(i for i in b.items if any("noul" in a for a in i["answers"].values()))
    nq, na = next((k, v) for k, v in noul["answers"].items() if "noul" in v)
    moved = {**noul["answers"], nq: {**na, "noul": min(1.0, float(na["noul"]) + 0.11) if na["noul"] < 0.5
                                     else float(na["noul"]) - 0.11}}
    assert canary_mod.compare(noul["answers"], moved) and not canary_mod.compare(
        noul["answers"], {**noul["answers"], nq: {**na, "noul": float(na["noul"]) + (0.09 if na["noul"] < 0.5 else -0.09)}})


def test_a_hand_edited_baseline_is_refused(tmp_path: Path) -> None:
    doc = json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))
    item = doc["items"][0]
    qid = next(iter(item["answers"]))
    a = item["answers"][qid]
    if "choice" in a:
        a["choice"] = next(k for k in a["probabilities"] if k != a["choice"])
    else:
        a["noul" if "noul" in a else "score"] = 0.0
    p = tmp_path / "canary.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(canary_mod.BaselineError):
        canary_mod.load_baseline(p)


def test_start_skips_items_and_the_estimate_counts_jev_overhead() -> None:
    from horizon.domain.pricing import JEV_REQUEST_OVERHEAD_TOKENS, load_price_table
    from horizon.evals.suites import Canary

    prices = load_price_table(EVALS_DIR.parent / "seed")
    full = Canary().plan(Options("canary"), prices, paid=True)
    tail = Canary().plan(Options("canary", start=18), prices, paid=True)
    assert [i["id"] for i in tail.items] == [i["id"] for i in full.items[18:]]
    # docs/ai/checks/m7.md: 20 canary requests billed $0.000446; the budget must cover that
    assert JEV_REQUEST_OVERHEAD_TOKENS >= 275 and 0.000446 < full.estimate_usd < 0.001
