"""The stored safety answers (safety design D5; tasks 1.5–1.6; content-safety "The safety answers are stored with the
line"; session-event-sourcing "AI-owned per-message data is not event-sourced"). No network."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from horizon.services.ai_meta import StoredSafety, store_rewrite, store_safety, stored_rewrite, stored_safety, stored_safety_many
from tests.conftest import Api
from tests.helpers.storm import assert_writer_free, storm
from tests.sessions.kit import API, assert_reduces, events, messages
from tests.sessions.test_gates_m12 import AMARA, agent, send

STEERED = StoredSafety(steer=True, care=False, p_input=0.93, p_care=0.02, versions={"unsafe_request": 1, "at_risk": 1})


async def a_line(api: Api) -> tuple[str, str]:
    sid = await agent(api, "one_on_one", [AMARA])
    await send(api, sid, "Tell me something about nights.")
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")
    return sid, str(user["id"])


async def test_write_then_read(api: Api) -> None:
    _sid, mid = await a_line(api)
    assert await stored_safety(api.rt, mid) is None                  # nothing stored yet: not flagged
    assert await store_safety(api.rt, mid, STEERED)
    got = await stored_safety(api.rt, mid)
    assert got is not None and (got.steer, got.care, got.p_input, got.p_care) == (True, False, 0.93, 0.02)
    assert got.at and got.versions == {"unsafe_request": 1, "at_risk": 1}
    assert await stored_safety_many(api.rt, [mid, "msg_none"]) == {mid: got}


async def test_a_missing_message_writes_nothing(api: Api) -> None:
    await a_line(api)
    assert not await store_safety(api.rt, "msg_gone", STEERED)
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM message_ai_meta WHERE message_id = 'msg_gone'"))).scalar_one()
    assert n == 0


async def test_the_answers_sit_beside_a_stored_rewrite(api: Api) -> None:
    _sid, mid = await a_line(api)
    assert await store_rewrite(api.rt, mid, AMARA, "night shift fatigue")
    assert await store_safety(api.rt, mid, STEERED)
    assert await stored_rewrite(api.rt, mid, AMARA) == "night shift fatigue"   # neither write wipes the other
    assert await store_rewrite(api.rt, mid, AMARA, "night shift rest")
    assert (await stored_safety(api.rt, mid)) is not None


async def test_an_old_row_reads_not_flagged(api: Api) -> None:
    _sid, mid = await a_line(api)
    assert await store_rewrite(api.rt, mid, AMARA, "night shift fatigue")    # a row with no safety (before M14)
    assert await stored_safety(api.rt, mid) is None
    async with api.rt.db.write() as tx:                                     # a malformed value reads the same
        await tx.conn.execute(text("UPDATE message_ai_meta SET safety = '{\"p\": 1}' WHERE message_id = :m"), {"m": mid})
    assert await stored_safety(api.rt, mid) is None


async def test_a_fork_copies_and_a_delete_cascades(api: Api) -> None:
    sid, mid = await a_line(api)
    assert await store_safety(api.rt, mid, STEERED)
    fork = (await api.post(f"{API}/sessions/{sid}/fork", {}, status=201)).json()
    fid = fork["session"]["id"]
    fuser = next(m for m in await messages(api, fid) if m["author"]["type"] == "user")
    copied = await stored_safety(api.rt, fuser["id"])
    assert copied is not None and copied.steer and copied.p_input == 0.93
    assert (await api.client.delete(f"{API}/sessions/{sid}")).status_code == 204
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM message_ai_meta WHERE message_id = :m"), {"m": mid})).scalar_one()
    assert n == 0
    assert await stored_safety(api.rt, fuser["id"]) is not None             # the fork keeps its own copy


async def test_the_answers_are_not_event_sourced(api: Api) -> None:
    """1.6: rebuilding the session from its events neither needs the stored answers nor recreates them."""
    sid, mid = await a_line(api)
    assert await store_safety(api.rt, mid, STEERED)
    evs = await events(api, sid)
    assert not any("pInput" in str(e.get("payload")) or "steer" in str(e.get("payload", {}).get("safety", ""))
                   for e in evs)
    await assert_reduces(api, sid)
    assert await stored_safety(api.rt, mid) is not None                     # still read from its row


async def test_a_stormed_write_leaves_the_writer_free(api: Api) -> None:
    _sid, mid = await a_line(api)
    for _ in range(10):
        task = asyncio.ensure_future(store_safety(api.rt, mid, STEERED))
        await storm(task)
    await assert_writer_free(api.rt.db)
    got = await stored_safety(api.rt, mid)
    assert got is None or got.steer                                         # all or nothing
