"""Unit of work (doc 01 §3, §4.1).

`async with db.write() as tx:` takes the process-wide writer lock, opens a `BEGIN IMMEDIATE` transaction and
collects events with `tx.publish(channel, event)`. Events reach the EventBus only after a successful commit;
a rollback drops them. The writer lock is never held across a network await.

`async with db.read() as conn:` opens a short deferred read transaction on the reader pool.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db.engines import make_engines

Publish = Callable[[str, dict[str, Any]], None]


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

    def set_publisher(self, publish: Publish | None) -> None:
        self._publish = publish

    @asynccontextmanager
    async def write(self) -> AsyncIterator[WriteTx]:
        async with self.write_lock:
            async with self.writer.begin() as conn:
                tx = WriteTx(conn)
                yield tx
        if self._publish:
            for channel, event in tx.events:
                self._publish(channel, event)

    @asynccontextmanager
    async def read(self) -> AsyncIterator[AsyncConnection]:
        async with self.reader.connect() as conn, conn.begin():
            yield conn

    async def dispose(self) -> None:
        await self.writer.dispose()
        await self.reader.dispose()
