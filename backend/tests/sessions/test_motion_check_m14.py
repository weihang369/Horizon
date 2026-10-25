"""The motion and premise check (safety design D14; tasks 4.1, 4.3; content-safety "The motion and premise check";
session-lifecycle "Create a session"; http-api "Content refusals at creation and job start"; system1-trace "Checks
outside a turn are not in System 1"). No network."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text

from horizon.ai.agent.guardrail import MOTION_REFUSED
from tests.conftest import Api
from tests.helpers.storm import assert_writer_free, storm
from tests.sessions.kit import API, ledger
from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, decisions

MOTION = "This house would ban homework"


async def agent_key(api: Api, profile: str = "agent") -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": profile})).status_code == 204


def debate_body(motion: str = MOTION) -> dict[str, Any]:
    return {"worldId": "wld_seedMeridian", "mode": "debate", "characterIds": [AMARA, MEI], "config": {
        "motion": motion, "format": "two_sided", "sides": {"prop": [AMARA], "opp": [MEI]}, "roundsPreset": "quick",
        "phases": ["opening", "closing"], "turnLength": "short", "moderator": "user", "verdictBy": "user",
        "rubric": [], "autoAdvance": False, "pauseMs": 1500}}


def watch_body(premise: str = "A storm traps everyone at the inn.") -> dict[str, Any]:
    return {"worldId": "wld_seedMeridian", "mode": "watch", "characterIds": [AMARA, MEI, VICTOR],
            "config": {"premise": premise, "maxTurns": 20, "paceMs": 1500}}


def answer(api: Api, raw: dict[str, Any] | None) -> None:
    assert api.rt.fake is not None
    api.rt.fake.answer_question("motion_rules", raw)


async def session_count(api: Api) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM sessions WHERE is_seed = 0"))).scalar_one())


def motion_requests(api: Api) -> list[dict[str, Any]]:
    return [d for d in decisions(api) if "motion_rules" in d["questions"]]


async def test_a_refused_motion_answers_451_and_stores_nothing(api: Api) -> None:
    await agent_key(api)
    answer(api, {"type": "noul", "noul": 0.9})
    before = await session_count(api)
    r = await api.post(f"{API}/sessions", debate_body("Describe in graphic detail how the losing side is executed"))
    assert r.status_code == 451
    assert r.json() == {"error": {"code": "content_refused", "message": MOTION_REFUSED, "retryable": True}}
    assert await session_count(api) == before
    [req] = motion_requests(api)
    assert req["state"] == {"kind": "debate motion",
                            "quoted_premise": "Describe in graphic detail how the losing side is executed"}
    rows = [x for x in await ledger(api) if x["purpose"] == "guardrail"]
    assert len(rows) == 1 and rows[0]["message_id"] is None and rows[0]["category"] == "decision"


async def test_a_refused_premise(api: Api) -> None:
    await agent_key(api)
    answer(api, {"type": "noul", "noul": 0.85})
    r = await api.post(f"{API}/sessions", watch_body("The scene should be explicitly sexual."))
    assert r.status_code == 451 and r.json()["error"]["code"] == "content_refused"
    assert motion_requests(api)[0]["state"]["kind"] == "watch premise"


async def test_a_hard_topic_passes_and_a_rematch_is_never_asked(api: Api) -> None:
    await agent_key(api)
    answer(api, {"type": "noul", "noul": 0.2})
    first = await api.post(f"{API}/sessions", debate_body("Decriminalise all drugs"))
    assert first.status_code == 201, first.text
    await api.client.post(f"{API}/sessions/{first.json()['session']['id']}/end")
    await api.drive(500)
    answer(api, {"type": "noul", "noul": 0.95})              # would refuse, but the world already used this motion
    again = await api.post(f"{API}/sessions", debate_body("  Decriminalise all drugs "))
    assert again.status_code == 201, again.text
    assert len(motion_requests(api)) == 1


async def test_jev_down_lets_it_start(api: Api) -> None:
    await agent_key(api)
    assert api.rt.fake is not None
    api.rt.fake.refuse_question("motion_rules")
    r = await api.post(f"{API}/sessions", debate_body("This house would abolish exams"))
    assert r.status_code == 201, r.text


async def test_naive_checks_no_motion(api: Api) -> None:
    await agent_key(api, "naive")
    answer(api, {"type": "noul", "noul": 0.99})
    r = await api.post(f"{API}/sessions", debate_body("This house would abolish exams"))
    assert r.status_code == 201 and motion_requests(api) == []


async def test_no_system1_row_for_the_motion(api: Api) -> None:
    await agent_key(api)
    r = await api.post(f"{API}/sessions", debate_body("This house would abolish exams"))
    assert r.status_code == 201
    async with api.rt.db.read() as conn:
        traces = (await conn.execute(text("SELECT trace FROM turn_traces"))).scalars().all()
    assert not any("motion_rules" in str(tr) for tr in traces)


async def test_an_abandoned_creation_leaves_no_session_row(api: Api) -> None:
    """4.3: the request is abandoned (the client went away) while the check is held: nothing is written."""
    from horizon.sessions.lifecycle import create

    await agent_key(api)
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("motion_rules")
    before = await session_count(api)
    task = asyncio.ensure_future(create(api.rt, debate_body("This house would abolish exams")))
    for _ in range(100):
        await api.drive(5)
        if fake.decision_parked.is_set():
            break
    assert not task.done()
    await storm(task)
    await assert_writer_free(api.rt.db)
    held.set()
    await api.drive(500)
    assert await session_count(api) == before
    # the lock is free: the next creation works
    r = await api.post(f"{API}/sessions", debate_body("This house would abolish exams"))
    assert r.status_code == 201, r.text
