"""The follow plan through the runtime (group-watch tasks 4.2–4.5, 4.8; design D8, D9; follow-plan spec; session-runtime
"The summary check follows each turn"; provider-gateway "A refused follow plan pauses nothing"). No network."""

from __future__ import annotations

import json
from typing import Any

import httpx

from horizon.domain.timeutil import ms_from_iso
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages
from tests.sessions.test_group_plan import fixture, send
from tests.sessions.test_turn_plan import agent

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
TRIO = [AMARA, MEI, VICTOR]


def follow_requests(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [b for b in (json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/alpha/decisions"))
            if "who_second" in b["questions"]]


async def first_is_amara(api: Api) -> None:
    await fixture(api, "who_first", AMARA, 0.9, chr_seedAmara=0.9, chr_seedMei=0.05, chr_seedVictor=0.05)


def rows_of(m: dict[str, Any], purpose: str) -> list[dict[str, Any]]:
    return [r for r in m["trace"]["system1"]["questions"] if r["purpose"] == purpose]


# ── 4.2: a pick speaks second at once; no pick sleeps the rest of the gap ──
async def test_a_pick_speaks_second_at_once_with_the_follow_plans_face_and_trace(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    await fixture(api, "who_second", VICTOR, 0.9, purpose="follow_plan", chr_seedVictor=0.9, none=0.1)
    await fixture(api, f"emotion_reply:{VICTOR}", "surprised", 0.9, purpose="follow_plan")
    replies = await send(api, sid, "I'm moving to Lisbon next month.")
    assert [m["author"]["characterId"] for m in replies] == [AMARA, VICTOR]
    victor = replies[1]
    tr = victor["trace"]
    assert tr["routing"]["question"] == "who speaks up now?" and tr["routing"]["selected"] == VICTOR
    assert victor["emotion"] == "surprised" and victor["emotionSource"] == "classifier"
    follow = rows_of(victor, "follow_plan")
    who = next(r for r in follow if r["id"] == "who_second")
    assert (who["answer"], who["result"], who["action"]) == (VICTOR, "used", "speaks second")
    evs = await events(api, sid)
    end = next(e for e in evs if e["type"] == "turn.end" and e["payload"]["messageId"] == replies[0]["id"])
    nxt = next(e for e in evs if e["type"] == "turn.next" and e["seq"] > end["seq"])
    assert nxt["payload"]["nextSpeakerId"] == VICTOR
    assert ms_from_iso(nxt["at"]) - ms_from_iso(end["at"]) < 400       # no turn gap before a picked second reply
    await assert_reduces(api, sid)


def jev_picks_second(api: Api, cid: str) -> None:
    """The fake answers every choice at 1/n (below every floor); make its follow-plan answer a sure pick instead."""
    fake = api.rt.fake
    assert fake is not None
    plain = fake._decide

    def decide(body: dict[str, Any]) -> httpx.Response:
        resp = plain(body)
        if "who_second" not in (body.get("questions") or {}):
            return resp
        data = json.loads(resp.content)
        data["answers"]["who_second"] = {"type": "choice", "choice": cid, "confidence": 0.9,
                                         "probabilities": {cid: 0.9}}
        return httpx.Response(200, json=data)

    fake._decide = decide  # type: ignore[method-assign]


async def drive_until_turn_end(api: Api, sid: str, step: float = 5, limit: float = 30000) -> dict[str, Any]:
    spent = 0.0
    while spent < limit:
        end = next((e for e in await events(api, sid) if e["type"] == "turn.end"), None)
        if end is not None:
            return end
        await api.drive(step)
        spent += step
    raise AssertionError("no turn.end")


async def test_a_pick_120ms_after_turn_end_speaks_at_plus_120ms(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    jev_picks_second(api, VICTOR)
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)   # call 1, then the follow plan
    await command(api, sid, "send", {"text": "I'm moving to Lisbon next month."})
    end = await drive_until_turn_end(api, sid)
    t_end = ms_from_iso(end["at"])
    await api.drive(120 - (ms_from_iso(api.rt.clock.now().isoformat()) - t_end))
    release.set()
    await api.drive(20000)
    nxt = next(e for e in await events(api, sid) if e["type"] == "turn.next" and e["seq"] > end["seq"])
    assert nxt["payload"]["nextSpeakerId"] == VICTOR
    assert 120 <= ms_from_iso(nxt["at"]) - t_end < 130


async def test_no_pick_starts_the_next_job_at_plus_400ms(api: Api) -> None:
    """`none` answered at once: the job still holds the rest of the turn gap, so the follow plan never shortens it. (The
    queued job is a Next speaker: a second send would supersede the first job and end its gap at once, G5.)"""
    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    await fixture(api, "who_second", "none", 0.9, purpose="follow_plan")
    await command(api, sid, "send", {"text": "Ok, thanks."})
    await api.drive(50)
    await command(api, sid, "next-speaker", {"characterId": MEI})   # queued behind the first job
    await api.drive(30000)
    evs = await events(api, sid)
    end = next(e for e in evs if e["type"] == "turn.end")
    nxt = next(e for e in evs if e["type"] == "turn.next" and e["seq"] > end["seq"])
    assert 400 <= ms_from_iso(nxt["at"]) - ms_from_iso(end["at"]) < 410


async def test_none_gives_one_reply_and_writes_its_rows_to_the_first(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    await fixture(api, "who_second", "none", 0.9, purpose="follow_plan")
    replies = await send(api, sid, "Ok, thanks.")
    assert [m["author"]["characterId"] for m in replies] == [AMARA]
    follow = rows_of(replies[0], "follow_plan")
    who = next(r for r in follow if r["id"] == "who_second")
    assert (who["answer"], who["action"]) == ("none", "no second reply")
    assert {r["result"] for r in follow if r["id"] == "emotion_reply"} == {"not_used"}


async def test_a_late_follow_plan_gives_no_second_reply_and_nothing_hangs(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    assert api.rt.fake is not None
    n = api.rt.fake.counts["decisions"]
    release = api.rt.fake.park_decision(n + 2)                 # call 1 (its faces aren't fixtured), then the follow plan
    replies = await send(api, sid, "Who's coming Friday?", ms=6000)
    assert [m["author"]["characterId"] for m in replies] == [AMARA]
    who = next(r for r in rows_of(replies[0], "follow_plan") if r["id"] == "who_second")
    assert who["answer"] == "no second reply (late)" and who["result"] == "fallback" and "p" not in who
    late_call = next(c for c in replies[0]["trace"]["calls"] if c["purpose"] == "follow_plan")
    assert late_call["fallback"] is True
    actor = await api.rt.sessions.get(sid)
    assert not actor.busy                                        # the job ended at the deadline
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "follow_plan"][-1]["finish_reason"] == "late"


# ── 4.3: where it runs and where it doesn't ──
async def test_one_mention_may_add_a_voice_but_never_offers_the_mentioned(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await send(api, sid, "Victor, thoughts?", [VICTOR])
    (body,) = follow_requests(api)
    assert VICTOR not in body["questions"]["who_second"]["criteria"]
    assert set(body["questions"]["who_second"]["criteria"]) == {AMARA, MEI, "none"}


async def test_two_mentions_policy_mentioned_and_everyone_start_no_follow_plan(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await send(api, sid, "Mei and Victor?", [MEI, VICTOR], ms=40000)
    await command(api, sid, "set-responder-policy", {"policy": "mentioned"})
    await send(api, sid, "Victor only.", [VICTOR])
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    await send(api, sid, "Everyone, quick round.", ms=60000)
    assert follow_requests(api) == []
    assert not [r for r in await ledger(api) if r["purpose"] == "follow_plan"]


async def test_naive_and_scripted_groups_start_no_follow_plan(api: Api) -> None:
    await api.set_key()
    sid: str = (await create(api, "group", TRIO))["session"]["id"]
    await api.drive(6000)
    await send(api, sid, "Hello all")
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    await send(api, sid, "Hello again")
    assert follow_requests(api) == [] and not [r for r in await ledger(api) if r["purpose"] == "follow_plan"]


async def test_never_a_third_reply(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    await fixture(api, "who_second", VICTOR, 0.9, purpose="follow_plan")
    replies = await send(api, sid, "Big news!", ms=40000)
    assert len(replies) == 2 and len(follow_requests(api)) == 0   # fixtures: no request; and only one follow plan ran


# ── 4.5: a refused follow plan pauses nothing ──
async def test_a_refused_follow_plan_pauses_nothing(api: Api) -> None:
    from horizon.gateway.pipeline import AFTER_TURN

    assert "follow_plan" in AFTER_TURN
    from horizon.gateway.context import PURPOSE_CATEGORY

    assert PURPOSE_CATEGORY["follow_plan"] == "decision"
    sid = await agent(api, "group", TRIO)
    actor = await api.rt.sessions.get(sid)
    from horizon.ai.contexts import FollowRequest
    from horizon.sessions.context import session_context

    sctx = await session_context(api.rt, actor)
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 0.00001}})).status_code == 200
    req = FollowRequest(session=sctx, first_id=AMARA, first_name="Amara", first_message_id="msg_x", first_text="Hm.",
                        message="Well?", candidates=[MEI, VICTOR], started_at=api.rt.clock.now())
    handle = api.rt.ai.planner(True).start_follow(req)
    from datetime import timedelta

    task = api.rt.spawn("follow", handle.by(api.rt.clock.now() + timedelta(seconds=1)))
    await api.drive(1500)
    plan = await task
    assert plan.second is None and plan.outcome == "fallback"
    await api.drive(500)
    types = [e["type"] for e in await events(api, sid)]
    assert "session.paused" not in types


async def test_scripted_messages_untouched(api: Api) -> None:
    """A smoke check that a follow plan leaves the event log reducible and every reply complete."""
    sid = await agent(api, "group", TRIO)
    await send(api, sid, "One", ms=20000)
    await send(api, sid, "Two", ms=20000)
    assert all(m["status"] == "complete" for m in chars(await messages(api, sid)))
    await assert_reduces(api, sid)


# ── 7.2 (moved here from phase 4): the second reply's cue and label ──
async def test_a_second_replys_request_names_the_first_replier_and_is_labelled_agent3(api: Api) -> None:
    import sqlalchemy as sa

    from horizon.db import tables as t

    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    await fixture(api, "who_second", VICTOR, 0.9, purpose="follow_plan")
    assert api.rt.fake is not None
    n = len(api.rt.fake.requests)
    replies = await send(api, sid, "I'm moving to Lisbon next month.")
    chats = [json.loads(r.content) for r in api.rt.fake.requests[n:] if r.url.path.endswith("/chat/completions")]
    tails = [str(b["messages"][-1]["content"]) for b in chats if b["messages"][-1]["role"] == "system"]
    sentence = "Amara has just answered. Don't repeat them; add your own angle, or answer Amara directly."
    assert sum(sentence in x for x in tails) == 1
    async with api.rt.db.read() as conn:
        labels = dict((await conn.execute(sa.select(t.turn_traces.c.message_id, t.turn_traces.c.prompt_version)
                                          .where(t.turn_traces.c.message_id.in_([m["id"] for m in replies])))).all())
    assert [labels[m["id"]] for m in replies] == ["agent-9", "agent-11"]
