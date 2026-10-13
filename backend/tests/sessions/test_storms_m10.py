"""Cancel storms on the paths M10 adds (group-watch design D2; session-runtime "New cancel paths leave the writer
free"). Each path is stormed while it writes and while its plan waits on a parked Jev answer; afterwards no
connection is checked out, a fresh write commits within 5 s, and the plan's ledger row says `cancelled`.

Phase 0 checks the helpers on M9's 1:1 plan; later phases add a test per new path."""

from __future__ import annotations

from typing import Any

from horizon.sessions.actor import SessionActor
from tests.conftest import Api
from tests.helpers.storm import assert_writer_free, park_next_decision, storm
from tests.sessions.kit import command, ledger
from tests.sessions.test_turn_plan import agent


async def test_a_storm_while_the_one_on_one_plan_waits_leaves_the_writer_free(api: Api) -> None:
    sid = await agent(api)
    release = park_next_decision(api.rt)
    await command(api, sid, "send", {"text": "Are you awake?"})
    await api.drive(300)                                   # turn.next and turn.thinking are out; Jev is parked
    actor: SessionActor = await api.rt.sessions.get(sid)
    worker = actor._worker
    assert worker is not None and not worker.done()
    await storm(worker)
    await assert_writer_free(api.rt.db)
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["finish_reason"] == "cancelled"
    assert not [r for r in await ledger(api) if r["purpose"] == "reply"]


# ── M10 phase 3 (task 3.6): the group cast plan ──
async def test_a_storm_while_the_group_cast_plan_waits_leaves_the_writer_free(api: Api) -> None:
    from tests.sessions.kit import assert_reduces

    sid = await agent(api, "group", ["chr_seedAmara", "chr_seedMei", "chr_seedVictor"])
    release = park_next_decision(api.rt)
    await command(api, sid, "send", {"text": "Anyone around?"})
    await api.drive(200)                                   # the job is planning; Jev is parked
    actor: SessionActor = await api.rt.sessions.get(sid)
    worker = actor._worker
    assert worker is not None and not worker.done()
    await storm(worker)
    await assert_writer_free(api.rt.db)
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["finish_reason"] == "cancelled"
    assert not [r for r in await ledger(api) if r["purpose"] == "reply"]
    await assert_reduces(api, sid)


async def test_a_storm_in_the_user_messages_append_leaves_the_writer_free(api: Api) -> None:
    """`group.send` itself is cancelled on every loop turn while it appends the user's message (and, if it got that
    far, while it queues the planned job): the append commits whole or not at all, and the writer is free after each
    storm. (Run in a task of its own: storming `submit()` would only cancel the caller's future, not the append.)"""
    import asyncio
    import random

    from horizon.services.runtime.reducer import ordered_messages
    from horizon.sessions.modes import group
    from tests.sessions.kit import assert_reduces

    sid = await agent(api, "group", ["chr_seedAmara", "chr_seedMei", "chr_seedVictor"])
    actor: SessionActor = await api.rt.sessions.get(sid)
    rng = random.Random(3)
    cut = 0
    for i in range(30):
        users = sum(1 for m in ordered_messages(actor.state) if m["author"]["type"] == "user")
        task = asyncio.ensure_future(group.send(actor, f"Ping {i}", []))
        await storm(task, after_s=rng.uniform(0.0, 0.03))
        await assert_writer_free(api.rt.db)
        after = sum(1 for m in ordered_messages(actor.state) if m["author"]["type"] == "user")
        assert after - users in (0, 1)
        cut += after == users
        await actor.clear()
    print(f"\nstorms on the user message's append: {cut} of 30 cut before it committed")
    assert 0 < cut < 30   # the storms hit both sides
    await api.drive(60000)
    await assert_writer_free(api.rt.db)
    await assert_reduces(api, sid)


# ── M10 phase 4 (task 4.8): the follow plan ──
async def _group_with_a_parked_follow_plan(api: Api) -> tuple[str, SessionActor, Any]:
    from tests.sessions.test_follow_plan import TRIO, first_is_amara

    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)                             # call 1 still asks the faces; the follow plan is call 2
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)
    return sid, await api.rt.sessions.get(sid), release


async def _follow_row_cancelled(api: Api, sid: str, release: Any) -> None:
    from tests.sessions.kit import assert_reduces

    release.set()
    await api.drive(2000)
    rows = [r for r in await ledger(api) if r["purpose"] == "follow_plan"]
    assert rows and rows[-1]["finish_reason"] == "cancelled"
    assert len([r for r in await ledger(api) if r["purpose"] == "reply"]) == 1   # no second reply
    await assert_reduces(api, sid)


async def test_a_storm_while_the_follow_plan_waits_leaves_the_writer_free(api: Api) -> None:
    from tests.sessions.test_follow_plan import drive_until_turn_end

    sid, actor, release = await _group_with_a_parked_follow_plan(api)
    await command(api, sid, "send", {"text": "I'm moving to Lisbon next month."})
    await drive_until_turn_end(api, sid)                  # the job now waits on the parked follow plan
    worker = actor._worker
    assert worker is not None and not worker.done()
    await storm(worker)
    await assert_writer_free(api.rt.db)
    await _follow_row_cancelled(api, sid, release)


async def test_a_storm_in_the_first_replys_turn_end_write_leaves_the_writer_free(api: Api, monkeypatch: Any) -> None:
    """The follow plan has started at the stream's end; the storm starts as `finish` does, so cancels land in the
    guardrail check, the ledger reads and the `turn.end` append. The follow handle is cancelled with the job."""
    import asyncio

    from horizon.sessions.turn import TurnRunner

    sid, _, release = await _group_with_a_parked_follow_plan(api)
    finish = TurnRunner.finish
    storms: list[asyncio.Task[Any]] = []

    async def stormed_finish(self: TurnRunner, *a: Any, **k: Any) -> str:
        task = asyncio.current_task()
        assert task is not None
        if not storms:
            storms.append(asyncio.ensure_future(storm(task)))
        return await finish(self, *a, **k)

    monkeypatch.setattr(TurnRunner, "finish", stormed_finish)
    await command(api, sid, "send", {"text": "I'm moving to Lisbon next month."})
    for _ in range(400):
        if storms and storms[0].done():
            break
        await api.drive(50)
    assert storms and storms[0].done()
    monkeypatch.setattr(TurnRunner, "finish", finish)
    await assert_writer_free(api.rt.db)
    await _follow_row_cancelled(api, sid, release)
