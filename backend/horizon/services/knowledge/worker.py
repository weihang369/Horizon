"""The ingestion worker (knowledge-memory-storage design D1, D18).

One `rt.spawn` task per source (`ingest:{sourceId}`), running `Pipeline.run(start)`. Stages are gated by the runtime's
activity-aware slots (`docling_slots` 1, `embed_slots` 2, doc 01 §4.4), so a virtual-time advance settles them and a
second PDF waits its turn. The `knowledge_sources` row is the durable record; this class only tracks live tasks.

- `submit(id, start)`: start (or keep) a source's task. A source already running is not started twice.
- `cancel(id)`: cancel and wait. A conversion process is killed by the converter; an embedding call already sent
  finishes shielded and is recorded at its real cost (D-86), with no vectors when the source is gone.
- `cancel_for(character_id=… | world_id=…)`: before a character or world delete, or a demo reset.
- `stop()`: cancel everything (shutdown, factory reset).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from horizon.services.knowledge.pipeline import Pipeline, Stage

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.knowledge")


@dataclass
class _Live:
    task: asyncio.Task[None]
    character_id: str | None
    world_id: str | None


class IngestionWorker:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.live: dict[str, _Live] = {}
        self.submitted: list[str] = []   # every submission, in order (tests)
        self.stopped = False

    def running(self, source_id: str) -> bool:
        live = self.live.get(source_id)
        return live is not None and not live.task.done()

    def submit(self, source_id: str, start: Stage = "extract", *, character_id: str | None = None,
               world_id: str | None = None) -> None:
        if self.stopped or self.running(source_id):
            return
        self.submitted.append(source_id)
        task = self.rt.spawn(f"ingest:{source_id}", self._run(source_id, start))
        self.live[source_id] = _Live(task, character_id, world_id)
        task.add_done_callback(functools.partial(self._done, source_id))

    def _done(self, source_id: str, task: asyncio.Task[None]) -> None:
        live = self.live.get(source_id)
        if live is not None and live.task is task:
            del self.live[source_id]

    async def _run(self, source_id: str, start: Stage) -> None:
        try:
            await Pipeline(self.rt, source_id).run(start)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("indexing source %s failed unexpectedly", source_id)
            with contextlib.suppress(Exception):
                await _mark_failed(self.rt, source_id)

    async def cancel(self, source_id: str) -> None:
        live = self.live.pop(source_id, None)
        if live is None or live.task.done():
            return
        live.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await live.task

    async def cancel_for(self, *, character_id: str | None = None, world_id: str | None = None,
                         source_ids: list[str] | None = None) -> None:
        """Cancel the live tasks of the given sources, or of every source whose row is in this character or world."""
        ids = set(source_ids or [])
        if character_id or world_id:
            from sqlalchemy import or_, select

            from horizon.db import tables as t

            S = t.knowledge_sources.c
            cond = []
            if character_id:
                cond.append(S.character_id == character_id)
            if world_id:
                cond.append(S.world_id == world_id)
            async with self.rt.db.read() as conn:
                ids |= set((await conn.execute(select(S.id).where(or_(*cond)))).scalars())
        for sid in [s for s in list(self.live) if s in ids]:
            await self.cancel(sid)

    async def stop(self) -> None:
        self.stopped = True
        for sid in list(self.live):
            await self.cancel(sid)


async def _mark_failed(rt: Runtime, source_id: str) -> None:
    from sqlalchemy import update

    from horizon.db import tables as t
    from horizon.events.bus import GLOBAL

    S = t.knowledge_sources.c
    async with rt.db.write() as tx:
        res = await tx.conn.execute(update(t.knowledge_sources).where(S.id == source_id).values(
            status="failed", error={"message": "Something went wrong while reading this source. Retry to try again."}))
        if res.rowcount:
            row = (await tx.conn.execute(t.knowledge_sources.select().where(S.id == source_id))).mappings().first()
            if row is not None:
                tx.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": source_id,
                                    "worldId": row["world_id"]})
