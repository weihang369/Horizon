"""A write survives any number of cancels (docs/ai/checks/m9.md 9.6, "Stop can break the database writer").

A Stop cancels the task that writes, and the coalescer's timer awaited by a cancelled turn took a second cancel. One
landing in the ROLLBACK left the single writer connection closed ("Connection closed") or open and holding SQLite's
write lock, so the next turn hung or `POST /stop` got "database is locked". These tests cancel a task on every loop
turn until it ends ("a storm"), so cancels land in BEGIN, in COMMIT and in ROLLBACK.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from sqlalchemy import text

from horizon.db.uow import Database
from tests.helpers.storm import storm as _storm

STORMS = 60


async def _db(tmp_path: Path, publish: Any = None) -> Database:
    db = Database(tmp_path / "t.db", publish)
    async with db.write() as tx:
        await tx.conn.execute(text("CREATE TABLE t (x INTEGER)"))
    return db


async def _count(db: Database) -> int:
    async with db.read() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM t"))).scalar_one())


async def test_a_write_cancelled_again_and_again_rolls_back_and_lets_the_writer_go(tmp_path: Path) -> None:
    db = await _db(tmp_path)
    inside = asyncio.Event()

    async def body() -> None:
        async with db.write() as tx:
            await tx.conn.execute(text("INSERT INTO t VALUES (1)"))
            inside.set()
            await asyncio.sleep(30)

    for _ in range(STORMS):
        inside.clear()
        task = asyncio.create_task(body())
        await inside.wait()
        await _storm(task)
        assert task.cancelled()
    async with asyncio.timeout(5):   # the old code hung here, or failed with "Connection closed" / "database is locked"
        async with db.write() as tx:
            await tx.conn.execute(text("INSERT INTO t VALUES (2)"))
    assert await _count(db) == 1
    assert db._checked_out() == 0
    await db.dispose()


async def test_a_cancel_anywhere_in_a_write_publishes_exactly_what_was_committed(tmp_path: Path) -> None:
    """A storm starting anywhere in a short write (≈ 2.5 ms): BEGIN, the body, COMMIT. Events go out if and only if the row
    was stored, and a cancel that lands in the COMMIT still ends the task cancelled."""
    published: list[int] = []
    db = await _db(tmp_path, lambda _c, e: published.append(int(e["n"])))
    rng = random.Random(7)

    async def body(n: int) -> None:
        async with db.write() as tx:
            await tx.conn.execute(text("INSERT INTO t VALUES (:n)"), {"n": n})
            tx.publish("c", {"n": n})

    for n in range(1, 200):
        task = asyncio.create_task(body(n))
        await _storm(task, after_s=rng.uniform(0.0, 0.006))
    async with db.read() as conn:
        stored = sorted(int(x) for x in (await conn.execute(text("SELECT x FROM t"))).scalars())
    assert sorted(published) == stored
    assert 0 < len(stored) < 199   # the storms hit both sides
    assert db._checked_out() == 0
    await db.dispose()


async def test_a_read_cancelled_again_and_again_leaves_no_snapshot_behind(tmp_path: Path) -> None:
    """A reader left open after a cut ROLLBACK keeps its WAL snapshot, and the TRUNCATE checkpoint never succeeds."""
    db = await _db(tmp_path)
    inside = asyncio.Event()

    async def body() -> None:
        async with db.read() as conn:
            await conn.execute(text("SELECT count(*) FROM t"))
            inside.set()
            await asyncio.sleep(30)

    for _ in range(STORMS):
        inside.clear()
        task = asyncio.create_task(body())
        await inside.wait()
        await _storm(task)
    async with db.write() as tx:
        await tx.conn.execute(text("INSERT INTO t VALUES (1)"))
    assert await db.checkpoint_truncate()
    assert db._checked_out() == 0
    await db.dispose()


async def test_a_failing_body_still_rolls_back_when_a_cancel_lands_in_the_rollback(tmp_path: Path) -> None:
    db = await _db(tmp_path)

    async def body() -> None:
        async with db.write() as tx:
            await tx.conn.execute(text("INSERT INTO t VALUES (1)"))
            raise ValueError("boom")

    rng = random.Random(11)
    for _ in range(STORMS):
        task = asyncio.create_task(body())
        await _storm(task, after_s=rng.uniform(0.0, 0.004))
        assert task.cancelled() or isinstance(task.exception(), ValueError)
    assert await _count(db) == 0
    assert db._checked_out() == 0
    await db.dispose()
