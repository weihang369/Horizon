"""`MemoryStore.apply` (doc 02 §3.7; long-term-memory "Memory writes are applied together", "Memory writes are serialised
per character"; knowledge-memory-storage design D17).

`apply(character_id, world_id, ops)`:
1. holds the character's lock for the whole call (OQ-SWE-09: memory writes serialised per character), so two
   sessions writing about one character apply one after the other, in queue order;
2. validates the whole batch first: kinds, non-empty text, importance in [0, 1], every referenced ID belonging to
   this character in this world, and every memory a `Supersede` replaces still being current (a batch written from a
   stale view loses, so two writers can't both replace one memory). One bad op fails the batch with nothing written
   (`MemoryOpError`);
3. embeds the new texts **before** taking the writer lock, for every non-retired space, only with a key; an embedding
   failure leaves the items FTS-only (memory recall is FTS in M5);
4. applies everything in **one** transaction: rows (FTS by trigger), vectors, `superseded_by`, `importance`,
   `last_recalled_at`/`recall_count`; then announces `entity.changed { kind: "memory", id: characterId, worldId }`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

import sqlite_vec
from sqlalchemy import and_, select, text, update

from horizon.ai.ports import Insert, MemoryDraft, MemoryOp, Reinforce, Supersede, Touch
from horizon.db import spaces
from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.events.bus import GLOBAL
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.memory")
KINDS = frozenset({"fact", "event", "preference", "about_user"})
M = t.memory_items.c


class MemoryOpError(ValueError):
    """A batch with an invalid op: nothing was written."""


def _check_unit(x: float, what: str) -> None:
    if not 0.0 <= float(x) <= 1.0:
        raise MemoryOpError(f"{what} must be between 0 and 1")


def _check_draft(d: MemoryDraft) -> None:
    if d.kind not in KINDS:
        raise MemoryOpError(f"unknown memory kind {d.kind!r}")
    if not d.text.strip():
        raise MemoryOpError("a memory needs text")
    _check_unit(d.importance, "importance")


def referenced_ids(ops: Sequence[MemoryOp]) -> set[str]:
    ids: set[str] = set()
    for op in ops:
        if isinstance(op, Supersede):
            ids.update(op.old_ids)
        elif isinstance(op, Reinforce):
            ids.add(op.id)
        elif isinstance(op, Touch):
            ids.update(op.ids)
    return ids


def drafts_of(ops: Sequence[MemoryOp]) -> list[MemoryDraft]:
    return [op.draft for op in ops if isinstance(op, Insert | Supersede)]


class MemoryStore:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, character_id: str) -> asyncio.Lock:
        return self._locks.setdefault(character_id, asyncio.Lock())

    async def apply(self, character_id: str, world_id: str, ops: Sequence[MemoryOp]) -> list[str]:
        """Apply `ops` for one character; returns the IDs of the memories it created, in op order."""
        if not ops:
            return []
        async with self.lock(character_id):
            for op in ops:
                if isinstance(op, Insert | Supersede):
                    _check_draft(op.draft)
                elif isinstance(op, Reinforce):
                    _check_unit(op.importance, "importance")
                elif not isinstance(op, Touch):
                    raise MemoryOpError(f"unknown memory op {type(op).__name__}")
            refs = referenced_ids(ops)
            replaced = {i for op in ops if isinstance(op, Supersede) for i in op.old_ids}
            async with self.rt.db.read() as conn:
                await self._check_refs(conn, character_id, world_id, refs, replaced)
            vectors = await self._embed(character_id, world_id, [d.text for d in drafts_of(ops)])
            return await self._write(character_id, world_id, ops, refs, vectors)

    async def _check_refs(self, conn: object, character_id: str, world_id: str, refs: set[str],
                          replaced: set[str] | None = None) -> None:
        from sqlalchemy.ext.asyncio import AsyncConnection

        assert isinstance(conn, AsyncConnection)
        ch = (await conn.execute(select(t.characters.c.world_id, t.characters.c.deleted_at)
                                 .where(t.characters.c.id == character_id))).first()
        if ch is None or ch[0] != world_id or ch[1] is not None:
            raise MemoryOpError("unknown character for this world")
        if not refs:
            return
        found = set((await conn.execute(select(M.id).where(and_(
            M.id.in_(refs), M.character_id == character_id, M.world_id == world_id)))).scalars())
        missing = refs - found
        if missing:
            raise MemoryOpError(f"memories not found for this character: {sorted(missing)}")
        if replaced:
            stale = set((await conn.execute(select(M.id).where(and_(M.id.in_(replaced), M.superseded_by.is_not(None)))))
                        .scalars())
            if stale:
                raise MemoryOpError(f"memories already superseded: {sorted(stale)}")

    async def _embed(self, character_id: str, world_id: str, texts: list[str]) -> dict[str, list[list[float]]]:
        """Vectors per space for the new texts, computed outside the writer lock (empty without a key or on failure)."""
        rt = self.rt
        if not texts or rt.keys.status() != "set":
            return {}
        async with rt.db.read() as conn:
            targets = await spaces.non_retired(conn)
        embedder = rt.ai.embedder(True)
        ctx = call_ctx("embed_doc", world_id=world_id, character_id=character_id)
        out: dict[str, list[list[float]]] = {}
        for space in targets:
            try:
                async with rt.embed_slots.slot():
                    out[space.id] = (await embedder.embed(texts, kind="document", space=space, ctx=ctx)).vectors
            except ProviderError as e:
                log.info("memories for %s stay keyword-only in %s: embedding failed (%s)", character_id, space.id, e.code)
        return out

    async def _write(self, character_id: str, world_id: str, ops: Sequence[MemoryOp], refs: set[str],
                     vectors: dict[str, list[list[float]]]) -> list[str]:
        rt = self.rt
        now = rt.now_iso()
        created: list[str] = []
        async with rt.db.write() as tx:
            conn = tx.conn
            replaced = {i for op in ops if isinstance(op, Supersede) for i in op.old_ids}
            await self._check_refs(conn, character_id, world_id, refs, replaced)   # still true inside the transaction
            n = 0
            for op in ops:
                if isinstance(op, Insert | Supersede):
                    d = op.draft
                    mid = new_id("mem")
                    res = await conn.execute(t.memory_items.insert().values(
                        id=mid, character_id=character_id, world_id=world_id, kind=d.kind, text=d.text.strip(),
                        importance=float(d.importance), source_session_id=d.source_session_id,
                        source_message_id=d.source_message_id, source_variant_id=d.source_variant_id,
                        source_mode=d.source_mode, about_character_id=d.about_character_id, created_at=now,
                        last_recalled_at=None, recall_count=0, superseded_by=None, is_seed=False))
                    rid = res.inserted_primary_key[0] if res.inserted_primary_key else None
                    for space_id, vecs in vectors.items():
                        mem, _ = spaces.vec_tables(space_id)
                        await conn.execute(text(f"INSERT INTO {mem}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                                           {"r": rid, "c": character_id, "e": sqlite_vec.serialize_float32(vecs[n])})
                    n += 1
                    created.append(mid)
                    if isinstance(op, Supersede):
                        await conn.execute(update(t.memory_items).where(M.id.in_(op.old_ids)).values(superseded_by=mid))
                elif isinstance(op, Reinforce):
                    await conn.execute(update(t.memory_items).where(M.id == op.id).values(importance=float(op.importance)))
                elif isinstance(op, Touch):
                    await conn.execute(update(t.memory_items).where(M.id.in_(op.ids)).values(
                        last_recalled_at=now, recall_count=M.recall_count + 1))
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "memory", "id": character_id, "worldId": world_id})
        return created
