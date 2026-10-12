"""Listener reactions through the runtime (turn-plan-emotion tasks 5.1–5.7; design D18–D21, D35; listener-reactions,
session-runtime and session-modes specs). No network: the fake answers in process (first option at 1/8: below the
floor), Decider fixtures answer without a request, and a parked request plus a queued response makes a late answer."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, events, ledger, messages
from tests.sessions.test_turn_plan import agent

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
CAST = [AMARA, MEI, VICTOR]


async def fixtures(api: Api, *items: tuple[str, str, float], clear: bool = False) -> None:
    body: dict[str, Any] = {"clear": clear, "set": [{"purpose": "reaction", "question": f"reaction:{cid}", "answer": {
        "choice": choice, "confidence": conf, "probabilities": {choice: conf}}} for cid, choice, conf in items]}
    assert (await api.post(f"{API}/_test/decider-fixtures", body)).status_code == 204


async def group(api: Api) -> str:
    return await agent(api, "group", CAST)


async def ask_amara(api: Api, sid: str, text: str = "What do you think?", ms: float = 20000) -> None:
    await command(api, sid, "send", {"text": text, "mentions": [AMARA]})
    await api.drive(ms)


def reaction_requests(api: Api) -> list[list[str]]:
    assert api.rt.fake is not None
    out = []
    for r in api.rt.fake.requests:
        if r.url.path.endswith("/alpha/decisions"):
            keys = list(json.loads(r.content).get("questions") or {})
            if keys and keys[0].startswith("reaction:"):
                out.append(keys)
    return out


def reactions(evs: list[dict[str, Any]]) -> list[tuple[str, str, str, float | None]]:
    return [(e["payload"]["characterId"], e["payload"]["emotion"], e["payload"]["source"], e["payload"].get("p"))
            for e in evs if e["type"] == "reaction"]


def confident(key: str, choice: str) -> httpx.Response:
    return httpx.Response(200, json={"id": "dec-late", "model": "typesafe/jev-1.13", "answers": {key: {
        "type": "choice", "choice": choice, "confidence": 0.95, "probabilities": {choice: 0.95}}},
        "usage": {"input_tokens": 300, "output_tokens": 0, "cost": 0.00003}})


# ── 5.6: one request per message, the questions and the row ──
async def test_two_listeners_one_request(api: Api) -> None:
    sid = await group(api)
    before = len(await ledger(api))
    await ask_amara(api, sid)
    reply = next(m for m in chars(await messages(api, sid)) if m["author"]["characterId"] == AMARA)
    assert reaction_requests(api)[0] == [f"reaction:{MEI}", f"reaction:{VICTOR}"]
    rows = [r for r in (await ledger(api))[before:] if r["purpose"] == "reaction"]
    assert rows[0]["category"] == "decision" and rows[0]["message_id"] == reply["id"]
    assert all(src == "default" for _, _, src, _ in reactions(await events(api, sid)))   # 1/8: nothing confident


async def test_confident_reactions_show_with_p_inside_the_window(api: Api) -> None:
    sid = await group(api)
    await fixtures(api, (MEI, "happy", 0.9), (VICTOR, "sad", 0.8))
    await command(api, sid, "send", {"text": "We won the grant!", "mentions": [AMARA]})
    await api.drive(300)
    evs = await events(api, sid)
    end = next(e for e in evs if e["type"] == "turn.end")
    await api.drive(20000)
    evs = await events(api, sid)
    first = [e for e in evs if e["type"] == "reaction" and e["payload"]["messageId"] == end["payload"]["messageId"]]
    assert {(e["payload"]["characterId"], e["payload"]["emotion"], e["payload"]["source"], e["payload"]["p"])
            for e in first} >= {(VICTOR, "sad", "classifier", 0.8)}
    assert all(f"reaction:{VICTOR}" not in keys for keys in reaction_requests(api))   # fixtures: not sent
    snap = (await api.get(f"{API}/sessions/{sid}")).json()
    faces = {p["characterId"]: p.get("currentEmotion") for p in snap["session"]["participants"]}
    assert faces[VICTOR] == "sad"


async def test_no_reactions_in_one_on_one(api: Api) -> None:
    sid = await agent(api)
    await command(api, sid, "send", {"text": "Hello there."})
    await api.drive(12000)
    assert "reaction" not in [r["purpose"] for r in await ledger(api)] and reaction_requests(api) == []


# ── 5.3: listeners read when the task runs; muted ones only fade ──
async def test_muted_listener_gets_no_question_and_fades(api: Api) -> None:
    sid = await group(api)
    await fixtures(api, (VICTOR, "surprised", 0.9))
    await ask_amara(api, sid, "Guess who quit today.")
    await fixtures(api, clear=True)
    await command(api, sid, "mute", {"characterId": VICTOR, "muted": True})
    n = len(reaction_requests(api))
    await ask_amara(api, sid, "Anyway, lunch?")
    assert all(f"reaction:{VICTOR}" not in keys for keys in reaction_requests(api)[n:])
    assert (VICTOR, "neutral", "default", None) in reactions(await events(api, sid))


# ── 5.6: a late answer shows nothing from Jev; the next speaker is never delayed ──
async def test_late_answer_and_next_speaker_not_delayed(api: Api) -> None:
    sid = await group(api)
    assert api.rt.fake is not None
    n0 = api.rt.fake.counts["decisions"]
    release = api.rt.fake.park_decision(n0 + 2)                            # route, then Amara's reaction request
    await command(api, sid, "send", {"text": "We won the grant!", "mentions": [AMARA]})
    await api.drive(3000)
    evs = await events(api, sid)
    ends = [e for e in evs if e["type"] == "turn.end"]
    nexts = [e for e in evs if e["type"] == "turn.next"]
    assert len(ends) >= 1 and len(nexts) >= 2                               # Mei's turn came while Jev was held
    gap = (_ms(nexts[1]["at"]) - _ms(ends[0]["at"]))
    assert gap <= 1000
    api.rt.fake.queued.append(confident(f"reaction:{MEI}", "angry"))
    release.set()
    await api.drive(5000)
    first = ends[0]["payload"]["messageId"]
    assert not [e for e in await events(api, sid) if e["type"] == "reaction" and e["payload"]["messageId"] == first
                and e["payload"]["source"] == "classifier"]
    late = [r for r in await ledger(api) if r["purpose"] == "reaction"]
    assert any(r["finish_reason"] == "late" for r in late)


def _ms(iso: str) -> float:
    from horizon.domain.timeutil import parse_iso, to_ms
    return float(to_ms(parse_iso(iso)))


# ── 5.7: the drop rules ──
async def test_a_user_message_drops_pending_reactions(api: Api) -> None:
    sid = await group(api)
    await fixtures(api, (MEI, "happy", 0.9), (VICTOR, "sad", 0.8))
    await command(api, sid, "send", {"text": "We won the grant!", "mentions": [AMARA]})
    await api.drive(100)                                                    # Amara's reply is done; reactions pending
    actor = await api.rt.sessions.get(sid)
    await actor.submit(_noop)
    await command(api, sid, "send", {"text": "Wait, actually, hold on.", "mentions": [AMARA]})
    await api.drive(250)
    evs = await events(api, sid)
    first = next(e for e in evs if e["type"] == "turn.end")["payload"]["messageId"]
    assert not [e for e in evs if e["type"] == "reaction" and e["payload"]["messageId"] == first]


async def test_manual_drops_pending_reactions(api: Api) -> None:
    sid = await group(api)
    await fixtures(api, (MEI, "happy", 0.9), (VICTOR, "sad", 0.8))
    await command(api, sid, "send", {"text": "We won the grant!", "mentions": [AMARA]})
    await api.drive(100)
    await command(api, sid, "set-emotion-mode", {"mode": "user"})
    await api.drive(20000)
    assert reactions(await events(api, sid)) == []


async def test_stop_cancels_reactions_and_the_summary_still_runs(api: Api) -> None:
    sid = await group(api)
    await fixtures(api, (MEI, "happy", 0.9), (VICTOR, "sad", 0.8))
    await command(api, sid, "send", {"text": "We won the grant!", "mentions": [AMARA]})
    await api.drive(100)
    actor = await api.rt.sessions.get(sid)
    marker = actor.background("summary", api.rt.clock.sleep(0.5))
    await command(api, sid, "stop")
    await api.drive(20000)
    assert reactions(await events(api, sid)) == [] and marker.done() and not marker.cancelled()


async def test_the_next_speakers_own_reaction_is_dropped_under_the_lock(api: Api) -> None:
    """D20: Mei's turn starts before her reaction to Amara is due: it is never emitted; Victor's still plays."""
    sid = await group(api)
    await fixtures(api, (MEI, "happy", 0.9), (VICTOR, "sad", 0.8))
    await ask_amara(api, sid, "We won the grant!")
    evs = await events(api, sid)
    first = next(e for e in evs if e["type"] == "turn.end")["payload"]["messageId"]
    on_first = [(e["payload"]["characterId"], e["payload"]["emotion"]) for e in evs
                if e["type"] == "reaction" and e["payload"]["messageId"] == first]
    mei_start = next(e for e in evs if e["type"] == "turn.start" and e["payload"]["author"].get("characterId") == MEI)
    mei_reacts = [e for e in evs if e["type"] == "reaction" and e["payload"]["messageId"] == first
                  and e["payload"]["characterId"] == MEI]
    assert all(e["seq"] < mei_start["seq"] for e in mei_reacts)             # never after her own turn.start
    assert (VICTOR, "sad") in on_first


async def test_emit_checked_runs_the_check_at_append_time(api: Api) -> None:
    sid = await group(api)
    actor = await api.rt.sessions.get(sid)
    seen: list[str | None] = []

    def check(state: dict[str, Any]) -> bool:
        seen.append(state.get("streamingId"))
        return state.get("streamingId") is None

    async def run() -> None:
        import asyncio
        async with actor.write_lock:
            start = asyncio.ensure_future(actor.emit({"type": "turn.start", "payload": {
                "messageId": "msg_lockcheck", "author": {"type": "character", "characterId": MEI}}}))
            await asyncio.sleep(0)
            checked = asyncio.ensure_future(actor.emit_checked({"type": "reaction", "payload": {
                "messageId": "msg_lockcheck", "characterId": MEI, "emotion": "happy", "source": "classifier"}}, check))
            await asyncio.sleep(0)
        await start
        assert await checked == []

    await actor.submit(run)
    assert seen == ["msg_lockcheck"]


async def _noop() -> None:
    return None


# ── D35: a refused reaction pauses nothing ──
async def test_budget_refusal_of_the_reaction_pauses_nothing(api: Api) -> None:
    sid = await group(api)
    actor = await api.rt.sessions.get(sid)
    from horizon.ai.contexts import ListenerView, ReactionRequest
    from horizon.sessions.context import session_context

    sctx = await session_context(api.rt, actor)
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 0.00001}})).status_code == 200
    req = ReactionRequest(session=sctx, message_id="msg_x", speaker_id=AMARA, line="We won.", seed="s:1",
                          listeners=[ListenerView(id=MEI, name="Mei Tanaka-Ruiz", face="surprised")])
    out = await api.rt.ai.reactions(True).predict(req)
    assert [(r.character_id, r.emotion, r.source) for r in out] == [(MEI, "neutral", "default")]   # the fade only
    await api.drive(500)
    types = [e["type"] for e in await events(api, sid)]
    assert "session.paused" not in types and "error" not in types


async def test_scripted_group_records_one_simulated_reaction_and_naive_none(api: Api) -> None:
    await api.set_key()                                                     # the scripted profile, with a key
    sid: str = (await create(api, "group", CAST))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Hi all", "mentions": [AMARA]})
    await api.drive(20000)
    rows = [r for r in await ledger(api) if r["purpose"] == "reaction"]
    assert rows and all(r["category"] == "decision" for r in rows)
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    n = len(rows)
    await command(api, sid, "send", {"text": "Again", "mentions": [AMARA]})
    await api.drive(20000)
    assert len([r for r in await ledger(api) if r["purpose"] == "reaction"]) == n   # naive with a key: no fake spend
