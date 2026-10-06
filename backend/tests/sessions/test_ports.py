"""AI ports, profile and the scripted source (ai-ports; provider-gateway "Scripted chat source"; tasks 3.1–3.5)."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import pytest
from pydantic import ValidationError

from horizon.ai.contexts import CharacterView, LineHint, ParticipantView, SessionContext, TurnContext, WorldView
from horizon.ai.profile import ProfileSpec
from horizon.ai.scripted import bank
from horizon.ai.scripted.ports import (
    ScriptedDebateHost,
    ScriptedGuardrail,
    ScriptedReactions,
    ScriptedWatchDirector,
    chunk_tokens,
    emotion_candidates,
    tokenize,
)
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.gateway.pipeline import SimulatedReply
from horizon.services.purge import PurgeWorker
from tests.conftest import Api
from tests.gwkit import block_network
from tests.jobs.kit import cancel_overlay_jobs
from tests.sessions.kit import API, chars, command, create, ledger, messages


def turn_ctx() -> TurnContext:
    s = SessionContext(session_id="ses_x1", world=WorldView(id="wld_seedMeridian", name="Meridian Council"), mode="one_on_one",
                       title="Chat", participants=[ParticipantView(character_id="chr_seedAmara", name="Amara Okafor",
                                                                   role="speaker", energy={"current": 500, "max": 1000})],
                       recent=[], history_tokens=12)
    return TurnContext(session=s, speaker=CharacterView(id="chr_seedAmara", name="Amara Okafor", profile={"name": "Amara"}),
                       message_id="msg_x1", prompt="hi", line=LineHint(kind="chat"), turn_index=3)


def test_contexts_round_trip_through_json_and_are_frozen() -> None:
    ctx = turn_ctx()
    again = TurnContext.model_validate_json(ctx.model_dump_json())
    assert again == ctx
    with pytest.raises(ValidationError):
        ctx.prompt = "changed"  # type: ignore[misc]
    c = ctx.call_ctx("reply")
    assert (c.purpose, c.category, c.drains, c.message_id, c.character_id, c.session_id, c.world_id) == (
        "reply", "chat", True, "msg_x1", "chr_seedAmara", "ses_x1", "wld_seedMeridian")
    route = ctx.session.call_ctx("route")
    assert (route.category, route.drains, route.message_id) == ("decision", False, None)


@pytest.mark.parametrize(("env", "key_set", "turn", "router", "host"), [
    ({}, False, "scripted", "scripted", "scripted"),
    ({}, True, "naive", "naive", "scripted"),
    ({"HORIZON_AI_PROFILE": "scripted"}, True, "scripted", "scripted", "scripted"),
    ({"HORIZON_AI_PROFILE": "naive", "HORIZON_AI_TURN": "scripted"}, True, "scripted", "naive", "scripted"),
    ({"HORIZON_AI_PROFILE": "naive", "HORIZON_AI_HOST": "naive"}, False, "naive", "naive", "scripted"),
])
def test_profile_selection(env: dict[str, str], key_set: bool, turn: str, router: str, host: str) -> None:
    spec = ProfileSpec.from_env(env)
    assert (spec.choose("turn", key_set=key_set), spec.choose("router", key_set=key_set),
            spec.choose("host", key_set=key_set)) == (turn, router, host)


async def test_ai_profile_route_only_in_test_mode(api_normal: Api) -> None:
    r = await api_normal.client.post(f"{API}/_test/ai-profile", json={"profile": "scripted"})
    assert r.status_code == 404


async def test_ai_profile_route_sets_per_port_overrides(api: Api) -> None:
    r = await api.client.post(f"{API}/_test/ai-profile", json={"profile": "naive", "overrides": {"turn": "scripted"}})
    assert r.status_code == 204
    assert api.rt.ai.impl("turn", key_set=True) == "scripted"
    assert api.rt.ai.impl("router", key_set=True) == "naive"


# ── the scripted source ──
def plan(cost: float = 0.0002) -> SimulatedReply:
    return SimulatedReply(chunks=["Hello", " there", " friend"], first_token_ms=1500, step_ms=75, tail_ms=50, total_ms=1700,
                          model="deepseek/deepseek-v4.1-flash", tokens_in=1900, tokens_cached=1300, tokens_out=6,
                          cost_usd=cost)


async def test_scripted_stream_is_billed_drains_and_never_touches_the_network(api: Api, monkeypatch: Any) -> None:
    attempts = block_network(monkeypatch)
    await api.set_key("sk-or-v1-" + "a" * 64)  # a real-looking key: still no request may leave
    before = (await api.json(f"{API}/characters/chr_seedAmara"))["energy"]["current"]
    ctx = call_ctx("reply", world_id="wld_seedMeridian", character_id="chr_seedAmara", message_id="msg_simTest1")
    got: list[str | None] = []

    async def consume() -> None:
        async for ch in api.rt.gateway.simulated_stream(ctx, plan(0.0003), api.rt.clock.sleep):
            got.append(ch.content)

    task = api.rt.spawn("sim", consume())
    await api.drive(2000)
    await task
    assert got == [None, "Hello", " there", " friend"]
    rows = [r for r in await ledger(api) if r["message_id"] == "msg_simTest1"]
    assert len(rows) == 1
    row = rows[0]
    assert (row["category"], row["purpose"], row["provider"], row["cost_source"]) == ("chat", "reply", "scripted", "provider")
    assert row["cost_usd"] == pytest.approx(0.0003)
    after = (await api.json(f"{API}/characters/chr_seedAmara"))["energy"]["current"]
    assert after == before - 3
    assert attempts == []
    assert api.rt.fake is not None and api.rt.fake.requests == []


async def test_scripted_stream_refused_at_the_cap_before_any_chunk(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)  # M4: the test-mode overlay job would also hit the tiny cap
    r = await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 0.0001}})
    assert r.status_code == 200
    seen: list[Any] = []
    unsub = api.rt.bus.subscribe("global")
    ctx = call_ctx("reply", world_id="wld_seedMeridian", character_id="chr_seedAmara", message_id="msg_simTest2")
    with pytest.raises(ProviderError) as e:
        async for ch in api.rt.gateway.simulated_stream(ctx, plan(0.0003), api.rt.clock.sleep):
            seen.append(ch)
    assert e.value.code == "daily_budget_exceeded" and seen == []
    ev = await asyncio.wait_for(unsub.get(), 1)
    assert ev is not None and ev["type"] == "budget.reached"
    assert [r for r in await ledger(api) if r["message_id"] == "msg_simTest2"] == []


# ── determinism ──
async def _exchange(api: Api) -> list[tuple[str, str | None]]:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "What should I eat before a night shift?"})
    await api.drive(12000)
    await command(api, sid, "send", {"text": "And after it?"})
    await api.drive(12000)
    return [(m["content"], m.get("emotion")) for m in await messages(api, sid)]


async def test_same_input_same_reply(make_api: Any, tmp_path: Any) -> None:
    a: Api = await make_api(data_dir=tmp_path / "a")
    b: Api = await make_api(data_dir=tmp_path / "b")
    first = await _exchange(a)
    second = await _exchange(b)
    assert first == second
    assert len(chars([{"author": {"type": "character"}} for c, _ in first if c])) >= 3


def test_bank_and_ports_are_deterministic() -> None:
    profile = {"name": "Amara Okafor", "role": "Emergency physician", "greeting": "Hi.", "expertise": ["medicine"],
               "tagline": "Let's look.", "speakingStyle": {"catchphrases": ["Let's look."]}}
    picks = [bank.pick_line("chat", profile, rng=random.Random("s:1"), prompt="sleep problems") for _ in range(2)]
    assert picks[0] == picks[1] and len(picks[0].text) > 100  # long enough for a 24-token cut
    assert bank.pick_line("greeting", profile, rng=random.Random(1)).text == "Hi."
    assert "proposition" in bank.debate_line("opening", "This house would tax sugar", "prop", 0).text
    assert emotion_candidates("happy", random.Random("x")) == emotion_candidates("happy", random.Random("x"))
    assert "".join(chunk_tokens(tokenize("Hello there, friend."), 3)) == "Hello there, friend."
    host = ScriptedDebateHost.__new__(ScriptedDebateHost)
    assert host.round_note("opening", 1, 2) == "ROUND 1 · OPENING · EXTENDED"
    assert ScriptedWatchDirector().order(["a", "b", "c"], "b") == ["b", "c", "a"]
    assert asyncio.run(ScriptedGuardrail().check(turn_ctx(), "text")).verdict == "pass"


async def test_reactions_follow_the_timing_table(api: Api) -> None:
    r = ScriptedReactions(api.rt.ai.deps)
    out = r.predict(turn_ctx().session, "msg_x1", "chr_a", ["chr_b", "chr_c", "chr_d", "chr_e"], seed="s")
    assert out == r.predict(turn_ctx().session, "msg_x1", "chr_a", ["chr_b", "chr_c", "chr_d", "chr_e"], seed="s")
    assert all(300 <= x.delay_ms <= 800 and 0.42 <= (x.p or 0) <= 0.9 for x in out)


# ── purge ──
async def test_purge_retried_after_a_crash(make_api: Any, tmp_path: Any) -> None:
    from horizon.db import tables as t

    data = tmp_path / "purge"
    api: Api = await make_api(data_dir=data)
    await api.rt.purge.stop()  # the backend "crashes" before the hook runs
    async with api.rt.db.write() as tx:
        await tx.conn.execute(t.ai_purge_queue.insert().values(scope="session", ids=["ses_gone1"], created_at=api.rt.now_iso(),
                                                               attempts=0, done_at=None))
    calls: list[tuple[str, list[str]]] = []

    class Hooks:
        async def on_delete(self, scope: str, ids: Any) -> None:
            calls.append((scope, list(ids)))

    worker = PurgeWorker(api.rt.db, Hooks(), api.rt.now_iso)
    worker.start()  # the restart drains pending entries
    await asyncio.wait_for(worker.idle.wait(), 5)
    await worker.stop()
    assert calls == [("session", ["ses_gone1"])]
    async with api.rt.db.read() as conn:
        rows = (await conn.execute(t.ai_purge_queue.select().where(t.ai_purge_queue.c.ids == ["ses_gone1"]))).mappings().all()
    assert len(rows) == 1 and rows[0]["done_at"] is not None


async def test_purge_failure_backs_off_and_retries(api: Api) -> None:
    from horizon.db import tables as t

    await api.rt.purge.stop()
    async with api.rt.db.write() as tx:
        await tx.conn.execute(t.ai_purge_queue.insert().values(scope="session", ids=["ses_gone2"], created_at=api.rt.now_iso(),
                                                               attempts=0, done_at=None))
    calls: list[int] = []
    slept: list[float] = []

    class Flaky:
        async def on_delete(self, scope: str, ids: Any) -> None:
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("index busy")

    async def sleeper(s: float) -> None:
        slept.append(s)

    worker = PurgeWorker(api.rt.db, Flaky(), api.rt.now_iso, sleeper=sleeper)
    worker.start()
    for _ in range(100):
        if worker.idle.is_set() and len(calls) >= 3:
            break
        await asyncio.sleep(0.02)
    await worker.stop()
    assert len(calls) >= 3 and slept[:2] == [1.0, 5.0]
