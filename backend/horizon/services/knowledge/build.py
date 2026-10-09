"""The embedding space build (embedding-spaces spec; knowledge-memory-storage design D9; doc 02 §3.9).

`build_space(rt, spec)` switches the store to a new embedding space (a new model or dimensions). There is no route or
UI: the AI stage calls it when it picks the final model.

1. **Register** `spec` as `building` (its vec0 tables and delete triggers), or resume a build of the same space.
   From then on every new vector is dual-written: ingestion batches and `MemoryStore.apply` embed for each non-retired
   space (`spaces.non_retired`).
2. **Fill.** Embed what the active space covers and the building one lacks: the chunks of `indexed` sources, and the
   memories that have a vector in the active space, in batches through the embedder with the usual hooks (each
   batch's vectors are written in its ledger row's transaction). Keyword-only sources are left alone: indexing a seed
   source is the user's explicit, per-source choice (D-91), and a build must not spend on it silently.
3. **Catch up.** Fill again until nothing is missing (rows added meanwhile were dual-written, so this only closes the
   gap between a scan and its writes). At most `MAX_PASSES`.
4. **Flip** in one transaction (`spaces.flip`): building → active, active → retired; fully embedded sources move to
   the new space, the rest become keyword-only. `rt.space_id` follows. The next start drops the retired tables.

A batch in flight at a crash is paid again by the next build (the build is an explicit, rare operation; ingestion's
`embed_sent_at` marker is per source and belongs to its pipeline). A provider error or a cap stops the build with the
space still `building`, so it can be resumed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sqlite_vec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.embedder import Batch, BatchHooks
from horizon.db import spaces
from horizon.db.spaces import SpaceSpec
from horizon.events.bus import GLOBAL
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.knowledge")

MAX_PASSES = 3


@dataclass
class BuildReport:
    space_id: str
    chunks: int = 0
    memories: int = 0
    passes: int = 0


async def build_space(rt: Runtime, spec: SpaceSpec) -> BuildReport:
    if rt.keys.status() != "set":
        raise ProviderError("no_key", "An OpenRouter key is needed to build an embedding space.")
    async with rt.db.write() as tx:
        current = await spaces.building(tx.conn)
        if current is None:
            await spaces.create_building(tx.conn, spec, rt.now_iso())
        elif current.id != spec.id:
            raise RuntimeError(f"another embedding space is building: {current.id}")
    report = BuildReport(space_id=spec.id)
    for _ in range(MAX_PASSES):
        report.passes += 1
        chunks, memories = await _fill(rt, spec)
        report.chunks += chunks
        report.memories += memories
        if chunks == 0 and memories == 0:
            break
    async with rt.db.write() as tx:
        before = await _statuses(tx.conn)
        await spaces.flip(tx.conn, spec.id)
        after = await _statuses(tx.conn)
    rt.space_id = spec.id
    for sid, (_cid, wid, status) in after.items():
        if before.get(sid, (_cid, wid, status))[2] != status:
            rt.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": sid, "worldId": wid})
    log.info("embedding space %s is active (%d chunks, %d memories embedded in %d passes)", spec.id, report.chunks,
             report.memories, report.passes)
    return report


async def _statuses(conn: AsyncConnection) -> dict[str, tuple[str, str, str]]:
    rows = (await conn.execute(text("SELECT id, character_id, world_id, status FROM knowledge_sources"))).all()
    return {str(r[0]): (str(r[1]), str(r[2]), str(r[3])) for r in rows}


async def _fill(rt: Runtime, space: SpaceSpec) -> tuple[int, int]:
    """One pass: embed the active space's coverage missing from `space`. Returns (chunks, memories) embedded."""
    async with rt.db.read() as conn:
        active = await spaces.active(conn)
        old_mem, _ = spaces.vec_tables(active.id)
        mem, kno = spaces.vec_tables(space.id)
        chunk_rows = (await conn.execute(text(
            f"SELECT c.rid, c.text, c.character_id, c.world_id FROM knowledge_chunks c "
            f"JOIN knowledge_sources s ON s.id = c.source_id WHERE s.status = 'indexed' "
            f"AND c.rid NOT IN (SELECT rid FROM {kno}) ORDER BY c.character_id, c.rid"))).all()
        memory_rows = (await conn.execute(text(
            f"SELECT m.rid, m.text, m.character_id, m.world_id FROM memory_items m "
            f"WHERE m.rid IN (SELECT rid FROM {old_mem}) AND m.rid NOT IN (SELECT rid FROM {mem}) "
            f"ORDER BY m.character_id, m.rid"))).all()
    chunks = await _embed_rows(rt, space, kno, "knowledge_chunks", chunk_rows)
    memories = await _embed_rows(rt, space, mem, "memory_items", memory_rows)
    return chunks, memories


async def _embed_rows(rt: Runtime, space: SpaceSpec, table: str, source_table: str, rows: Sequence[Any]) -> int:
    groups: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for rid, body, cid, wid in rows:
        groups.setdefault((str(cid), str(wid)), []).append((int(rid), str(body)))
    embedder = rt.ai.embedder(True)
    written = 0
    for (cid, wid), items in groups.items():
        rids = [rid for rid, _ in items]

        def hooks(batch: Batch, *, _rids: list[int] = rids, _cid: str = cid) -> BatchHooks:
            async def commit(conn: AsyncConnection, _row_id: str, b: Batch) -> None:
                nonlocal written
                written += await _write(conn, table, source_table, _cid, [_rids[i] for i in b.indices], b.vectors)

            return BatchHooks(before_send=None, commit_with=commit)

        ctx = call_ctx("embed_doc", world_id=wid, character_id=cid)
        async with rt.embed_slots.slot():
            out = await embedder.embed([body for _, body in items], kind="document", space=space, ctx=ctx, hooks=hooks)
        if out.cached:
            async with rt.db.write() as tx:
                written += await _write(tx.conn, table, source_table, cid, [rids[i] for i in out.cached],
                                        [out.vectors[i] for i in out.cached])
    return written


async def _write(conn: AsyncConnection, table: str, source_table: str, character_id: str, rids: list[int],
                 vectors: list[list[float]]) -> int:
    """Write the vectors of rows that still exist (a row deleted while its batch was in flight gets none)."""
    if not rids:
        return 0
    marks = ", ".join(str(int(r)) for r in rids)
    alive = {int(r[0]) for r in (await conn.execute(text(f"SELECT rid FROM {source_table} WHERE rid IN ({marks})"))).all()}
    n = 0
    for rid, vec in zip(rids, vectors, strict=True):
        if rid not in alive:
            continue
        await conn.execute(text(f"DELETE FROM {table} WHERE rid = :r"), {"r": rid})
        await conn.execute(text(f"INSERT INTO {table}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                           {"r": rid, "c": character_id, "e": sqlite_vec.serialize_float32(vec)})
        n += 1
    return n
