"""M9's `moodline` and `latency` suites offline (turn-plan-emotion tasks 8.8, 8.9; design D30, D31; evaluation-harness
"Same history in both arms", "Replay from the store", "Verdict is advice", "Never from the store", "Stopped at the
first word"). The fake provider answers; Decider fixtures give Jev call 1 a confident non-neutral face."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from horizon.ai.agent.turn import AgentTurnEngine
from horizon.evals import latency as lat
from horizon.evals import moodline as mood
from horizon.evals.runner import Options, RunEnv, store_for
from horizon.evals.store import ResponseStore
from tests.conftest import Api

API = "/api/v1"
CAST = ("chr_seedAmara", "chr_seedMei", "chr_seedVictor", "chr_seedHana", "chr_seedRin", "chr_seedTakeshi")


async def faces(api: Api, face: str = "sad") -> None:
    body = {"set": [{"purpose": "turn_plan", "question": f"emotion_reply:{cid}",
                     "answer": {"choice": face, "confidence": 0.9, "probabilities": {face: 0.9}}} for cid in CAST]}
    assert (await api.post(f"{API}/_test/decider-fixtures", body)).status_code == 204


def env(api: Api, tmp: Path, suite: str, **kw: Any) -> RunEnv:
    return RunEnv(rt=api.rt, opts=Options(suite=suite, **kw), store=None, run_dir=tmp, max_usd=5.0)


# ── 8.8: moodline ──
async def test_same_history_in_both_arms(api: Api, tmp_path: Path) -> None:
    await api.set_key()
    await faces(api)
    e = env(api, tmp_path, "moodline", limit=1)
    suite = mood.Moodline()
    c = mood.candidates(per_file=2)[0]
    sctx, speaker, latest, _ = await suite.context(e, c)
    from horizon.ai.agent.planner import JevTurnPlanner
    from horizon.ai.contexts import PlanRequest, TurnContext

    plan = await JevTurnPlanner(api.rt.ai.deps).plan(PlanRequest(
        session=sctx, speaker_id=speaker.id, cast=[speaker], latest=latest, turn_index=c["turn"],
        started_at=api.rt.clock.now()))
    assert plan is not None and plan.emotion is not None and plan.emotion.face == "sad"
    on, off = suite.arms(TurnContext(session=sctx, speaker=speaker, message_id=None, prompt=latest, max_tokens=200,
                                     plan=plan))
    engine = AgentTurnEngine(mood.with_mood_line(api.rt.ai.deps))   # D40: the suite forces the line on for ON
    a, b = engine.request(on)[0].messages, engine.request(off)[0].messages
    mood_line = "Your mood right now: a bit low. Let it show in how you word this reply; don't name the feeling."
    assert a[:-1] == b[:len(a) - 1] and a[-1]["role"] == "system" and a[-1]["content"].startswith(mood_line)
    rest = a[-1]["content"].removeprefix(mood_line).lstrip("\n")
    assert (b[-1]["content"] == rest) if rest else (len(b) == len(a) - 1)


async def test_replay_from_the_store_spends_nothing(api: Api, tmp_path: Path) -> None:
    await api.set_key()
    await faces(api)
    api.rt.gateway.store = ResponseStore.eval_view(tmp_path / "cache", None)
    fake = api.rt.fake
    assert fake is not None
    suite = mood.Moodline()
    plan = suite.plan(Options(suite="moodline", limit=2), api.rt.prices, paid=False)
    first = await suite.run(env(api, tmp_path, "moodline", limit=2), plan)
    assert len(first.rows) == 2 and all(r["reply_on"] and r["reply_off"] for r in first.rows)
    sent = dict(fake.counts)
    again = await suite.run(env(api, tmp_path, "moodline", limit=2), plan)
    assert dict(fake.counts) == sent                                   # every reply and judge answer from the store
    assert [r["reply_on"] for r in again.rows] == [r["reply_on"] for r in first.rows]
    assert any(line.startswith("- verdict (advice; nothing was changed)") for line in again.summary)


def test_verdict_is_advice_and_follows_e8() -> None:
    assert mood.verdict((0.2, 0.05, 0.35), (0.55, 0.45, 0.65)).startswith("keep")
    assert mood.verdict((0.2, 0.05, 0.35), (0.3, 0.2, 0.45)).startswith("reword")
    drop = mood.verdict((0.0, -0.1, 0.1), (0.6, 0.5, 0.7))
    assert drop.startswith("propose dropping") and "nothing was changed" in drop


def test_block_bootstrap_on_a_known_split() -> None:
    rows = [{"transcript": "long_one_on_one_en", "d": 1.0}] * 10 + [{"transcript": "long_group_meridian", "d": 0.0}] * 10
    assert mood.blocks(rows, "d") == [[1.0] * 10, [0.0] * 10]
    mean, lo, hi = mood.interval(rows, "d")  # type: ignore[misc]
    assert mean == 0.5 and lo == 0.0 and hi == 1.0                     # two blocks: either can be drawn twice
    same = [{"transcript": "long_one_on_one_en", "d": 1.0}] * 30
    assert mood.interval(same, "d") == (1.0, 1.0, 1.0)


# ── 8.9: latency ──
def test_latency_never_uses_the_store(tmp_path: Path) -> None:
    assert store_for(Options(suite="latency"), tmp_path, None) is None
    assert store_for(Options(suite="moodline"), tmp_path, None) is not None


async def test_stopped_at_the_first_word_and_the_report_renders(api: Api, tmp_path: Path) -> None:
    from tests.sessions.test_turns import FixedEngine

    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    # The fake sends a whole reply at once; this engine streams for seconds, so Stop lands mid-reply as on the provider
    api.rt.ai.override("turn", FixedEngine(api, text="Long answer, word by word, " * 12))
    suite = lat.Latency()
    plan = suite.plan(Options(suite="latency", limit=2), api.rt.prices, paid=False)
    assert [t["character"] for t in plan.items] == ["chr_seedAmara", "chr_seedMei"]
    res = await suite.run(env(api, tmp_path, "latency", limit=2, profile="agent"), plan)
    assert len(res.rows) == 2 and all(r["status"] == "interrupted" for r in res.rows)
    assert all(r["to_token_ms"] is not None and r["to_face_ms"] is not None for r in res.rows)
    text = "\n".join(res.summary)
    assert "send → first word (token event) (n 2): p50" in text and "p90" in text and "stopped at the first word: 2/2" in text


async def test_a_turn_past_the_watchdog_dumps_every_stack_and_gives_up(tmp_path: Path, monkeypatch: Any) -> None:
    """A paid run must never hang (9.6's first run did): past the watchdog the stacks go to the run folder."""
    monkeypatch.setattr(lat, "TURN_WATCHDOG_S", 0.05)
    e: Any = SimpleNamespace(rt=SimpleNamespace(clock=object()), run_dir=tmp_path / "run")   # a real clock: not frozen
    with pytest.raises(TimeoutError):
        await lat.Latency.guarded(e, asyncio.Event().wait())
    assert "===" in (tmp_path / "run" / lat.STACKS).read_text(encoding="utf-8")


def test_an_unknown_suite_lists_the_known_ones(capsys: Any) -> None:
    """evaluation-harness "Unknown suite": it exits non-zero and lists every suite, M9's included."""
    import argparse

    import pytest

    from horizon.evals.cli import register

    parser = argparse.ArgumentParser(prog="horizon")
    register(parser.add_subparsers(dest="cmd"))
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["eval", "no-such-suite"])   # M15 built `conversations`
    assert e.value.code != 0
    err = capsys.readouterr().err
    for name in ("canary", "decisions", "smoke", "drafter", "summary", "long", "transcript", "moodline", "latency"):
        assert name in err
