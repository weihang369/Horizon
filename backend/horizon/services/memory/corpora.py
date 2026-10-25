"""Recall's two corpora (docs/ai/09 M9; memory design D30; session-recall "Recall stays in its scope").

Both satisfy `horizon.ai.retrieval.Corpus` and are bound by the runtime, never by the AI layer:
- **`SessionLines(session, upto_seq)`:** this session's indexed lines (`message_index`, `message_fts`,
  `message_vec__{space}` partitioned by session) with `seq ≤ upto_seq`, the latest summary's bound at the turn. Every
  query re-checks the session and its world on the joined row.
- **`Overflow(character, exclude_ids)`:** the character's current memories (`memory_fts`, `memory_vec__{space}`
  partitioned by character) minus the ids already in its block, in its world.

`texts` / `vectors` read only rows in scope, so a hit from another session, character or world can't come back even
when its text or vector is identical (NFR-23).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sqlite_vec
from sqlalchemy import text

from horizon.ai.retrieval import Candidate
from horizon.db import spaces

if TYPE_CHECKING:
    from horizon.runtime import Runtime


def _floats(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def _marks(rids: list[int]) -> str:
    return ",".join(str(int(r)) for r in rids)


@dataclass(frozen=True)
class LineRow:
    rid: int
    message_id: str
    seq: int
    text: str
    before: str | None = None      # the indexed line before it ("Name: text"), shown with it (D35)


@dataclass(frozen=True)
class MemoryRowHit:
    rid: int
    id: str
    kind: str
    text: str
    importance: float
    source_mode: str | None
    source_session_id: str | None
    created_at: str
    last_recalled_at: str | None


class SessionLines:
    def __init__(self, rt: Runtime, world_id: str, session_id: str, upto_seq: int, space_id: str) -> None:
        self.rt = rt
        self.world_id = world_id
        self.session_id = session_id
        self.upto_seq = upto_seq
        self.space_id = space_id

    @property
    def _scope(self) -> dict[str, Any]:
        return {"s": self.session_id, "w": self.world_id, "u": self.upto_seq}

    _SCOPE = "JOIN sessions s ON s.id = i.session_id WHERE i.session_id = :s AND s.world_id = :w AND i.seq <= :u"

    async def fts(self, query: str, limit: int) -> list[Candidate]:
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(text(
                "SELECT i.rid FROM message_fts f JOIN message_index i ON i.rid = f.rowid " + self._SCOPE
                + " AND message_fts MATCH :q ORDER BY bm25(message_fts), i.rid LIMIT :n"),
                {"q": query, "n": limit, **self._scope})).all()
        return [Candidate(rid=int(r[0]), rank=i) for i, r in enumerate(rows)]

    async def knn(self, vector: list[float], limit: int) -> list[Candidate]:
        table = spaces.message_vec_table(self.space_id)
        async with self.rt.db.read() as conn:
            try:
                rows = (await conn.execute(text(
                    f"SELECT v.rid, v.embedding FROM {table} v JOIN message_index i ON i.rid = v.rid " + self._SCOPE
                    + " AND v.embedding MATCH :q AND v.session_id = :s AND v.k = :n ORDER BY v.distance"),
                    {"q": sqlite_vec.serialize_float32(vector), "n": limit, **self._scope})).all()
            except Exception:   # the space's tables are gone (retired under us): keywords only
                return []
        return [Candidate(rid=int(r[0]), rank=i, vector=_floats(bytes(r[1]))) for i, r in enumerate(rows)]

    async def vectors(self, rids: list[int]) -> dict[int, list[float]]:
        if not rids:
            return {}
        table = spaces.message_vec_table(self.space_id)
        async with self.rt.db.read() as conn:
            own = {int(r[0]) for r in (await conn.execute(text(
                f"SELECT i.rid FROM message_index i JOIN sessions s ON s.id = i.session_id WHERE i.rid IN "
                f"({_marks(rids)}) AND i.session_id = :s AND s.world_id = :w AND i.seq <= :u"), self._scope)).all()}
            if not own:
                return {}
            sql = " UNION ALL ".join(f"SELECT rid, embedding FROM {table} WHERE rid = {int(r)}" for r in sorted(own))
            try:
                rows = (await conn.execute(text(sql))).all()
            except Exception:
                return {}
        return {int(r): _floats(bytes(b)) for r, b in rows}

    async def texts(self, rids: list[int]) -> dict[int, str]:
        return {r.rid: r.text for r in (await self.rows(rids)).values()}

    async def rows(self, rids: list[int]) -> dict[int, LineRow]:
        """The lines in scope, each with the indexed line before it."""
        if not rids:
            return {}
        async with self.rt.db.read() as conn:
            got = (await conn.execute(text(
                "SELECT i.rid, i.message_id, i.seq, i.text, (SELECT p.text FROM message_index p WHERE "
                "p.session_id = i.session_id AND p.seq < i.seq ORDER BY p.seq DESC LIMIT 1) FROM message_index i "
                f"JOIN sessions s ON s.id = i.session_id WHERE i.rid IN ({_marks(rids)}) AND i.session_id = :s "
                "AND s.world_id = :w AND i.seq <= :u"), self._scope)).all()
        return {int(r[0]): LineRow(rid=int(r[0]), message_id=str(r[1]), seq=int(r[2]), text=str(r[3]),
                                   before=str(r[4]) if r[4] is not None else None) for r in got}


class Overflow:
    def __init__(self, rt: Runtime, world_id: str, character_id: str, exclude_ids: list[str], space_id: str) -> None:
        self.rt = rt
        self.world_id = world_id
        self.character_id = character_id
        self.exclude_ids = list(exclude_ids)
        self.space_id = space_id

    def _scope(self) -> tuple[str, dict[str, Any]]:
        params: dict[str, Any] = {"c": self.character_id, "w": self.world_id}
        names = []
        for i, mid in enumerate(self.exclude_ids):
            params[f"x{i}"] = mid
            names.append(f":x{i}")
        excl = f" AND m.id NOT IN ({','.join(names)})" if names else ""
        return ("m.character_id = :c AND m.world_id = :w AND m.superseded_by IS NULL" + excl), params

    async def fts(self, query: str, limit: int) -> list[Candidate]:
        where, params = self._scope()
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(text(
                f"SELECT m.rid FROM memory_fts f JOIN memory_items m ON m.rid = f.rowid WHERE memory_fts MATCH :q "
                f"AND {where} ORDER BY bm25(memory_fts), m.rid LIMIT :n"), {"q": query, "n": limit, **params})).all()
        return [Candidate(rid=int(r[0]), rank=i) for i, r in enumerate(rows)]

    async def knn(self, vector: list[float], limit: int) -> list[Candidate]:
        mem, _ = spaces.vec_tables(self.space_id)
        where, params = self._scope()
        async with self.rt.db.read() as conn:
            try:
                rows = (await conn.execute(text(
                    f"SELECT v.rid, v.embedding FROM {mem} v JOIN memory_items m ON m.rid = v.rid "
                    f"WHERE v.embedding MATCH :q AND v.character_id = :c AND v.k = :n AND {where} ORDER BY v.distance"),
                    {"q": sqlite_vec.serialize_float32(vector), "n": limit + len(self.exclude_ids), **params})).all()
            except Exception:
                return []
        return [Candidate(rid=int(r[0]), rank=i, vector=_floats(bytes(r[1]))) for i, r in enumerate(rows[:limit])]

    async def vectors(self, rids: list[int]) -> dict[int, list[float]]:
        if not rids:
            return {}
        mem, _ = spaces.vec_tables(self.space_id)
        own = set(await self.rows(rids))
        if not own:
            return {}
        async with self.rt.db.read() as conn:
            sql = " UNION ALL ".join(f"SELECT rid, embedding FROM {mem} WHERE rid = {int(r)}" for r in sorted(own))
            try:
                rows = (await conn.execute(text(sql))).all()
            except Exception:
                return {}
        return {int(r): _floats(bytes(b)) for r, b in rows}

    async def texts(self, rids: list[int]) -> dict[int, str]:
        return {r.rid: r.text for r in (await self.rows(rids)).values()}

    async def rows(self, rids: list[int]) -> dict[int, MemoryRowHit]:
        if not rids:
            return {}
        where, params = self._scope()
        async with self.rt.db.read() as conn:
            got = (await conn.execute(text(
                "SELECT m.rid, m.id, m.kind, m.text, m.importance, m.source_mode, m.source_session_id, m.created_at, "
                f"m.last_recalled_at FROM memory_items m WHERE m.rid IN ({_marks(rids)}) AND {where}"), params)).all()
        return {int(r[0]): MemoryRowHit(rid=int(r[0]), id=str(r[1]), kind=str(r[2]), text=str(r[3]),
                                        importance=float(r[4]), source_mode=r[5], source_session_id=r[6],
                                        created_at=str(r[7]), last_recalled_at=r[8]) for r in got}


async def session_has_lines(rt: Runtime, session_id: str, upto_seq: int | None = None) -> bool:
    async with rt.db.read() as conn:
        row = (await conn.execute(text(
            "SELECT 1 FROM message_index WHERE session_id = :s" + (" AND seq <= :u" if upto_seq is not None else "")
            + " LIMIT 1"), {"s": session_id, "u": upto_seq})).first()
    return row is not None
