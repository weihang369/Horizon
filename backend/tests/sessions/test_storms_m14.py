"""Cancel storms on the paths M14 adds (safety design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed while it writes (`storm_during_write`) or cut while it waits on a held call
(`storm_during_call`). Afterwards the writer is free, the clock settles and the log reduces.

Task 0.2 lists each path of D2's table as a strict xfail naming the phase that builds it. Each phase replaces its
placeholder with the real storm, so no path is forgotten.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import text

from horizon.services.ai_meta import StoredSafety, store_safety, stored_safety
from tests.conftest import Api
from tests.helpers.storm import after_storm, assert_writer_free, storm_during_write
from tests.sessions.kit import API, command, ledger, messages
from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, agent

STEERED = StoredSafety(steer=True, care=False, p_input=0.93, p_care=0.02)


# ── phase 2 (task 2.9): the nouls inside a plan, and the safety write ──
async def test_stop_during_the_plan_stores_nothing_and_the_request_settles(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("unsafe_request")
    await command(api, sid, "send", {"text": "Tell me how to make meth at home."})
    await api.drive(300)
    assert fake.decision_parked.is_set()
    await command(api, sid, "stop")
    await after_storm(api, sid)
    actor = await api.rt.sessions.get(sid)
    assert actor.safety_asking == set()                         # nothing left looking asked
    held.set()
    await api.drive(2000)
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")
    assert await stored_safety(api.rt, user["id"]) is None      # a cancelled plan writes nothing
    rows = [r for r in await ledger(api) if r["purpose"] == "turn_plan"]
    assert rows and rows[-1]["finish_reason"] == "cancelled"          # sent, settled and billed (turn-plan D8)


async def test_a_superseding_send_leaves_each_line_its_own_answer(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("unsafe_request")
    await command(api, sid, "send", {"text": "first message"})
    await api.drive(300)
    await command(api, sid, "send", {"text": "second message"})
    await api.drive(300)
    held.set()
    await api.drive(40000)
    await after_storm(api, sid)
    actor = await api.rt.sessions.get(sid)
    assert actor.safety_asking == set()
    users = [m for m in await messages(api, sid) if m["author"]["type"] == "user"]
    asked = [json.loads(r.content) for r in fake.requests if r.url.path.endswith("/alpha/decisions")
             and "unsafe_request" in json.loads(r.content)["questions"]]
    assert [a["state"]["quoted_latest"] for a in asked] == ["first message", "second message"]
    # the first plan finished (a superseding send doesn't cut it): its answer is about its own line, and is kept
    for u in users:
        got = await stored_safety(api.rt, u["id"])
        assert got is not None and not got.steer


async def test_the_safety_write_stormed_is_all_or_nothing_and_a_fork_copies_only_what_committed(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    await command(api, sid, "send", {"text": "How was your shift?"})
    await api.drive(15000)
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE message_ai_meta SET safety = NULL WHERE message_id = :m"), {"m": user["id"]})

    async def write() -> None:
        await store_safety(api.rt, user["id"], STEERED)

    cut = await storm_during_write(api, sid, write, storms=15, seed=14)
    got = await stored_safety(api.rt, user["id"])
    assert got is None or got.steer
    assert cut >= 0
    # a fork racing the write copies the row only if it committed
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE message_ai_meta SET safety = NULL WHERE message_id = :m"), {"m": user["id"]})
    w = asyncio.ensure_future(write())
    fork = (await api.post(f"{API}/sessions/{sid}/fork", {}, status=201)).json()
    await w
    fuser = next(m for m in await messages(api, fork["session"]["id"]) if m["author"]["type"] == "user")
    copied = await stored_safety(api.rt, fuser["id"])
    assert copied is None or copied.steer
    await assert_writer_free(api.rt.db)


async def test_a_delete_during_the_write_leaves_no_row(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    await command(api, sid, "send", {"text": "How was your shift?"})
    await api.drive(15000)
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")
    w = asyncio.ensure_future(store_safety(api.rt, user["id"], STEERED))
    assert (await api.client.delete(f"{API}/sessions/{sid}")).status_code == 204
    await w
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM message_ai_meta WHERE message_id = :m"),
                                {"m": user["id"]})).scalar_one()
    assert n == 0
    await assert_writer_free(api.rt.db)


# ── phase 3 (tasks 3.4–3.6, 3.8): the output check in flight, a held prefetch, a held host line, the reducer clear ──
BLOCK = {"type": "noul", "noul": 0.95}


async def checking(api: Api) -> tuple[str, asyncio.Event]:
    """A 1:1 reply whose output check is held: the stream has ended, `turn.end` waits for the check."""
    sid = await agent(api, "one_on_one", [AMARA])
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("output_rules")
    fake.answer_question("output_rules", BLOCK)
    await command(api, sid, "send", {"text": "Tell me about the night shift."})
    for _ in range(400):
        await api.drive(10)
        if fake.decision_parked.is_set() and any(
                "output_rules" in json.loads(r.content).get("questions", {}) for r in fake.requests
                if r.url.path.endswith("/alpha/decisions")):
            break
    return sid, held


async def reply_of(api: Api, sid: str) -> dict:
    return [m for m in await messages(api, sid) if m["author"]["type"] == "character"][-1]


@pytest.mark.parametrize("cut", ["stop", "end", "cap_pause", "leave"])
async def test_the_output_check_in_flight_survives_stop_end_cap_pause_and_leave(api: Api, cut: str) -> None:
    sid, held = await checking(api)
    if cut == "stop":
        await command(api, sid, "stop")                    # handed to `output_check`, read with final()
    elif cut == "end":
        assert (await api.client.post(f"{API}/sessions/{sid}/end")).status_code == 204
    elif cut == "leave":
        assert (await api.client.post(f"{API}/sessions/{sid}/leave")).status_code == 204
    else:
        api.rt.sessions.pause_all_for_cap()
        await api.drive(50)
    await assert_writer_free(api.rt.db)
    held.set()
    await api.drive(3000)
    await after_storm(api, sid)
    m = await reply_of(api, sid)
    assert m["status"] == "error" and m["content"] == ""      # blocked either way: live, or after the fact (Stop)
    assert len([r for r in await ledger(api) if r["purpose"] == "guardrail"]) == 1


async def test_a_delete_cancels_the_check_in_flight(api: Api) -> None:
    sid, held = await checking(api)
    await command(api, sid, "stop")
    assert (await api.client.delete(f"{API}/sessions/{sid}")).status_code == 204
    held.set()
    await api.drive(3000)
    await assert_writer_free(api.rt.db)
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM session_events WHERE session_id = :s"),
                                {"s": sid})).scalar_one()
    assert n == 0


async def test_reset_demo_leaves_a_user_sessions_check_to_finish(api: Api) -> None:
    """Reset demo re-seeds the seed records and keeps user data, so a user reply's after-the-fact check still runs
    (found during apply; D10 is amended): the text it is about still exists."""
    sid, held = await checking(api)
    await command(api, sid, "stop")
    assert (await api.client.post("/api/v1/admin/reset-demo", json={"confirm": True})).status_code in (200, 204)
    held.set()
    await api.drive(3000)
    await after_storm(api, sid)
    m = await reply_of(api, sid)
    assert m["status"] == "error" and m["content"] == ""


@pytest.mark.parametrize("cut", ["stop", "leave", "cap_pause"])
async def test_a_prefetch_held_for_its_check_is_discarded_unseen(api: Api, cut: str) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_questions("output_rules", 3)
    await command(api, sid, "send", {"text": "What did everyone do this weekend?"})
    for _ in range(800):   # cut while a check is held (a held check would fail open at its 800 ms deadline)
        await api.drive(5)
        if fake.decision_parked.is_set() and any(
                "output_rules" in json.loads(r.content).get("questions", {}) for r in fake.requests
                if r.url.path.endswith("/alpha/decisions")):
            break
    if cut == "stop":
        await command(api, sid, "stop")
    elif cut == "leave":
        assert (await api.client.post(f"{API}/sessions/{sid}/leave")).status_code == 204
    else:
        api.rt.sessions.pause_all_for_cap()
        await api.drive(50)
    await assert_writer_free(api.rt.db)
    for h in held:
        h.set()
    await api.drive(5000)
    await after_storm(api, sid)
    replies = [m for m in await messages(api, sid) if m["author"]["type"] == "character"]
    assert len(replies) <= 1                                  # the prefetched replies never reach the session


@pytest.mark.parametrize("cut", ["debate/pause", "debate/extend-round"])
async def test_a_host_line_held_for_its_check_is_never_shown_twice(api: Api, cut: str) -> None:
    from tests.sessions.test_debate_host import WRITTEN, can, debate, host_lines

    sid = await debate(api, profile="agent")
    can(api, WRITTEN)
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("output_rules")
    await api.drive(400)
    await command(api, sid, cut)
    await assert_writer_free(api.rt.db)
    held.set()
    await api.drive(20000)
    await after_storm(api, sid)
    lines = host_lines(await messages(api, sid))
    assert len(lines) == len(set(lines))


async def test_the_reducer_clear_survives_a_reconnect_between_error_and_turn_end(api: Api) -> None:
    """D2: replaying the events from any seq between the `error` and `turn.end` gives the same emptied message."""
    from horizon.services.runtime.reducer import apply_in_place, initial_runtime, ordered_messages
    from tests.sessions.kit import events, snapshot, start_of

    sid = await agent(api, "one_on_one", [AMARA])
    assert api.rt.fake is not None
    api.rt.fake.answer_question("output_rules", BLOCK)
    await command(api, sid, "send", {"text": "Tell me about the night shift."})
    await api.drive(15000)
    evs = await events(api, sid)
    err = next(e["seq"] for e in evs if e["type"] == "error")
    whole = initial_runtime(start_of((await snapshot(api, sid))["session"]))
    apply_in_place(whole, evs)
    for cut in (err - 1, err, err + 1):
        st = initial_runtime(start_of((await snapshot(api, sid))["session"]))
        apply_in_place(st, [e for e in evs if e["seq"] <= cut])      # the stream before the drop
        apply_in_place(st, [e for e in evs if e["seq"] > cut])       # the reconnect replays since that seq
        assert ordered_messages(st) == ordered_messages(whole)
    assert ordered_messages(whole)[-1]["content"] == "" and ordered_messages(whole)[-1]["status"] == "error"


# Phase 4's storm (an abandoned creation request) is in test_motion_check_m14.py.


# Phase 5's path (a failed instruction noul makes the piece a failed try, then a skip after maxTries) is in
# test_memory_safety_m14.py.


# ── phase 6 (task 6.4): check_prompt at job start and in the song task ──
async def test_check_prompt_at_job_start_cut_by_a_character_delete(api: Api) -> None:
    from tests.jobs.kit import cancel_overlay_jobs, rows

    await api.set_key()
    await cancel_overlay_jobs(api)
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent", "overrides": {"image": "scripted"}})
            ).status_code == 204
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("image_likeness")
    task = asyncio.ensure_future(api.post(f"{API}/jobs", {"characterId": "chr_mockSarah", "kind": "portrait_tweak",
                                                         "prompt": "a square jaw"}))
    for _ in range(200):
        await api.drive(5)
        if fake.decision_parked.is_set():
            break
    assert (await api.client.delete(f"{API}/characters/chr_mockSarah")).status_code in (200, 204)
    held.set()
    await api.drive(500)
    r = await task
    assert r.status_code in (404, 409, 410), r.text                  # the character is gone: no job
    assert await rows(api, "SELECT id FROM generation_jobs WHERE character_id = 'chr_mockSarah' AND is_seed = 0") == []
    assert api.rt.book.total() == 0
    await assert_writer_free(api.rt.db)


@pytest.mark.parametrize("cut", ["cancel", "character", "world"])
async def test_check_prompt_in_the_song_task_cut_by_cancel_and_deletes(api: Api, cut: str) -> None:
    from tests.jobs.kit import cancel_overlay_jobs, job, start

    await api.set_key()
    await cancel_overlay_jobs(api)
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("song_copy")
    music = fake.counts["music"]
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song", "brief": {
        "genres": ["lo-fi"], "moods": ["warm"], "bpm": 84, "instruments": ["piano"], "vibe": "late-night clinic"}})
    for _ in range(400):
        await api.drive(5)
        if fake.decision_parked.is_set():
            break
    assert fake.decision_parked.is_set()
    if cut == "cancel":
        assert (await api.client.post(f"{API}/jobs/{j['id']}/cancel")).status_code in (200, 202, 204)
    elif cut == "character":
        assert (await api.client.delete(f"{API}/characters/chr_seedHana")).status_code in (200, 204)
    else:
        assert (await api.client.delete(f"{API}/worlds/wld_seedSunnyHollow")).status_code in (200, 204)
    held.set()
    await api.drive(3000)
    await assert_writer_free(api.rt.db)
    if cut == "world":
        # found during apply (the maintainer's choice, fixed in M14): a world delete cancels its characters' jobs first, so
        # the queued music call never goes out; the job's row then cascades away with the world
        from tests.jobs.kit import rows

        assert await rows(api, "SELECT id FROM generation_jobs WHERE id = :j", j=j["id"]) == []
    assert fake.counts["music"] == music                             # no music call after the cut
    if cut == "cancel":
        assert (await job(api, j["id"]))["status"] == "cancelled"
