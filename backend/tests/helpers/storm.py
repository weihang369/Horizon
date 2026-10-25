"""Cancel storms (docs/ai/checks/m9.md 9.6, "Stop can break the database writer"; group-watch design D2).

A storm cancels a task on every loop turn until it ends, so cancels land in BEGIN, in COMMIT, in ROLLBACK and in any
wait in between. Every new M10 cancel path is stormed twice: once while it writes and once while its plan waits on a
parked Jev answer. Afterwards the writer must be free.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text

from horizon.db.uow import Database

FREE_WITHIN_S = 5.0


async def storm(task: asyncio.Task[Any], *, after_s: float = 0.0) -> None:
    """Let `task` run for `after_s` seconds, then cancel it on every loop turn until it has ended. (Spinning, not
    `asyncio.sleep`: on Windows the loop's clock moves in 15.6 ms steps, and a shorter sleep returns at once.)"""
    end = time.perf_counter() + after_s
    while time.perf_counter() < end and not task.done():  # noqa: ASYNC110 - spinning on purpose (see above)
        await asyncio.sleep(0)
    while not task.done():
        task.cancel()
        await asyncio.sleep(0)


async def assert_writer_free(db: Database) -> None:
    """A fresh write commits, and every connection is back in its pool, within `FREE_WITHIN_S`. (In a live session the
    next job may hold a reader for a moment; a leaked connection never comes back, so this times out.)"""
    async with asyncio.timeout(FREE_WITHIN_S):
        async with db.write() as tx:
            await tx.conn.execute(text("SELECT 1"))
        while db._checked_out():  # noqa: ASYNC110 - the pool has no event to wait on (Database.dispose polls too)
            await asyncio.sleep(0.01)


def park_next_decision(rt: Any) -> asyncio.Event:
    """Hold the fake provider's next Jev request until the returned event is set, so a storm can land while a plan
    waits (design D2). The request is still sent and settles once released."""
    fake = rt.fake
    assert fake is not None, "test mode only"
    ev: asyncio.Event = fake.park_decision(fake.counts["decisions"] + 1)
    return ev


# ── M11 (debate design D2): the two storms every new cancel path gets ──
def park_next_chat(rt: Any, purpose: str) -> asyncio.Event:
    """Hold the fake provider's next chat request labelled `purpose` (a host line, a verdict) until the returned event
    is set, so a storm can land while the call is out."""
    fake = rt.fake
    assert fake is not None, "test mode only"
    ev: asyncio.Event = fake.park_chat(purpose)
    return ev


async def after_storm(api: Any, sid: str) -> None:
    """D2's checks after a storm: the writer is free (a fresh write, every connection back), the clock settles, and the
    served events reduce to the served messages and session."""
    from tests.sessions.kit import assert_reduces

    await assert_writer_free(api.rt.db)
    await api.rt.clock.settle()
    await assert_reduces(api, sid)


async def storm_during_write(api: Any, sid: str, run: Callable[[], Awaitable[Any]], *, storms: int = 20,
                             window_s: float = 0.03, seed: int = 11) -> int:
    """Run `run()` in a task of its own `storms` times, each storm starting at a random point in its first `window_s`
    seconds, so cancels land in its writes (BEGIN, the body, COMMIT). D2's checks follow each storm. Returns how many
    storms ended the task cancelled (a storm that starts after the task finished cuts nothing).

    The first storm starts at once and the last at `window_s`, so both sides are always hit: on the CI runner (23 Oct)
    the asleep-side pause's writes took a few ms, and 20 random starts in 0.25 s all landed after them."""
    rng = random.Random(seed)
    cut = 0
    for i in range(storms):
        task = asyncio.ensure_future(run())
        start = 0.0 if i == 0 else window_s if i == storms - 1 and storms > 1 else rng.uniform(0.0, window_s)
        await storm(task, after_s=start)
        if task.cancelled():
            cut += 1
        elif task.exception() is not None:
            raise task.exception()  # type: ignore[misc]
        await after_storm(api, sid)
    return cut


async def storm_during_call(api: Any, sid: str, task: asyncio.Task[Any], release: asyncio.Event) -> None:
    """`task` waits on a parked call (`park_decision` or `park_next_chat`): storm it, run D2's checks, then release the
    parked request so it settles."""
    assert not task.done(), "the task must still be waiting on its parked call"
    await storm(task)
    await after_storm(api, sid)
    release.set()
    await api.drive(10)
