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


# ── M10 phase 5 (task 5.7): G5's supersede ──
async def test_a_storm_on_a_superseding_send_leaves_the_writer_free(api: Api) -> None:
    """A send that supersedes a running job (its first reply done, the gap begun) is cancelled on every loop turn while
    it bumps the epoch and appends the user's message: the writer is free after each storm and the log reduces."""
    import asyncio
    import random

    from horizon.sessions.modes import group
    from tests.sessions.kit import assert_reduces, create, events
    from tests.sessions.test_supersede import TRIO

    await api.set_key()
    sid: str = (await create(api, "group", TRIO))["session"]["id"]
    await api.drive(6000)
    actor: SessionActor = await api.rt.sessions.get(sid)
    rng = random.Random(5)
    for i in range(10):
        start = len(await events(api, sid))
        await command(api, sid, "send", {"text": f"Round {i}?"})
        for _ in range(400):
            await api.drive(25)
            if any(e["type"] == "turn.end" for e in (await events(api, sid))[start:]):
                break
        task = asyncio.ensure_future(group.send(actor, f"Never mind {i}", []))
        await storm(task, after_s=rng.uniform(0.0, 0.02))
        await assert_writer_free(api.rt.db)
        await api.drive(40000)
    await assert_writer_free(api.rt.db)
    await assert_reduces(api, sid)


async def test_a_storm_in_the_turn_next_check_leaves_the_writer_free(api: Api, monkeypatch: Any) -> None:
    """The storm starts as a reply's `turn.next` goes through the epoch check under the write lock."""
    import asyncio

    from tests.sessions.kit import assert_reduces, create
    from tests.sessions.test_supersede import TRIO

    await api.set_key()
    sid: str = (await create(api, "group", TRIO))["session"]["id"]
    await api.drive(6000)
    actor: SessionActor = await api.rt.sessions.get(sid)
    checked = actor.emit_checked
    storms: list[asyncio.Task[Any]] = []

    async def stormed(event: Any, check: Any) -> Any:
        task = asyncio.current_task()
        if event.get("type") == "turn.next" and not storms and task is not None:
            storms.append(asyncio.ensure_future(storm(task)))
        return await checked(event, check)

    monkeypatch.setattr(actor, "emit_checked", stormed)
    await command(api, sid, "send", {"text": "Who's up for a walk?"})
    for _ in range(400):
        if storms and storms[0].done():
            break
        await api.drive(25)
    assert storms and storms[0].done()
    await assert_writer_free(api.rt.db)
    monkeypatch.setattr(actor, "emit_checked", checked)
    await command(api, sid, "send", {"text": "Hello again?"})
    await api.drive(40000)
    await assert_writer_free(api.rt.db)
    await assert_reduces(api, sid)


async def test_a_storm_on_step_ins_follow_plan_leaves_the_writer_free(api: Api) -> None:
    from tests.sessions.kit import assert_reduces
    from tests.sessions.test_follow_plan import drive_until_turn_end
    from tests.sessions.test_group_g4 import _agent_watch
    from tests.sessions.test_group_plan import fixture
    from tests.sessions.test_supersede import VICTOR

    sid = await _agent_watch(api)
    await fixture(api, "who_first", VICTOR, 0.9, chr_seedVictor=0.9, chr_seedMei=0.05, chr_seedAmara=0.05)
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)   # call 1 (faces), then the follow plan
    await command(api, sid, "watch/step-in", {"text": "Who left the door open?"})
    await drive_until_turn_end(api, sid)
    actor: SessionActor = await api.rt.sessions.get(sid)
    worker = actor._worker
    assert worker is not None and not worker.done()
    await storm(worker)
    await assert_writer_free(api.rt.db)
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "follow_plan"][-1]["finish_reason"] == "cancelled"
    await assert_reduces(api, sid)


# ── M10 phase 6 (task 6.6): the watch's plan made ahead ──
async def _watch_with_a_parked_plan_ahead(api: Api, *extra: int) -> tuple[str, SessionActor, list[Any]]:
    """An `agent` watch in MANUAL (so every decision is a plan): call 1 opens, call 2 is made ahead (parked), and any
    `extra` calls after it are parked too."""
    from tests.sessions.test_watch_plan import _until_turn_end, agent_watch

    sid = await agent_watch(api, manual=True, maxTurns=10, paceMs=1500)
    assert api.rt.fake is not None
    n = api.rt.fake.counts["decisions"]
    releases = [api.rt.fake.park_decision(n + k) for k in (2, *extra)]
    await _until_turn_end(api, sid, 1)
    await api.drive(100)
    return sid, await api.rt.sessions.get(sid), releases


async def _settle(api: Api, sid: str, releases: list[Any]) -> list[str]:
    from tests.sessions.kit import assert_reduces

    await command(api, sid, "stop")
    await api.drive(2000)
    for r in releases:
        r.set()
    await api.drive(5000)
    await assert_writer_free(api.rt.db)
    await assert_reduces(api, sid)
    return [r["finish_reason"] for r in await ledger(api) if r["purpose"] == "turn_plan"]


async def test_a_storm_on_the_plan_made_ahead_while_parked(api: Api) -> None:
    sid, actor, releases = await _watch_with_a_parked_plan_ahead(api)
    assert actor.mode.plan_ahead is not None
    _, task = actor.mode.plan_ahead
    await storm(task)
    await assert_writer_free(api.rt.db)
    finish = await _settle(api, sid, releases)
    assert finish[-1] == "cancelled"


async def test_a_storm_in_the_turn_count_write_after_the_plan_ahead_starts(api: Api, monkeypatch: Any) -> None:
    import asyncio

    from tests.sessions.test_watch_plan import agent_watch

    sid = await agent_watch(api, manual=True, maxTurns=10, paceMs=1500)
    actor: SessionActor = await api.rt.sessions.get(sid)
    emit = actor.emit
    storms: list[asyncio.Task[Any]] = []

    async def stormed(*events: Any, **k: Any) -> Any:
        task = asyncio.current_task()
        if (not storms and task is not None and actor.mode.plan_ahead is not None
                and any(e.get("type") == "watch.state" and e["payload"].get("turnsTaken") == 1 for e in events)):
            storms.append(asyncio.ensure_future(storm(task)))
        return await emit(*events, **k)

    monkeypatch.setattr(actor, "emit", stormed)
    for _ in range(400):
        if storms and storms[0].done():
            break
        await api.drive(25)
    assert storms and storms[0].done()
    monkeypatch.setattr(actor, "emit", emit)
    await assert_writer_free(api.rt.db)
    finish = await _settle(api, sid, [])
    assert "cancelled" in finish or len(finish) == 2      # the plan made ahead: cancelled by Stop, or already answered


async def test_a_storm_during_the_redo_after_a_fingerprint_change(api: Api) -> None:
    sid, actor, releases = await _watch_with_a_parked_plan_ahead(api, 3)
    await command(api, sid, "watch/direct", {"text": "The lights go out."})
    assert api.rt.fake is not None
    for _ in range(400):                                   # until the redo (call 3) is parked
        if api.rt.fake.counts["decisions"] >= 3:
            break
        await api.drive(25)
    assert api.rt.fake.counts["decisions"] >= 3
    worker = actor._worker
    assert worker is not None and not worker.done()
    await storm(worker)
    await assert_writer_free(api.rt.db)
    finish = await _settle(api, sid, releases)
    assert finish[-1] == "cancelled"                      # the redo, cut while Jev was parked
