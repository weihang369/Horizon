"""The AI purge worker (doc 01 §4.6, ai-ports "Purge hooks are delivered at least once", design D14).

After a deletion commits, its transaction has queued an `ai_purge_queue` row (scope + ids). This worker calls
`hooks.on_delete(scope, ids)` for each pending row and marks `done_at`; a failure counts an attempt and retries after a
backoff (an injected sleeper, like the cost corrector, never the clock). It wakes on `notify()` after an insert and
drains every pending row at startup, so an entry left by a crash is delivered after the restart.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select, update

from horizon.ai.hooks import AiStateHooks
from horizon.db import tables as t
from horizon.db.uow import Database

log = logging.getLogger("horizon.purge")

BACKOFF_S = (1.0, 5.0, 30.0, 120.0, 600.0)
Sleeper = Callable[[float], Awaitable[None]]
Q = t.ai_purge_queue.c


class PurgeWorker:
    def __init__(self, db: Database, hooks: AiStateHooks, now_iso: Callable[[], str], *,
                 sleeper: Sleeper = asyncio.sleep) -> None:
        self.db = db
        self.hooks = hooks
        self.now_iso = now_iso
        self.sleeper = sleeper
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.idle = asyncio.Event()

    def start(self) -> None:
        self._wake.set()  # startup: drain whatever a crash left behind
        self._task = asyncio.get_running_loop().create_task(self._run(), name="purge")

    def notify(self) -> None:
        self._wake.set()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _pending(self) -> list[tuple[int, str, Any, int]]:
        async with self.db.read() as conn:
            rows = (await conn.execute(select(Q.id, Q.scope, Q.ids, Q.attempts).where(Q.done_at.is_(None))
                                       .order_by(Q.id))).all()
        return [(int(r[0]), str(r[1]), r[2], int(r[3])) for r in rows]

    async def _deliver(self, scope: str, ids: Any) -> None:
        """A memory Forget carries `{memoryItemIds, characterId, messageIds}` and goes to `on_forget` (M5 design D16);
        every other scope carries a list of IDs and goes to `on_delete`."""
        if scope == "memory" and isinstance(ids, dict):
            await self.hooks.on_forget(list(ids.get("memoryItemIds") or []), str(ids.get("characterId") or ""),
                                       list(ids.get("messageIds") or []))
            return
        await self.hooks.on_delete(scope, list(ids or []))

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            self.idle.clear()
            failed = False
            for row_id, scope, ids, attempts in await self._pending():
                try:
                    await self._deliver(scope, ids)
                except Exception:
                    log.exception("purge hook failed for %s %s (attempt %d)", scope, ids, attempts + 1)
                    async with self.db.write() as tx:
                        await tx.conn.execute(update(t.ai_purge_queue).where(Q.id == row_id).values(attempts=attempts + 1))
                    failed = True
                    await self.sleeper(BACKOFF_S[min(attempts, len(BACKOFF_S) - 1)])
                    continue
                async with self.db.write() as tx:
                    await tx.conn.execute(update(t.ai_purge_queue).where(Q.id == row_id).values(done_at=self.now_iso()))
            if failed:
                self._wake.set()  # retry the failures on the next pass
            else:
                self.idle.set()
