"""Cancel storms (docs/ai/checks/m9.md 9.6, "Stop can break the database writer"; group-watch design D2).

A storm cancels a task on every loop turn until it ends, so cancels land in BEGIN, in COMMIT, in ROLLBACK and in any
wait in between. Every new M10 cancel path is stormed twice: once while it writes and once while its plan waits on a
parked Jev answer. Afterwards the writer must be free.
"""

from __future__ import annotations

import asyncio
import time
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
