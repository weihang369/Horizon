"""Stop, idle release, restart and stream cut (session-runtime "Stop and pause are prompt", "Idle sessions release",
"One writer per session"; http-api "Stream cut"; tasks 5.3–5.5)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import Token, TurnEvent
from horizon.gateway.pipeline import SimulatedReply
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages, snapshot


async def _streaming(api: Api, sid: str) -> dict[str, Any]:
    for _ in range(40):
        await api.drive(250)
        m = next((x for x in await messages(api, sid) if x["status"] == "streaming"), None)
        if m is not None:
            return m
    raise AssertionError("no reply started streaming")


async def test_stop_mid_stream_keeps_the_streamed_text_and_the_spend(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedVictor"]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Tell me everything about precedent."})
    m = await _streaming(api, sid)
    await api.drive(300)
    await command(api, sid, "stop")
    await api.drive(1000)
    reply = next(x for x in await messages(api, sid) if x["id"] == m["id"])
    assert reply["status"] == "interrupted" and reply["interruptedBy"] == "user"
    streamed = "".join(e["payload"]["delta"] for e in await events(api, sid)
                       if e["type"] == "token" and e["payload"]["messageId"] == m["id"])
    assert reply["content"] == streamed and 0 < len(streamed)
    rows = [r for r in await ledger(api) if r["message_id"] == m["id"] and r["category"] == "chat"]  # M9: the reply's row
    assert len(rows) == 1 and rows[0]["cost_source"] == "estimate"
    assert reply["usage"]["costUsd"] == round(rows[0]["cost_usd"], 6)
    assert not api.rt.sessions.peek(sid).generating  # type: ignore[union-attr]
    await assert_reduces(api, sid)


class SlowEngine:
    """A real-time slow stream (the clock is released): one chunk every 200 ms."""

    name = "slow"
    version = "t1"
    prompt_version = None

    def __init__(self, api: Api) -> None:
        self.api = api

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        spec = SimulatedReply(chunks=["word "] * 200, first_token_ms=50, step_ms=200, tail_ms=0, total_ms=40_000,
                              model="deepseek/deepseek-v4.1-flash", tokens_in=900, tokens_cached=0, tokens_out=200,
                              cost_usd=0.0002)
        async for ch in self.api.rt.gateway.simulated_stream(ctx.call_ctx("reply"), spec, self.api.rt.clock.sleep):
            if ch.content:
                yield Token(ch.content)


async def test_stop_within_500ms_in_real_time(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedVictor"]))["session"]["id"]
    await api.drive(6000)
    assert (await api.post(f"{API}/_test/clock", {"release": True})).status_code == 200
    api.rt.ai.override("turn", SlowEngine(api))
    await command(api, sid, "send", {"text": "Go on."})
    for _ in range(100):
        await asyncio.sleep(0.05)
        if any(x["status"] == "streaming" and x["content"] for x in await messages(api, sid)):
            break
    started = time.monotonic()
    await command(api, sid, "stop")
    for _ in range(100):
        last = chars(await messages(api, sid))[-1]
        if last["status"] == "interrupted":
            break
        await asyncio.sleep(0.01)
    elapsed = time.monotonic() - started
    assert last["status"] == "interrupted" and last["interruptedBy"] == "user"
    assert elapsed < 0.5, elapsed


async def test_command_after_idle_release(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    assert (await api.client.post(f"{API}/sessions/{sid}/leave")).status_code == 204
    assert api.rt.sessions.peek(sid) is not None
    await api.drive(11 * 60_000)
    assert api.rt.sessions.peek(sid) is None  # released: no subscriber, no work, 10 minutes of clock time
    last = len(await events(api, sid))
    await command(api, sid, "send", {"text": "Still there?"})
    await api.drive(12000)
    evs = await events(api, sid)
    assert evs[last]["seq"] == last + 1 and evs[last]["type"] == "session.resumed"
    assert len(chars(await messages(api, sid))) == 2
    await assert_reduces(api, sid)


async def test_a_subscriber_keeps_the_actor(api: Api) -> None:
    from horizon.events.bus import session_channel

    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    sub = api.rt.bus.subscribe(session_channel(sid))
    await api.drive(11 * 60_000)
    assert api.rt.sessions.peek(sid) is not None
    api.rt.bus.unsubscribe(sub)
    await api.drive(11 * 60_000)
    assert api.rt.sessions.peek(sid) is None


async def test_restart_continues_the_sequence(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "restart"
    a: Api = await make_api(data_dir=data)
    await a.set_key()
    sid = (await create(a, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await a.drive(6000)
    high = len(await events(a, sid))
    await a.rt.stop()
    b: Api = await make_api(data_dir=data)
    await command(b, sid, "set-readable-mode", {"on": True})
    evs = await events(b, sid)
    assert evs[-1]["seq"] == high + 1


async def test_stream_cut_scenario(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedVictor"]))["session"]["id"]
    await api.drive(6000)
    assert (await api.post(f"{API}/_test/scenario", {"id": "stream_cut"})).status_code == 204
    await command(api, sid, "send", {"text": "Define your terms, counsel. What exactly do you mean by a fair trial in this case?"})
    await api.drive(12000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "interrupted" and reply["interruptedBy"] == "error"
    assert reply["error"]["code"] == "network"
    evs = await events(api, sid)
    err = next(e for e in evs if e["type"] == "error" and e["payload"].get("messageId") == reply["id"])
    end = next(e for e in evs if e["type"] == "turn.end" and e["payload"]["messageId"] == reply["id"])
    assert err["seq"] < end["seq"] and end["payload"]["interruptedBy"] == "error"
    tokens = "".join(e["payload"]["delta"] for e in evs if e["type"] == "token" and e["payload"]["messageId"] == reply["id"])
    assert tokens == reply["content"] and 60 <= len(tokens) <= 140  # about 24 tokens
    rows = [r for r in await ledger(api) if r["message_id"] == reply["id"] and r["category"] == "chat"]  # M9: the reply's row
    assert len(rows) == 1 and rows[0]["cost_source"] == "estimate"
    # The fault was one-shot: the next reply completes.
    await command(api, sid, "send", {"text": "Try again."})
    await api.drive(12000)
    assert chars(await messages(api, sid))[-1]["status"] == "complete"
    assert (await snapshot(api, sid))["session"]["status"] == "active"
    await assert_reduces(api, sid)


class QuickEngine(SlowEngine):
    """A real-time stream fast enough to keep the coalescer's timer armed: one chunk every `step_ms`."""

    def __init__(self, api: Api, *, chunks: int, step_ms: float) -> None:
        super().__init__(api)
        self.chunks, self.step_ms = chunks, step_ms

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        spec = SimulatedReply(chunks=["word "] * self.chunks, first_token_ms=20, step_ms=self.step_ms, tail_ms=0,
                              total_ms=int(20 + self.step_ms * self.chunks), model="deepseek/deepseek-v4.1-flash",
                              tokens_in=900, tokens_cached=0, tokens_out=self.chunks, cost_usd=0.000001)
        async for ch in self.api.rt.gateway.simulated_stream(ctx.call_ctx("reply"), spec, self.api.rt.clock.sleep):
            if ch.content:
                yield Token(ch.content)


