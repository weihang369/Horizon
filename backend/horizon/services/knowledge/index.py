"""The scoped retrieval index (retrieval "Retrieval stays in the speaker's scope"; design D10, D13; NFR-23).

Built by the runtime per turn for the **speaker's** world and character; the AI retrievers only ever see this object.
Every query binds the character (the vec0 partition key, and the FTS join back) and re-checks the world and character
on the joined row, so no hit from another character or world can come back even when vectors or text are identical.
Memory queries return current (not superseded) items only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sqlite_vec
from sqlalchemy import and_, select, text

from horizon.ai.contexts import KnowledgeHit, MemoryHit
from horizon.ai.retrieval import Candidate, rank_score
from horizon.db import spaces
from horizon.db import tables as t

if TYPE_CHECKING:
    from horizon.runtime import Runtime


class ScopedIndex:
    def __init__(self, rt: Runtime, world_id: str, character_id: str, active_space: str) -> None:
        self.rt = rt
        self.world_id = world_id
        self.character_id = character_id
        self.active_space = active_space

    @property
    def _scope(self) -> dict[str, Any]:
        return {"w": self.world_id, "c": self.character_id}

    async def knowledge_fts(self, query: str, limit: int) -> list[Candidate]:
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(text(
                "SELECT c.rid FROM knowledge_fts f JOIN knowledge_chunks c ON c.rid = f.rowid "
                "WHERE knowledge_fts MATCH :q AND c.world_id = :w AND c.character_id = :c "
                "ORDER BY bm25(knowledge_fts), c.rid LIMIT :n"), {"q": query, "n": limit, **self._scope})).all()
        return [Candidate(rid=int(r[0]), rank=i) for i, r in enumerate(rows)]

    async def knowledge_knn(self, vector: list[float], limit: int) -> list[Candidate]:
        _, kno = spaces.vec_tables(self.active_space)
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(text(
                f"SELECT v.rid FROM {kno} v JOIN knowledge_chunks c ON c.rid = v.rid "
                "WHERE v.embedding MATCH :q AND v.character_id = :c AND v.k = :n "
                "AND c.world_id = :w AND c.character_id = :c ORDER BY v.distance"),
                {"q": sqlite_vec.serialize_float32(vector), "n": limit, **self._scope})).all()
        return [Candidate(rid=int(r[0]), rank=i) for i, r in enumerate(rows)]

    async def knowledge_hits(self, rids: list[int], scores: dict[int, float]) -> list[KnowledgeHit]:
        if not rids:
            return []
        C, S, X = t.knowledge_chunks.c, t.knowledge_sources.c, t.knowledge_sections.c
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(
                select(C.rid, C.id, C.source_id, C.locator, C.text, S.title, S.type, X.text.label("section_text"))
                .join(t.knowledge_sources, S.id == C.source_id)
                .join(t.knowledge_sections, X.id == C.section_id)
                .where(and_(C.rid.in_(rids), C.world_id == self.world_id, C.character_id == self.character_id,
                            S.world_id == self.world_id, S.character_id == self.character_id)))).mappings().all()
        by_rid = {int(r["rid"]): r for r in rows}
        return [KnowledgeHit(chunk_id=r["id"], source_id=r["source_id"], title=r["title"], type=r["type"],
                             locator=r["locator"], text=r["text"], section_text=r["section_text"],
                             score=float(scores.get(rid, 0.5)))
                for rid in rids if (r := by_rid.get(rid)) is not None]

    async def memory_fts(self, query: str, limit: int) -> list[MemoryHit]:
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(text(
                "SELECT m.id, m.kind, m.text, m.source_session_id FROM memory_fts f JOIN memory_items m ON m.rid = f.rowid "
                "WHERE memory_fts MATCH :q AND m.world_id = :w AND m.character_id = :c AND m.superseded_by IS NULL "
                "ORDER BY bm25(memory_fts), m.rid LIMIT :n"), {"q": query, "n": limit, **self._scope})).all()
        return [MemoryHit(id=r[0], kind=r[1], text=r[2], source_session_id=r[3], score=rank_score(i))
                for i, r in enumerate(rows)]

    async def memory_recent(self, limit: int) -> list[MemoryHit]:
        M = t.memory_items.c
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(select(M.id, M.kind, M.text, M.source_session_id).where(and_(
                M.world_id == self.world_id, M.character_id == self.character_id, M.superseded_by.is_(None)))
                .order_by(M.created_at.desc(), M.id).limit(limit))).all()
        return [MemoryHit(id=r[0], kind=r[1], text=r[2], source_session_id=r[3], score=rank_score(i))
                for i, r in enumerate(rows)]


async def has_vectors(rt: Runtime, character_ids: list[str]) -> bool:
    """Whether any of these characters has a source indexed in the active space (the query-embedding gate, D12)."""
    if not character_ids:
        return False
    S = t.knowledge_sources.c
    async with rt.db.read() as conn:
        row = (await conn.execute(select(S.id).where(and_(
            S.character_id.in_(character_ids), S.status == "indexed",
            S.embedding_space_id == rt.space_id)).limit(1))).first()
    return row is not None
