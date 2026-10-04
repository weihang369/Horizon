"""Prefetched openings and the D-77 discard (session-runtime "Discarded prefetches still drain energy"; design D5,
OQ-7; tasks 7.4–7.6)."""

from __future__ import annotations

import math
from typing import Any

from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages

TRIO = ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]


def _shape(evs: list[dict[str, Any]], mid: str) -> list[str]:
    """A message's own event types, with tokens collapsed and the emotion's position (timing variety) ignored."""
    out: list[str] = []
    for e in evs:
        if e["payload"].get("messageId") != mid or e["type"] == "emotion" or e["type"] == "reaction":
            continue
        if e["type"] == "token" and out and out[-1] == "token":
            continue
        out.append(e["type"])
    return out


async def test_everyone_answer_prefetches_and_releases_like_normal_turns(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "group", TRIO))["session"]["id"]
    api.rt.llm_slots.peak = 0
    await command(api, sid, "everyone-answer")
    await api.drive(40000)
    replies = chars(await messages(api, sid))
    assert [m["author"]["characterId"] for m in replies] == TRIO
    assert all(m["status"] == "complete" for m in replies)
    evs = await events(api, sid)
    shapes = [_shape(evs, m["id"]) for m in replies]
    assert shapes[0] == shapes[1] == shapes[2] == ["turn.start", "token", "turn.end", "insight"]
    for m in replies:  # each reply has its turn.next / thinking preamble right before it
        start = next(e for e in evs if e["type"] == "turn.start" and e["payload"]["messageId"] == m["id"])
        before = [e["type"] for e in evs if e["seq"] < start["seq"]][-2:]
        assert before == ["turn.next", "turn.thinking"]
        reply_call = next(c for c in m["trace"]["calls"] if c["purpose"] == "reply")
        assert reply_call["costUsd"] == m["usage"]["costUsd"] > 0
    rows = [r for r in await ledger(api) if r["purpose"] == "reply"]
    assert sorted(r["message_id"] for r in rows) == sorted(m["id"] for m in replies)  # linked on release
    assert 2 <= api.rt.llm_slots.peak <= 4
    # Released openings wait for nothing: their first token follows the preamble at once.
    from horizon.domain.timeutil import ms_from_iso

    for m in replies[1:]:
        start = next(e for e in evs if e["type"] == "turn.next" and e["payload"]["nextSpeakerId"] == m["author"]["characterId"])
        first = next(e for e in evs if e["type"] == "token" and e["payload"]["messageId"] == m["id"])
        assert ms_from_iso(first["at"]) - ms_from_iso(start["at"]) < 600
    await assert_reduces(api, sid)


async def _debate(api: Api) -> str:
    await api.set_key()
    sid: str = (await create(api, "debate", ["chr_seedAmara", "chr_seedVictor"], config={
        "motion": "This house would tax sugary drinks", "format": "two_sided",
        "sides": {"prop": ["chr_seedAmara"], "opp": ["chr_seedVictor"]}, "roundsPreset": "quick",
        "phases": ["opening", "closing"], "turnLength": "short", "moderator": "user", "verdictBy": "arbiter",
        "rubric": [], "autoAdvance": True, "pauseMs": 1500}))["session"]["id"]
    return sid


async def test_stop_during_a_debate_opening_discards_the_prefetch(api: Api) -> None:
    sid = await _debate(api)
    victor_before = (await api.json(f"{API}/characters/chr_seedVictor"))["energy"]
    for _ in range(40):
        await api.drive(250)
        if any(m["status"] == "streaming" for m in await messages(api, sid)):
            break
    actor = api.rt.sessions.peek(sid)
    assert actor is not None and len(actor.mode.debate_prefetch) == 1  # Victor's opening runs ahead
    await command(api, sid, "stop")
    await api.drive(5000)
    msgs = await messages(api, sid)
    speakers = {m["author"].get("characterId") for m in chars(msgs)}
    assert speakers == {"chr_seedAmara"}
    rows = [r for r in await ledger(api) if r["purpose"] == "reply" and r["character_id"] == "chr_seedVictor"]
    assert len(rows) == 1 and rows[0]["message_id"] is None
    victor_after = (await api.json(f"{API}/characters/chr_seedVictor"))["energy"]
    points = math.ceil(rows[0]["cost_usd"] / 0.0001 - 1e-9)
    assert points > 0 and victor_before["current"] - victor_after["current"] in (points, points - 1)
    known = {m["id"] for m in msgs}
    assert all(e["payload"].get("messageId") in (None, *known) for e in await events(api, sid))
    assert actor.prefetches == set()


async def test_debate_opening_prefetch_is_released_in_order(api: Api) -> None:
    sid = await _debate(api)
    await api.drive(90000)
    msgs = await messages(api, sid)
    opening = [m for m in chars(msgs) if (m.get("debate") or {}).get("phase") == "opening"]
    assert [m["author"]["characterId"] for m in opening] == ["chr_seedAmara", "chr_seedVictor"]
    rows = {r["message_id"] for r in await ledger(api) if r["purpose"] == "reply"}
    assert {m["id"] for m in chars(msgs)} <= rows


async def test_preflight_lock_wait_is_measured(api: Api) -> None:
    """OQ-7: the p95 preflight lock wait under the group/prefetch load is recorded (a cache only if p95 > 20 ms)."""
    await api.set_key()
    sid = (await create(api, "group", TRIO))["session"]["id"]
    api.rt.gateway.lock_waits_ms.clear()
    for _ in range(3):
        await command(api, sid, "everyone-answer")
        await api.drive(40000)
    waits = sorted(api.rt.gateway.lock_waits_ms)
    assert len(waits) >= 9
    p95 = waits[max(0, math.ceil(0.95 * len(waits)) - 1)]
    print(f"\n[OQ-7] preflight lock wait over {len(waits)} calls: p95 = {p95:.3f} ms, max = {waits[-1]:.3f} ms")
    assert p95 < 20
