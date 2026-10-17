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


def _placeholder(phase: int) -> None:
    pytest.fail(f"built in phase {phase}")


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


@pytest.mark.xfail(strict=True, reason="phase 3: the output check in flight")
async def test_the_output_check_cut_by_stop_end_cap_pause_leave_delete_and_reset() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 3: a finished prefetch held for its check")
async def test_a_prefetch_held_for_its_check_cut_by_stop_leave_and_cap_pause() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 3: a host line or verdict prose held for its check")
async def test_a_host_line_or_verdict_held_for_its_check_cut_by_extend_skip_and_clear() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 3: the reducer clear")
async def test_the_reducer_clear_survives_a_reconnect_between_error_and_turn_end() -> None:
    _placeholder(3)


@pytest.mark.xfail(strict=True, reason="phase 4: the motion check")
async def test_the_motion_check_cut_by_an_abandoned_request() -> None:
    _placeholder(4)


@pytest.mark.xfail(strict=True, reason="phase 5: the instruction noul fails in a pause run")
async def test_a_failed_instruction_noul_makes_the_piece_a_failed_try() -> None:
    _placeholder(5)


@pytest.mark.xfail(strict=True, reason="phase 6: check_prompt at job start")
async def test_check_prompt_at_job_start_cut_by_a_character_delete() -> None:
    _placeholder(6)


@pytest.mark.xfail(strict=True, reason="phase 6: check_prompt in the song task")
async def test_check_prompt_in_the_song_task_cut_by_cancel_and_deletes() -> None:
    _placeholder(6)