async def test_stop_pressed_twice_again_and_again_never_breaks_the_writer(api: Api) -> None:
    """docs/ai/checks/m9.md 9.6: the latency run hung on the turn after a Stop (its first token never written), and a
    later `POST /stop` failed with "database is locked". In real time, with tokens arriving every 7 ms so the coalescer's
    timer is busy writing, Stop is pressed twice at once at the first word, 15 times; every reply ends interrupted, a
    last reply still completes, and the log reduces."""
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedVictor"]))["session"]["id"]
    await api.drive(6000)
    assert (await api.post(f"{API}/_test/clock", {"release": True})).status_code == 200
    api.rt.ai.override("turn", QuickEngine(api, chunks=400, step_ms=7))

    async def until(pred: Any, what: str, limit_s: float = 5.0) -> dict[str, Any]:
        end = time.monotonic() + limit_s
        while time.monotonic() < end:
            last = chars(await messages(api, sid))
            if last and pred(last[-1]):
                return last[-1]
            await asyncio.sleep(0.01)
        raise AssertionError(f"timed out waiting for {what}")

    for i in range(15):
        await command(api, sid, "send", {"text": f"Go on ({i})."})
        await until(lambda m: m["status"] == "streaming" and m["content"], f"reply {i} to stream")
        await asyncio.gather(command(api, sid, "stop"), command(api, sid, "stop"))
        await until(lambda m: m["status"] == "interrupted", f"reply {i} to end interrupted")
    api.rt.ai.override("turn", QuickEngine(api, chunks=12, step_ms=7))
    await command(api, sid, "send", {"text": "One last thing."})
    last = await until(lambda m: m["status"] == "complete", "the last reply to complete")
    assert last["content"].strip()
    assert sum(1 for m in chars(await messages(api, sid)) if m["status"] == "interrupted") == 15
    await assert_reduces(api, sid)
