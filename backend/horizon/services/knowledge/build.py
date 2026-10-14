"""The embedding space build (embedding-spaces spec; knowledge-memory-storage design D9; doc 02 §3.9; rag design D4, D5).

`build_space(rt, spec, kinds)` switches the store to a new embedding space (a new model, dimensions or document
template). There is no route or UI: `horizon space build` estimates, asks and calls it (rag D5).

1. **Register** `spec` as `building` (its vec0 tables and delete triggers), or resume a build of the same space.
   From then on every new vector is dual-written: ingestion batches and `MemoryStore.apply` embed for each non-retired
   space (`spaces.non_retired`).
2. **Fill**, for each kind asked (`knowledge`, `memory`; M13 adds messages, rag D27):
   - **Copy what wouldn't change** (doc 10 K3), inside the fill's write transaction, with no request and no ledger
     row: memory vectors when the model and dimensions are the active space's (memories are always plain), and
     knowledge vectors only when the document template is the same too.
   - **Embed the rest** that the active space covers and the building one lacks: the pieces of `indexed` sources
     (under the new space's template, `kind="knowledge"`), and the memories that have a vector in the active space, in
     batches through the embedder with the usual hooks (each batch's vectors are written in its ledger row's
     transaction). Keyword-only sources are left alone: indexing a seed source is the user's explicit, per-source
     choice (D-91), and a build must not spend on it silently.
3. **Catch up.** Fill again until nothing is missing (rows added meanwhile were dual-written, so this only closes the
   gap between a scan and its writes). At most `MAX_PASSES`.
4. **Flip** in one transaction (`spaces.flip`): building → active, active → retired; fully embedded sources move to
   the new space, the rest become keyword-only. `rt.space_id` follows. The next start drops the retired tables, so a
   search that started on the old space finishes on it (rag D12).

A batch in flight at a crash is paid again by the next build (the build is an explicit, rare operation; ingestion's
`embed_sent_at` marker is per source and belongs to its pipeline). A provider error or a cap stops the build with the
space still `building`, so it can be resumed.

`plan_build(rt, spec, kinds)` counts the same work without doing it, for the command's estimate.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sqlite_vec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.embedder import Batch, BatchHooks, PieceMeta, request_text
from horizon.db import spaces
from horizon.db.spaces import SpaceSpec
from horizon.domain.pricing import count_tokens, estimate_embedding
from horizon.events.bus import GLOBAL
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.knowledge")

MAX_PASSES = 3
KINDS = ("knowledge", "memory")


@dataclass
class BuildReport:
    space_id: str
    chunks: int = 0
    memories: int = 0
    passes: int = 0
    copied_chunks: int = 0
    copied_memories: int = 0


@dataclass(frozen=True)
class BuildPlan:
    """What a build would do (rag D5's estimate)."""

    space: SpaceSpec
    active: SpaceSpec
    chunks: int                 # pieces to embed
    memories: int               # memories to embed
    copy_chunks: int            # vectors copied instead
    copy_memories: int
    tokens: int
    cost_usd: float


def copies_memories(active: SpaceSpec, spec: SpaceSpec) -> bool:
    return active.model == spec.model and active.dims == spec.dims


def copies_knowledge(active: SpaceSpec, spec: SpaceSpec) -> bool:
    return copies_memories(active, spec) and (active.doc_template or None) == (spec.doc_template or None)


async def plan_build(rt: Runtime, spec: SpaceSpec, kinds: Sequence[str] = KINDS) -> BuildPlan:
    async with rt.db.read() as conn:
        active = await spaces.active(conn)
        old_mem, _ = spaces.vec_tables(active.id)
        chunk_rows = (await conn.execute(text(
            "SELECT c.rid, c.text, c.heading, c.locator, s.title FROM knowledge_chunks c "
            "JOIN knowledge_sources s ON s.id = c.source_id WHERE s.status = 'indexed'"))).all() \
            if "knowledge" in kinds else []
        memory_rows = (await conn.execute(text(
            f"SELECT m.rid, m.text FROM memory_items m WHERE m.rid IN (SELECT rid FROM {old_mem})"))).all() \
            if "memory" in kinds else []
    copy_k, copy_m = copies_knowledge(active, spec), copies_memories(active, spec)
    tokens = 0
    if not copy_k:
        tokens += sum(count_tokens(request_text(str(r[1]), "knowledge", spec, PieceMeta(str(r[4]), r[2], r[3])))
                      for r in chunk_rows)
    if not copy_m:
        tokens += sum(count_tokens(str(r[1])) for r in memory_rows)
    return BuildPlan(space=spec, active=active, chunks=0 if copy_k else len(chunk_rows),
                     memories=0 if copy_m else len(memory_rows), copy_chunks=len(chunk_rows) if copy_k else 0,
                     copy_memories=len(memory_rows) if copy_m else 0, tokens=tokens,
                     cost_usd=estimate_embedding(rt.prices, tokens))


async def build_space(rt: Runtime, spec: SpaceSpec, kinds: Sequence[str] = KINDS) -> BuildReport:
    if rt.keys.status() != "set":
        raise ProviderError("no_key", "An OpenRouter key is needed to build an embedding space.")
    unknown = set(kinds) - set(KINDS)
    if unknown:
        raise ValueError(f"unknown kinds to fill: {sorted(unknown)}")
    async with rt.db.write() as tx:
        current = await spaces.building(tx.conn)
        if current is None:
            await spaces.create_building(tx.conn, spec, rt.now_iso())
        elif current.id != spec.id:
            raise RuntimeError(f"another embedding space is building: {current.id}")
    report = BuildReport(space_id=spec.id)
    for _ in range(MAX_PASSES):
        report.passes += 1
        chunks, memories = await _fill(rt, spec, kinds, report)
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
    log.info("embedding space %s is active (%d chunks, %d memories embedded; %d and %d copied; %d passes)", spec.id,
             report.chunks, report.memories, report.copied_chunks, report.copied_memories, report.passes)
    return report


async def _statuses(conn: AsyncConnection) -> dict[str, tuple[str, str, str]]:
    rows = (await conn.execute(text("SELECT id, character_id, world_id, status FROM knowledge_sources"))).all()
    return {str(r[0]): (str(r[1]), str(r[2]), str(r[3])) for r in rows}


async def _copy(conn: AsyncConnection, src: str, dst: str) -> int:
    res = await conn.execute(text(f"INSERT INTO {dst}(rid, character_id, embedding) SELECT rid, character_id, embedding "
                                  f"FROM {src} WHERE rid NOT IN (SELECT rid FROM {dst})"))
    return res.rowcount or 0


async def _fill(rt: Runtime, space: SpaceSpec, kinds: Sequence[str], report: BuildReport) -> tuple[int, int]:
    """One pass: copy what wouldn't change, then embed the active space's coverage missing from `space`. Returns
    (chunks, memories) embedded."""
    async with rt.db.write() as tx:
        active = await spaces.active(tx.conn)
        old_mem, old_kno = spaces.vec_tables(active.id)
        mem, kno = spaces.vec_tables(space.id)
        if "memory" in kinds and copies_memories(active, space):
            report.copied_memories += await _copy(tx.conn, old_mem, mem)
        if "knowledge" in kinds and copies_knowledge(active, space):
            report.copied_chunks += await _copy(tx.conn, old_kno, kno)
    async with rt.db.read() as conn:
        chunk_rows = (await conn.execute(text(
            f"SELECT c.rid, c.text, c.character_id, c.world_id, s.is_seed, s.title, c.heading, c.locator "
            f"FROM knowledge_chunks c JOIN knowledge_sources s ON s.id = c.source_id WHERE s.status = 'indexed' "
            f"AND c.rid NOT IN (SELECT rid FROM {kno}) ORDER BY c.character_id, c.rid"))).all() \
            if "knowledge" in kinds else []
        memory_rows = (await conn.execute(text(
            f"SELECT m.rid, m.text, m.character_id, m.world_id, m.is_seed, NULL, NULL, NULL FROM memory_items m "
            f"WHERE m.rid IN (SELECT rid FROM {old_mem}) AND m.rid NOT IN (SELECT rid FROM {mem}) "
            f"ORDER BY m.character_id, m.rid"))).all() if "memory" in kinds else []
    chunks = await _embed_rows(rt, space, kno, "knowledge_chunks", chunk_rows, knowledge=True)
    memories = await _embed_rows(rt, space, mem, "memory_items", memory_rows, knowledge=False)
    return chunks, memories


async def _embed_rows(rt: Runtime, space: SpaceSpec, table: str, source_table: str, rows: Sequence[Any], *,
                      knowledge: bool) -> int:
    groups: dict[tuple[str, str, bool], list[tuple[int, str, PieceMeta | None]]] = {}
    for rid, body, cid, wid, is_seed, title, heading, locator in rows:   # D31: seed text may use the seed store
        meta = PieceMeta(title=str(title), heading=heading, locator=locator) if knowledge else None
        groups.setdefault((str(cid), str(wid), bool(is_seed)), []).append((int(rid), str(body), meta))
    embedder = rt.ai.embedder(True)
    written = 0
    for (cid, wid, seed), items in groups.items():
        rids = [rid for rid, _, _ in items]

        def hooks(batch: Batch, *, _rids: list[int] = rids, _cid: str = cid, _seed: bool = seed) -> BatchHooks:
            async def commit(conn: AsyncConnection, _row_id: str, b: Batch) -> None:
                nonlocal written
                written += await _write(conn, table, source_table, _cid, [_rids[i] for i in b.indices], b.vectors)

            return BatchHooks(before_send=None, commit_with=commit, store_ok=_seed)

        ctx = call_ctx("embed_doc", world_id=wid, character_id=cid)
        bodies = [body for _, body, _ in items]
        async with rt.embed_slots.slot():
            if knowledge:
                out = await embedder.embed(bodies, kind="knowledge", space=space, ctx=ctx, hooks=hooks,
                                           meta=[m for _, _, m in items if m is not None])
            else:
                out = await embedder.embed(bodies, kind="document", space=space, ctx=ctx, hooks=hooks)
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
