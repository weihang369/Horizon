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

from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.pool import QueuePool

from horizon.db.engines import make_engines

Publish = Callable[[str, dict[str, Any]], None]

log = logging.getLogger("horizon.db")
DISPOSE_WAIT_S = 5.0


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
        self._check_open()
        async with self.write_lock:
            async with self.writer.begin() as conn:
                tx = WriteTx(conn)
                yield tx
        if self._publish:
            for channel, event in tx.events:
                self._publish(channel, event)

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
        async with self.reader.connect() as conn, conn.begin():
            yield conn

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
