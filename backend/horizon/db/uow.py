"""Unit of work (doc 01 §3, §4.1).

`async with db.write() as tx:` takes the process-wide writer lock, opens a `BEGIN IMMEDIATE` transaction and
collects events with `tx.publish(channel, event)`. Events reach the EventBus only after a successful commit;
a rollback drops them. The writer lock is never held across a network await.

`async with db.read() as conn:` opens a short deferred read transaction on the reader pool.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.pool import QueuePool

from horizon.db.engines import make_engines
from horizon.domain import vclock

Publish = Callable[[str, dict[str, Any]], None]

log = logging.getLogger("horizon.db")
DISPOSE_WAIT_S = 5.0


@dataclass
class _Ended:
    committed: bool = False
    cut: bool = False   # a cancel landed during the COMMIT: the caller re-raises it after its own step


@asynccontextmanager
async def _transaction(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncConnection, _Ended]]:
    """`engine.begin()`, with its BEGIN and its end (COMMIT or ROLLBACK, then the connection back to the pool) each run
    to the end by `vclock.to_the_end`. A Stop cancels the task that writes, and the coalescer's timer awaited by a
    cancelled turn takes a second cancel; one landing in a ROLLBACK left the single writer connection closed, or open
    and holding SQLite's write lock, so the next turn hung or got "database is locked" (docs/ai/checks/m9.md 9.6)."""
    cm = engine.begin()
    begun, cut = await vclock.to_the_end(cm.__aenter__(), "db-begin")
    if cut:
        if begun.exception() is None:
            await _end_with(cm, asyncio.CancelledError())   # BEGIN went through: roll it back before letting go
        raise asyncio.CancelledError
    conn = begun.result()
    ended = _Ended()
    try:
        yield conn, ended
    except BaseException as e:
        if await _end_with(cm, e) and not isinstance(e, asyncio.CancelledError):
            raise asyncio.CancelledError from e
        raise
    done, ended.cut = await vclock.to_the_end(cm.__aexit__(None, None, None), "db-commit")
    failed = done.exception()
    if failed is not None:   # the COMMIT failed (its rollback has run): the caller sees that, or the cancel
        if ended.cut:
            raise asyncio.CancelledError from failed
        raise failed
    ended.committed = True


async def _end_with(cm: Any, exc: BaseException) -> bool:
    """Roll back after `exc` and return the connection; True when a cancel landed meanwhile."""
    done, cut = await vclock.to_the_end(cm.__aexit__(type(exc), exc, exc.__traceback__), "db-rollback")
    failed = done.exception()
    if failed is not None and failed is not exc:
        log.warning("rollback after %s failed", type(exc).__name__, exc_info=failed)
    return cut


@dataclass
class WriteTx:
    conn: AsyncConnection
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        self.events.append((channel, event))


class Database:
    def __init__(self, db_path: Path, publish: Publish | None = None) -> None:
        self.path = db_path
        self.writer, self.reader = make_engines(db_path)
        self.write_lock = asyncio.Lock()
        self._publish = publish
        self._closed = False

    def set_publisher(self, publish: Publish | None) -> None:
        self._publish = publish

    @asynccontextmanager
    async def write(self) -> AsyncIterator[WriteTx]:
        """The body can be cancelled like any await; BEGIN, COMMIT or ROLLBACK and the connection's return can't, so
        the writer lock is let go only once the one writer connection is back in the pool, clean. A cancel that lands
        during the COMMIT is re-raised after it, and the committed events are still published."""
        self._check_open()
        async with self.write_lock:
            async with _transaction(self.writer) as (conn, ended):
                tx = WriteTx(conn)
                yield tx
            committed = ended.committed
        if committed and self._publish:
            for channel, event in tx.events:
                self._publish(channel, event)
        if ended.cut:
            raise asyncio.CancelledError

    async def checkpoint_truncate(self, *, attempts: int = 5, delay_s: float = 0.1) -> bool:
        """`PRAGMA wal_checkpoint(TRUNCATE)` outside any transaction, on the writer connection (M5 design D16): copy every
        WAL frame home and truncate the WAL to 0 bytes, so a forgotten memory's old pages leave the file. A reader holding
        an old snapshot makes it busy; it is retried, and False means a later checkpoint will finish the job."""
        self._check_open()
        for i in range(attempts):
            async with self.write_lock, self.writer.connect() as conn:
                raw = await conn.get_raw_connection()
                driver: Any = raw.driver_connection
                cur = await driver.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                row = await cur.fetchone()
                await cur.close()
            if row is not None and int(row[0]) == 0:
                return True
            if i < attempts - 1:
                await asyncio.sleep(delay_s)
        return False

    @asynccontextmanager
    async def read(self) -> AsyncIterator[AsyncConnection]:
        self._check_open()
        async with _transaction(self.reader) as (conn, ended):
            yield conn
        if ended.cut:
            raise asyncio.CancelledError

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError("database is closed")

    async def dispose(self) -> None:
        """Close every pooled connection. Later reads and writes raise instead of reopening the file, and one already
        under way gets DISPOSE_WAIT_S to finish first: `engine.dispose()` cannot close a checked-out connection, which
        then goes back to the detached pool and holds `horizon.db` open (a factory reset's wipe fails on Windows)."""
        self._closed = True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + DISPOSE_WAIT_S
        while self._checked_out():
            if loop.time() >= deadline:
                log.warning("disposing the database with connections still checked out")
                break
            await asyncio.sleep(0.01)
        await self.writer.dispose()
        await self.reader.dispose()

    def _checked_out(self) -> int:
        return sum(cast(QueuePool, e.pool).checkedout() for e in (self.writer, self.reader))
