"""Retrieval isolation (NFR-23; knowledge-memory-storage task 7.7; retrieval "Identical knowledge in two worlds").

World B is Meridian's twin (same characters, memories and knowledge text, different ids; `test_isolation._build_twin`).
Both worlds' chunks and memories also get **identical vectors** (a hash of the text), so a vector search alone could
not tell them apart. FTS retrieval, vector KNN retrieval and memory recall for a character in world A must return only
A's rows, through the retrievers and through a full scripted turn.
"""

from __future__ import annotations

import hashlib
import struct

import sqlite_vec
from sqlalchemy import text

from horizon.ai.retrieval import (
    NaiveKnowledgeRetriever,
    NaiveMemoryRetriever,
    QueryBundle,
    ScriptedKnowledgeRetriever,
    ScriptedMemoryRetriever,
)
from horizon.db import spaces
from horizon.services.knowledge.index import ScopedIndex
from tests.conftest import Api
from tests.isolation.test_isolation import A, B, _build_twin
from tests.knowledge.kit import RecordingEngine, owners
from tests.sessions.kit import command, create

AMARA, TWIN = "chr_seedAmara", "chr_twinseedAmara"
DIMS = 1024


def vec(s: str) -> list[float]:
    """A deterministic unit vector from the text (identical text → identical vector, in either world)."""
    raw = b"".join(hashlib.sha256(f"{s}:{i}".encode()).digest() for i in range(DIMS * 4 // 32))
    xs = [v / 2**31 - 1.0 for v in struct.unpack(f"<{DIMS}I", raw)]
    norm = sum(x * x for x in xs) ** 0.5
    return [x / norm for x in xs]


async def _twin_with_vectors(api: Api) -> None:
    await _build_twin(api)
    mem, kno = spaces.vec_tables(api.rt.space_id or "")
    async with api.rt.db.write() as tx:
        for table, src in ((kno, "knowledge_chunks"), (mem, "memory_items")):
            rows = (await tx.conn.execute(text(f"SELECT rid, character_id, text FROM {src} "
                                               "WHERE character_id IN (:a, :b)"), {"a": AMARA, "b": TWIN})).all()
            for rid, cid, body in rows:
                await tx.conn.execute(text(f"INSERT INTO {table}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                                      {"r": rid, "c": cid, "e": sqlite_vec.serialize_float32(vec(body))})


async def _a_chunk(api: Api) -> str:
    async with api.rt.db.read() as conn:
        return str((await conn.execute(text("SELECT text FROM knowledge_chunks WHERE character_id = :c "
                                            "AND text LIKE '%triage%' ORDER BY rid LIMIT 1"), {"c": AMARA})).scalar_one())


async def test_identical_vectors_and_text_stay_in_their_world(api: Api) -> None:
    await _twin_with_vectors(api)
    target = await _a_chunk(api)
    space = api.rt.space_id or ""
    q = QueryBundle(text=target[:200], vectors={space: vec(target)})
    for world, cid, mine in ((A, AMARA, lambda i: "_twin" not in i), (B, TWIN, lambda i: "_twin" in i)):
        idx = ScopedIndex(api.rt, world, cid, space)
        knn = await idx.knowledge_knn(vec(target), 20)
        hits = await idx.knowledge_hits([c.rid for c in knn], {})
        assert hits and all(mine(h.chunk_id) and mine(h.source_id) for h in hits)
        for retriever in (NaiveKnowledgeRetriever(), ScriptedKnowledgeRetriever()):
            got = await retriever.retrieve(idx, q, 5)
            assert got and all(mine(h.chunk_id) for h in got)
            assert await owners(api, [h.source_id for h in got], "knowledge_sources") == {(world, cid)}
        for mret in (NaiveMemoryRetriever(), ScriptedMemoryRetriever()):
            ms = await mret.recall(idx, QueryBundle("Kai coffee headaches"), 3)
            assert ms and all(mine(m.id) for m in ms)
            assert await owners(api, [m.id for m in ms], "memory_items") == {(world, cid)}
    # The world and the character are re-bound on every join back: a mismatched pair finds nothing.
    cross = ScopedIndex(api.rt, A, TWIN, space)
    assert await cross.knowledge_knn(vec(target), 20) == []
    assert await cross.knowledge_fts('"triage"', 20) == []
    assert await cross.memory_fts('"kai"', 3) == [] and await cross.memory_recent(3) == []


async def test_a_full_turn_in_world_a_sees_only_world_a(api: Api) -> None:
    await _twin_with_vectors(api)
    await api.set_key()
    r = await api.post("/api/v1/_test/ai-profile", {"profile": "scripted",
                                                     "overrides": {"knowledge_retriever": "naive", "embedder": "naive"}})
    assert r.status_code == 204
    eng = RecordingEngine(api)
    api.rt.ai.override("turn", eng)
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "What do the triage guidelines say about headaches? Remember Kai?"})
    await api.drive(10000)
    ctx = eng.seen[-1]
    assert ctx.knowledge and ctx.memory
    assert all("_twin" not in h.chunk_id for h in ctx.knowledge) and all("_twin" not in m.id for m in ctx.memory)
    assert await owners(api, [h.source_id for h in ctx.knowledge], "knowledge_sources") == {(A, AMARA)}
    assert await owners(api, [m.id for m in ctx.memory], "memory_items") == {(A, AMARA)}
