"""Virtual time (session-runtime design D2): ordered timers, settle, the guard and release."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from horizon.domain.clock import FrozenClock, calendar_for
from horizon.domain.vclock import Inbox, SettleTimeout, Slots

CAL = calendar_for("Asia/Kuala_Lumpur")
T0 = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)


def clock() -> FrozenClock:
    return FrozenClock(CAL, T0)


async def test_same_instant_timers_fire_in_registration_order() -> None:
    c = clock()
    order: list[str] = []

    async def at(name: str, s: float) -> None:
        await c.sleep(s)
        order.append(name)

    for name, s in (("b", 2), ("a1", 1), ("a2", 1), ("c", 3), ("a3", 1)):
        c.activity.spawn(name, at(name, s))
    await c.advance(5000)
    assert order == ["a1", "a2", "a3", "b", "c"]


async def test_timers_past_the_target_wait() -> None:
    c = clock()
    order: list[str] = []

    async def at(name: str, s: float) -> None:
        await c.sleep(s)
        order.append(name)

    c.activity.spawn("x", at("x", 2))
    await c.advance(1999)
    assert order == []
    assert c.pending == 1
    await c.advance(1)
    assert order == ["x"]


async def test_settle_waits_for_the_woken_tasks_follow_up_work() -> None:
    """A woken task's follow-up I/O (here: a slow thread call, like a DB write) is done before advance returns."""
    c = clock()
    writes: list[int] = []

    async def worker() -> None:
        await c.sleep(1)
        await asyncio.to_thread(lambda: __import__("time").sleep(0.05))
        writes.append(1)
        await c.sleep(1)  # a chained timer within the same advance
        await asyncio.sleep(0.01)
        writes.append(2)

    c.activity.spawn("worker", worker())
    await c.advance(2000)
    assert writes == [1, 2]


async def test_spawned_children_count_until_done() -> None:
    c = clock()
    done: list[str] = []

    async def child() -> None:
        await asyncio.sleep(0.02)
        done.append("child")

    async def parent() -> None:
        await c.sleep(1)
        c.activity.spawn("child", child())

    c.activity.spawn("parent", parent())
    await c.advance(1000)
    assert done == ["child"]


async def test_guard_names_a_stuck_holder() -> None:
    c = clock()
    stuck = asyncio.Event()

    async def hangs() -> None:
        await stuck.wait()  # waits without giving up its token

    task = c.activity.spawn("stuck-turn", hangs())
    with pytest.raises(SettleTimeout, match="stuck-turn"):
        await c.activity.settle(guard_s=0.1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await c.settle()


async def test_release_wakes_sleepers_and_sleep_becomes_real() -> None:
    c = clock()
    woke: list[bool] = []

    async def long_sleep() -> None:
        await c.sleep(3600)
        woke.append(True)

    task = c.activity.spawn("long", long_sleep())
    await c.settle()
    c.release()
    await asyncio.wait_for(task, 1)
    assert woke == [True]
    assert not c.frozen
    assert abs((c.now() - datetime.now(UTC)).total_seconds()) < 5
    await asyncio.wait_for(c.sleep(0.01), 1)


async def test_cancelled_sleeper_keeps_the_count_balanced() -> None:
    c = clock()

    async def sleeper() -> None:
        await c.sleep(10)

    task = c.activity.spawn("s", sleeper())
    await c.settle()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await c.settle()
    assert c.activity.busy == {}
    await c.advance(20_000)  # the cancelled timer is skipped


async def test_inbox_hands_the_token_to_the_consumer() -> None:
    c = clock()
    inbox: Inbox[int] = Inbox()
    got: list[int] = []

    async def consumer() -> None:
        while True:
            item = await inbox.get()
            await asyncio.sleep(0.01)
            got.append(item)

    task = c.activity.spawn("actor", consumer())
    await c.settle()
    inbox.put(1)
    inbox.put(0, front=True)
    await c.settle()
    assert got == [0, 1]
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_slots_hand_off_while_the_holder_sleeps() -> None:
    c = clock()
    slots = Slots(1)
    order: list[str] = []

    async def user(name: str) -> None:
        async with slots.slot():
            order.append(f"{name}+")
            await c.sleep(1)
            order.append(f"{name}-")

    c.activity.spawn("a", user("a"))
    c.activity.spawn("b", user("b"))
    await c.advance(1000)
    await c.advance(1000)
    assert order == ["a+", "a-", "b+", "b-"]
    assert slots.peak == 1 and slots.in_use == 0
