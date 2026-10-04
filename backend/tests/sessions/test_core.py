"""Event writer, actor and manager core (session-runtime "One writer per session"; tasks 2.1–2.5, 4.7)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.services import reads
from horizon.sessions.fork import fork_events, replay_base
from horizon.sessions.writer import EventWriter
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, messages


async def _fresh_from_seed(api: Api, seed_sid: str, new_sid: str) -> tuple[str, list[dict[str, Any]]]:
    """A fresh session row (the seed recording's start) and the seed's events renamed for it."""
    async with api.rt.db.read() as conn:
        src = await reads.get_session(conn, seed_sid)
        evs = await reads.events_after(conn, seed_sid, 0, 10_000)
    renamed, _ = fork_events(evs, src, None, new_sid, api.rt.now_iso())
    base = {**replay_base(src), "id": new_sid, "isSeed": False, "state": None}
    row, parts = mp.session_rows(base, is_seed=False)
    async with api.rt.db.write() as tx:
        await tx.conn.execute(t.sessions.insert().values(**row))
        await tx.conn.execute(t.participants.insert(), parts)
    return new_sid, renamed


async def test_writer_projects_a_seed_recording(api: Api) -> None:
    sid, renamed = await _fresh_from_seed(api, "ses_seedDebate4Day", "ses_writerTest1")
    w = await EventWriter.load(api.rt.db, sid, api.rt.now_iso)
    assert w.last_seq == 0
    for i in range(0, len(renamed), 7):  # appended in batches, like a live session
        await w.append([{"type": e["type"], "payload": e["payload"]} for e in renamed[i:i + 7]])
    evs = await events(api, sid)
    assert [e["seq"] for e in evs] == list(range(1, len(renamed) + 1))
    msgs = await messages(api, sid)
    assert len(msgs) > 5 and all(m["status"] != "streaming" for m in msgs)
    assert any(m.get("citations") for m in msgs)
    await assert_reduces(api, sid)
    async with api.rt.db.read() as conn:
        cites = (await conn.execute(t.message_citations.select().where(
            t.message_citations.c.message_id.in_([m["id"] for m in msgs])))).all()
        traces = (await conn.execute(t.turn_traces.select().where(
            t.turn_traces.c.message_id.in_([m["id"] for m in msgs])))).all()
    assert len(cites) == sum(len(m.get("citations") or []) for m in msgs)
    assert len(traces) == sum(1 for m in msgs if m.get("trace"))
    # A restarted writer continues the sequence.
    w2 = await EventWriter.load(api.rt.db, sid, api.rt.now_iso)
    assert w2.last_seq == len(renamed)


async def test_twenty_concurrent_commands_never_interleave(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "group", ["chr_seedAmara", "chr_seedVictor"]))["session"]["id"]
    actor = await api.rt.sessions.get(sid)
    start = actor.writer.last_seq
    done: list[int] = []

    def cmd(n: int) -> Any:
        async def run() -> None:
            for _ in range(3):
                await actor.emit({"type": "turn.thinking", "payload": {"characterId": "chr_seedAmara"}})
                await asyncio.sleep(0)
            done.append(n)
        return run

    await asyncio.gather(*(actor.submit(cmd(n)) for n in range(20)))
    evs = [e for e in await events(api, sid) if e["seq"] > start]
    assert [e["seq"] for e in evs] == list(range(start + 1, start + 61))
    assert done == list(range(20))  # one at a time, in arrival order


async def test_concurrent_sends_are_not_interleaved(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    await asyncio.gather(command(api, sid, "send", {"text": "first question"}),
                         command(api, sid, "send", {"text": "second question"}))
    await api.drive(30000)
    msgs = await messages(api, sid)
    assert [m["author"]["type"] for m in msgs] == ["character", "user", "user", "character", "character"]
    evs = await events(api, sid)
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    # Each reply's events are contiguous from its turn.start to its turn.end.
    for m in chars(msgs)[1:]:
        own = [e["seq"] for e in evs if e["payload"].get("messageId") == m["id"] and e["type"] in ("turn.start", "turn.end")]
        between = [e for e in evs if own[0] < e["seq"] < own[1]]
        assert all(e["payload"].get("messageId") in (m["id"], None) for e in between)
    await assert_reduces(api, sid)


async def test_manager_get_races_share_one_actor_and_reset_clears(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "group", ["chr_seedAmara", "chr_seedVictor"]))["session"]["id"]
    await api.rt.sessions.release(sid)
    a, b = await asyncio.gather(api.rt.sessions.get(sid), api.rt.sessions.get(sid))
    assert a is b
    await api.post(f"{API}/admin/factory-reset", {"confirm": "DELETE EVERYTHING"}, status=204)
    assert api.rt.sessions.actors == {}


# ── preconditions (http-api "Session command routes") ──
async def test_unknown_seed_and_missing_key(api: Api) -> None:
    r = await api.post(f"{API}/sessions/ses_seedAmaraHeadache/send", {"text": "hi"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"
    await api.set_key()
    r = await api.post(f"{API}/sessions/ses_nope/send", {"text": "hi"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    before = len(await events(api, "ses_seedAmaraHeadache"))
    r = await api.post(f"{API}/sessions/ses_seedAmaraHeadache/send", {"text": "hi"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert len(await events(api, "ses_seedAmaraHeadache")) == before
    r = await api.post(f"{API}/sessions/ses_seedAmaraHeadache/set-readable-mode", {"on": True})
    assert r.status_code == 409


@pytest.mark.parametrize(("case", "status", "code"), [
    ("ended", 409, "conflict"), ("mode", 409, "conflict"), ("empty", 422, "validation"), ("invalid_key", 401, "invalid_key"),
    ("cap", 402, "daily_budget_exceeded"), ("other_live", 409, "conflict"),
])
async def test_rejections_before_202(api: Api, case: str, status: int, code: str) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    body: dict[str, Any] = {"text": "hello"}
    name = "send"
    other = ""
    if case == "ended":
        assert (await api.client.post(f"{API}/sessions/{sid}/end")).status_code == 204
    elif case == "mode":
        name, body = "debate/pause", {}
    elif case == "empty":
        body = {"text": "   "}
    elif case == "invalid_key":
        await api.set_key("sk-or-bad-0001")
        secret = api.rt.keys.secret()
        assert secret is not None
        api.rt.keys.mark_rejected(secret)
    elif case == "cap":
        # The greeting has already spent more than this cap.
        r = await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 0.0001}})
        assert r.status_code == 200
    elif case == "other_live":
        other = (await create(api, "one_on_one", ["chr_seedVictor"]))["session"]["id"]
        await api.drive(6000)
        await command(api, other, "send", {"text": "Tell me everything about precedent."})
        for _ in range(40):
            await api.drive(250)
            if any(m["status"] == "streaming" for m in await messages(api, other)):
                break
    r = await api.post(f"{API}/sessions/{sid}/{name}", body)
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code
    if case == "other_live":
        assert r.json()["error"]["details"]["activeSessionId"] == other


async def test_accepted_send_stores_the_user_message_before_202_and_retry_is_idempotent(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    h = {"Idempotency-Key": "send-0001"}
    r1 = await api.client.post(f"{API}/sessions/{sid}/send", json={"text": "hello there"}, headers=h)
    assert r1.status_code == 202 and r1.json() == {}
    users = [m for m in await messages(api, sid) if m["author"]["type"] == "user"]
    assert [m["content"] for m in users] == ["hello there"]
    r2 = await api.client.post(f"{API}/sessions/{sid}/send", json={"text": "hello there"}, headers=h)
    assert r2.status_code == 202 and r2.headers.get("idempotent-replay") == "true"
    await api.drive(12000)
    assert len([m for m in await messages(api, sid) if m["author"]["type"] == "user"]) == 1
    assert len(chars(await messages(api, sid))) == 2
