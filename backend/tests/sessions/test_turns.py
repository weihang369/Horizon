"""The turn runner and the 1:1 slice details (session-runtime "Turn order", "Trace ownership", "Reply drains energy as
a session event", "Citations are stored at turn end", "A blocked reply is scrubbed"; session-lifecycle create;
session-modes settings; tasks 4.1–4.6, 10.4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import CitationMap, Emotion, GuardrailResult, Token, TracePatch, TurnEvent
from horizon.db import tables as t
from horizon.gateway.pipeline import SimulatedReply
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages, snapshot


class FixedEngine:
    """A test engine: a fixed text at a fixed cost, plus a citation map and a trace patch that tries to set `energy`."""

    name = "fixed"
    version = "t1"
    prompt_version = None

    def __init__(self, api: Api, text: str = "Read the review [1] closely. It is clear.", cost: float = 0.0004) -> None:
        self.api = api
        self.text = text
        self.cost = cost

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        spec = SimulatedReply(chunks=[self.text[i:i + 6] for i in range(0, len(self.text), 6)], first_token_ms=500,
                              step_ms=60, tail_ms=20, total_ms=1500, model="deepseek/deepseek-v4.1-flash",
                              tokens_in=1000, tokens_cached=0, tokens_out=12, cost_usd=self.cost)
        yield Emotion("thinking")
        async for ch in self.api.rt.gateway.simulated_stream(ctx.call_ctx("reply"), spec, self.api.rt.clock.sleep):
            if ch.content:
                yield Token(ch.content)
        yield CitationMap([{"n": 1, "sourceId": "kno_seedAmara1", "title": "Review", "type": "file", "chunkId": "kch_a1",
                            "quote": "One"},
                           {"n": 2, "sourceId": "kno_seedAmara1", "title": "Review", "type": "file", "chunkId": "kch_a2",
                            "quote": "Two"}])
        yield TracePatch({"energy": {"characterId": "chr_seedAmara", "spent": 999, "remaining": 0, "max": 1},
                          "context": {"budget": 12000, "used": {"system": 1, "persona": 2, "memory": 0, "knowledge": 0,
                                                                "history": 3, "user": 4, "mode": 5}}})


async def _one_on_one(api: Api) -> str:
    await api.set_key()
    sid: str = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    return sid


async def test_turn_order_trace_ownership_drain_and_citations(api: Api) -> None:
    sid = await _one_on_one(api)
    api.rt.ai.override("turn", FixedEngine(api))
    before = (await api.json(f"{API}/characters/chr_seedAmara"))["energy"]["current"]
    await command(api, sid, "send", {"text": "What does the review say?"})
    await api.drive(10000)
    reply = chars(await messages(api, sid))[-1]
    evs = await events(api, sid)
    start = next(e for e in evs if e["type"] == "turn.start" and e["payload"]["messageId"] == reply["id"])
    # Message ID exists before spend: the ledger row carries the turn.start message ID.
    rows = [r for r in await ledger(api) if r["purpose"] == "reply" and r["message_id"] == start["payload"]["messageId"]]
    assert len(rows) == 1
    # Trace ownership: the backend's energy section wins; the engine's context section is kept.
    tr = reply["trace"]
    assert tr["energy"]["spent"] == 4 and tr["energy"]["characterId"] == "chr_seedAmara"
    assert tr["context"]["used"]["user"] == 4
    assert tr["model"]["costUsd"] == reply["usage"]["costUsd"] == 0.0004
    assert next(c for c in tr["calls"] if c["purpose"] == "reply")["costUsd"] == 0.0004
    # The drain is a session event after turn.end.
    end = next(e for e in evs if e["type"] == "turn.end" and e["payload"]["messageId"] == reply["id"])
    energy = next(e for e in evs if e["type"] == "energy" and e["seq"] > end["seq"])
    assert energy["payload"]["spent"] == 4
    after = (await api.json(f"{API}/characters/chr_seedAmara"))["energy"]["current"]
    assert before - after == 4 or before - after == 3  # net of a fraction of a point of regeneration
    # Unused citation dropped: only [1] is in the content.
    assert [c["n"] for c in end["payload"]["citations"]] == [1]
    assert [c["n"] for c in reply["citations"]] == [1]
    async with api.rt.db.read() as conn:
        n = (await conn.execute(t.message_citations.select().where(t.message_citations.c.message_id == reply["id"]))).all()
    assert len(n) == 1
    await assert_reduces(api, sid)


async def test_blocked_reply_is_scrubbed(api: Api) -> None:
    sid = await _one_on_one(api)

    class Block:
        async def check(self, ctx: Any, text: str) -> GuardrailResult:
            return GuardrailResult("block", [{"name": "sfw", "verdict": "block", "p": 0.99}])

    api.rt.ai.override("guardrail", Block())
    await command(api, sid, "send", {"text": "Say something you shouldn't."})
    await api.drive(12000)
    reply = chars(await messages(api, sid))[-1]
    evs = await events(api, sid)
    end = next(e for e in evs if e["type"] == "turn.end" and e["payload"]["messageId"] == reply["id"])
    err = next(e for e in evs if e["type"] == "error" and e["payload"].get("messageId") == reply["id"])
    assert end["payload"]["status"] == "error" and err["payload"]["code"] == "content_refused"
    assert reply["content"] == "" and reply["status"] == "error"
    tokens = [e for e in evs if e["type"] == "token" and e["payload"]["messageId"] == reply["id"]]
    assert tokens and all(e["payload"]["delta"] == "" for e in tokens)
    assert any(r["message_id"] == reply["id"] for r in await ledger(api))  # the spend stays
    await assert_reduces(api, sid)


# ── create (session-lifecycle) ──
async def test_create_validation(api: Api) -> None:
    await api.set_key()
    r = await api.post(f"{API}/sessions", {"worldId": "wld_seedMeridian", "mode": "one_on_one",
                                          "characterIds": ["chr_seedAmara", "chr_seedVictor"]})
    assert r.status_code == 422
    assert r.json()["error"]["details"] == {"field": "characterIds", "min": 1, "max": 1, "got": 2}
    r = await api.post(f"{API}/sessions", {"worldId": "wld_seedMeridian", "mode": "group", "characterIds": ["chr_seedAmara"]})
    assert r.status_code == 422 and r.json()["error"]["details"]["min"] == 2
    count = len(await api.json(f"{API}/worlds/wld_seedMeridian/sessions"))
    r = await api.post(f"{API}/sessions", {"worldId": "wld_seedMeridian", "mode": "one_on_one", "characterIds": ["chr_seedHana"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert len(await api.json(f"{API}/worlds/wld_seedMeridian/sessions")) == count


async def test_create_without_key_and_greeting_waits_for_the_clock(api: Api) -> None:
    r = await api.post(f"{API}/sessions", {"worldId": "wld_seedMeridian", "mode": "one_on_one", "characterIds": ["chr_seedAmara"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"
    await api.set_key()
    snap = await create(api, "one_on_one", ["chr_seedAmara"])
    sid = snap["session"]["id"]
    assert snap["session"]["status"] == "active" and snap["lastSeq"] == 2  # session.state + one energy, already applied
    assert snap["messages"] == [] and snap["session"]["title"] == "Chat with Amara"
    assert chars(await messages(api, sid)) == []  # frozen: nothing moves until the clock does
    await api.drive(6000)
    msgs = chars(await messages(api, sid))
    assert len(msgs) == 1 and msgs[0]["status"] == "complete"


async def test_create_announces_the_session(api: Api) -> None:
    await api.set_key()
    sub = api.rt.bus.subscribe("global")
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    seen = []
    while not sub.queue.empty():
        seen.append(sub.queue.get_nowait())
    assert {"type": "entity.changed", "kind": "session", "id": sid, "worldId": "wld_seedMeridian"} in seen


# ── reactions and the turn gap ──
async def test_reactions_land_after_turn_end_and_never_delay_the_next_speaker(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "group", ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]))["session"]["id"]
    await command(api, sid, "everyone-answer")
    await api.drive(40000)
    from horizon.domain.timeutil import ms_from_iso

    evs = await events(api, sid)
    ends = [e for e in evs if e["type"] == "turn.end"]
    reactions = [e for e in evs if e["type"] == "reaction"]
    assert len(ends) == 3 and reactions
    for r in reactions:
        end = next(e for e in ends if e["payload"]["messageId"] == r["payload"]["messageId"])
        assert 300 <= ms_from_iso(r["at"]) - ms_from_iso(end["at"]) <= 800
    nexts = [e for e in evs if e["type"] == "turn.next"]
    for end, nxt in zip(ends, nexts[1:], strict=False):
        assert ms_from_iso(nxt["at"]) - ms_from_iso(end["at"]) == 400  # the turn gap, reactions or not


# ── settings commands ──
async def test_settings_commands(api: Api) -> None:
    sid = await _one_on_one(api)
    n = len(await events(api, sid))
    await command(api, sid, "set-readable-mode", {"on": True})
    evs = (await events(api, sid))[n:]
    assert [e["type"] for e in evs] == ["session.state"] and evs[0]["payload"] == {"settings": {"readableMode": True}}
    assert (await snapshot(api, sid))["session"]["readableMode"] is True
    await command(api, sid, "set-emotion", {"characterId": "chr_seedAmara", "emotion": "sad"})
    ev = (await events(api, sid))[-1]
    assert ev["type"] == "emotion" and ev["payload"] == {"characterId": "chr_seedAmara", "emotion": "sad", "source": "user"}
    for name, body, key in (("set-emotion-mode", {"mode": "user"}, "emotionMode"),
                            ("set-music-policy", {"policy": "scene_bed"}, "musicPolicy")):
        await command(api, sid, name, body)
        assert (await events(api, sid))[-1]["payload"]["settings"] == {key: next(iter(body.values()))}
    await assert_reduces(api, sid)


async def test_mute_and_responder_policy(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "group", ["chr_seedAmara", "chr_seedVictor"]))["session"]["id"]
    await command(api, sid, "mute", {"characterId": "chr_seedVictor", "muted": True})
    parts = (await snapshot(api, sid))["session"]["participants"]
    assert [p["mutedByUser"] for p in parts] == [False, True]
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    assert (await snapshot(api, sid))["session"]["config"]["responderPolicy"] == "everyone"
    await assert_reduces(api, sid)
