"""Group mode and the Jev router (session-modes "Group responders", "Group routing is traced", "Group steering
commands"; ai-ports "Jev router"; http-api "Decider fixture over HTTP"; tasks 6.6, 7.1–7.3)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from horizon.ai.decider import Decider
from horizon.gateway.context import CallContext
from horizon.gateway.decisions import DecisionsResponse
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages

TRIO = ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]


async def _group(api: Api, cast: list[str] = TRIO) -> str:
    await api.set_key()
    sid: str = (await create(api, "group", cast))["session"]["id"]
    return sid


async def test_auto_policy_with_a_mention(api: Api) -> None:
    sid = await _group(api)
    await command(api, sid, "send", {"text": "Victor, what do you make of it?", "mentions": ["chr_seedVictor"]})
    await api.drive(30000)
    replies = chars(await messages(api, sid))
    assert replies[0]["author"]["characterId"] == "chr_seedVictor" and replies[0]["forcedSpeaker"] is True
    assert 1 <= len(replies) <= 2
    assert replies[0]["trace"]["routing"]["forcedBy"] == "mention"
    await assert_reduces(api, sid)


async def test_route_call_in_every_reply_of_a_send(api: Api) -> None:
    sid = await _group(api)
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    await command(api, sid, "send", {"text": "What should we cook tonight?"})
    await api.drive(40000)
    replies = chars(await messages(api, sid))
    assert len(replies) == 3
    routes = [[c for c in m["trace"]["calls"] if c["purpose"] == "route"] for m in replies]
    assert all(len(r) == 1 for r in routes) and all(r == routes[0] for r in routes)
    tr = replies[0]["trace"]["routing"]
    assert tr["question"] and tr["selected"] == replies[0]["author"]["characterId"] and tr["candidates"]
    rows = [r for r in await ledger(api) if r["purpose"] == "route"]
    assert len(rows) == 1 and rows[0]["message_id"] is None and rows[0]["category"] == "decision"


async def test_muted_participant_is_skipped(api: Api) -> None:
    sid = await _group(api)
    await command(api, sid, "mute", {"characterId": "chr_seedMei", "muted": True})
    await command(api, sid, "everyone-answer")
    await api.drive(40000)
    speakers = [m["author"]["characterId"] for m in chars(await messages(api, sid))]
    assert sorted(speakers) == ["chr_seedAmara", "chr_seedVictor"]


async def test_next_speaker_nudge_and_random(api: Api) -> None:
    sid = await _group(api)
    await command(api, sid, "next-speaker", {"characterId": "chr_seedMei"})
    await api.drive(15000)
    first = chars(await messages(api, sid))[-1]
    assert first["author"]["characterId"] == "chr_seedMei"
    nudge = next(e for e in await events(api, sid) if e["type"] == "turn.next")
    assert nudge["payload"]["forcedBy"] == "nudge"
    await command(api, sid, "next-speaker", {})
    await api.drive(15000)
    second = chars(await messages(api, sid))[-1]
    assert second["author"]["characterId"] != "chr_seedMei"


async def test_mentioned_policy_without_mentions_answers_nobody(api: Api) -> None:
    sid = await _group(api)
    await command(api, sid, "set-responder-policy", {"policy": "mentioned"})
    await command(api, sid, "send", {"text": "Anyone?"})
    await api.drive(20000)
    assert chars(await messages(api, sid)) == []


# ── the Jev router ──
async def _naive_router(api: Api) -> None:
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"router": "naive"}})
    assert r.status_code == 204


async def test_jev_router_answer_is_used(api: Api) -> None:
    sid = await _group(api)
    await _naive_router(api)
    await command(api, sid, "send", {"text": "Who wants to start?"})
    await api.drive(30000)
    replies = chars(await messages(api, sid))
    assert replies and replies[0]["author"]["characterId"] == "chr_seedAmara"  # the fake answers the first option
    tr = replies[0]["trace"]
    assert tr["routing"]["candidates"] and "fallback" not in next(c for c in tr["calls"] if c["purpose"] == "route")
    rows = [r for r in await ledger(api) if r["purpose"] == "route"]
    assert len(rows) == 1 and rows[0]["message_id"] is None and rows[0]["provider"] != "scripted"


def _slow_decider(api: Api, delay: float, answers: Mapping[str, Any] | None = None) -> None:
    gw = api.rt.gateway

    async def decide(state: Any, questions: Mapping[str, Mapping[str, Any]], ctx: CallContext) -> DecisionsResponse:
        await asyncio.sleep(delay)
        resp = await gw.decide(state, questions, ctx)
        return resp if answers is None else DecisionsResponse(resp.generation_id, answers, resp.usage, resp.model)

    api.rt._decider = Decider(decide, gw.cfg.timeouts, api.rt.decider_fixtures)


async def test_jev_router_timeout_falls_back_and_the_late_answer_is_recorded(api: Api) -> None:
    sid = await _group(api)
    await _naive_router(api)
    _slow_decider(api, 0.6)
    await command(api, sid, "send", {"text": "Who wants to start?"})
    await api.drive(30000)
    replies = chars(await messages(api, sid))
    assert len(replies) == 1
    tr = replies[0]["trace"]
    assert "candidates" not in tr["routing"] and tr["routing"]["reason"] == "fallback"
    route = next(c for c in tr["calls"] if c["purpose"] == "route")
    assert route["fallback"] is True
    await api.rt.decider.idle()
    assert len([r for r in await ledger(api) if r["purpose"] == "route"]) == 1  # the late answer is still billed


async def test_jev_router_invalid_answer_falls_back(api: Api) -> None:
    sid = await _group(api)
    await _naive_router(api)
    _slow_decider(api, 0.0, {"speaker": {"choice": "chr_nobody"}})
    await command(api, sid, "send", {"text": "Who wants to start?"})
    await api.drive(30000)
    replies = chars(await messages(api, sid))
    assert len(replies) == 1 and replies[0]["trace"]["routing"]["reason"] == "fallback"


async def test_decider_fixture_over_http(api: Api) -> None:
    sid = await _group(api)
    await _naive_router(api)
    r = await api.post(f"{API}/_test/decider-fixtures",
                       {"set": [{"purpose": "route", "question": "speaker", "answer": {"choice": "chr_seedMei"}}]})
    assert r.status_code == 204
    await command(api, sid, "send", {"text": "Who wants to start?"})
    await api.drive(30000)
    replies = chars(await messages(api, sid))
    assert replies[0]["author"]["characterId"] == "chr_seedMei"
    assert replies[0]["trace"]["routing"]["selected"] == "chr_seedMei"
    assert [r for r in await ledger(api) if r["purpose"] == "route"] == []
    assert (await api.post(f"{API}/_test/decider-fixtures", {"clear": True})).status_code == 204
