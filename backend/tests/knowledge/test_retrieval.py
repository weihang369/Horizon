"""Retrieval policy and the scoped index (knowledge-memory-storage tasks 7.1–7.2; retrieval "User text cannot change the
keyword query", "Knowledge retrieval", "Memory recall")."""

from __future__ import annotations

import sqlite_vec
from sqlalchemy import text

from horizon.ai.ports import Insert, MemoryDraft, Supersede
from horizon.ai.retrieval import (
    NaiveKnowledgeRetriever,
    NaiveMemoryRetriever,
    QueryBundle,
    ScriptedKnowledgeRetriever,
    ScriptedMemoryRetriever,
    fts_query,
)
from horizon.db import spaces
from horizon.services.knowledge.index import ScopedIndex, has_vectors
from tests.conftest import Api

MERIDIAN = "wld_seedMeridian"
AMARA = "chr_seedAmara"


def index(api: Api, character: str = AMARA, world: str = MERIDIAN) -> ScopedIndex:
    return ScopedIndex(api.rt, world, character, api.rt.space_id or "")


def test_query_builder_ignores_syntax() -> None:
    q = fts_query('"burnout" NEAR(review -triage) text: OR AND (')
    assert q == '"burnout" OR "review" OR "triage" OR "text"'
    assert fts_query("   ?!  ... ") is None and fts_query("a") is None
    assert fts_query("Café crème brûlée") == '"café" OR "crème" OR "brûlée"'
    many = fts_query(" ".join(f"word{i}" for i in range(40)))
    assert many is not None and many.count(" OR ") == 15


async def test_syntax_heavy_text_runs_against_fts(api: Api) -> None:
    q = fts_query('"burnout" NEAR(review -triage) text: OR AND (')
    assert q is not None
    hits = await index(api).knowledge_fts(q, 5)          # no FTS syntax error
    assert hits


async def test_keyword_only_seed_knowledge_is_found(api: Api) -> None:
    hits = await ScriptedKnowledgeRetriever().retrieve(index(api), QueryBundle("What does the review say about burnout?"), 5)
    assert hits and len(hits) <= 5
    assert all(0 <= h.score <= 1 for h in hits)
    assert any("burnout" in h.text.lower() for h in hits)
    assert all(h.source_id.startswith("kno_") and h.title and h.section_text for h in hits)


async def test_meaning_match_through_vectors(api: Api) -> None:
    _, kno = spaces.vec_tables(api.rt.space_id or "")
    async with api.rt.db.write() as tx:
        rows = (await tx.conn.execute(text("SELECT rid, id FROM knowledge_chunks WHERE character_id = :c ORDER BY rid"),
                                      {"c": AMARA})).all()
        target_rid, target_id = int(rows[-1][0]), str(rows[-1][1])
        for i, (rid, _) in enumerate(rows):
            vec = [0.0] * 1024
            vec[0 if int(rid) == target_rid else 1 + (i % 1000)] = 1.0
            await tx.conn.execute(text(f"INSERT INTO {kno}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                                  {"r": rid, "c": AMARA, "e": sqlite_vec.serialize_float32(vec)})
    query = [1.0] + [0.0] * 1023
    hits = await NaiveKnowledgeRetriever().retrieve(index(api), QueryBundle("zzqx vvwy", {api.rt.space_id or "": query}), 5)
    assert hits[0].chunk_id == target_id and 0 < hits[0].score <= 1
    assert await ScriptedKnowledgeRetriever().retrieve(index(api), QueryBundle("zzqx vvwy"), 5) == []


async def test_rrf_score_is_one_when_first_in_both_lists(api: Api) -> None:
    _, kno = spaces.vec_tables(api.rt.space_id or "")
    first = (await index(api).knowledge_fts('"burnout"', 1))[0]
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text(f"INSERT INTO {kno}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                              {"r": first.rid, "c": AMARA, "e": sqlite_vec.serialize_float32([1.0] + [0.0] * 1023)})
    hits = await NaiveKnowledgeRetriever().retrieve(
        index(api), QueryBundle("burnout", {api.rt.space_id or "": [1.0] + [0.0] * 1023}), 3)
    assert hits[0].score == 1.0


async def test_superseded_memory_is_never_recalled(api: Api) -> None:
    [a] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft("fact", "Amara drinks kombucha daily.", 0.5))])
    [b] = await api.rt.memory.apply(AMARA, MERIDIAN, [Supersede([a], MemoryDraft("fact", "Amara quit tea entirely.", 0.6))])
    naive = await NaiveMemoryRetriever().recall(index(api), QueryBundle("kombucha daily"), 3)
    assert all(m.id != a for m in naive)
    recent = await ScriptedMemoryRetriever().recall(index(api), QueryBundle(""), 3)
    assert recent[0].id == b and all(m.id != a for m in recent) and len(recent) <= 3


async def test_vector_gate_follows_indexed_sources(api: Api) -> None:
    assert not await has_vectors(api.rt, [AMARA])
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE knowledge_sources SET status = 'indexed', embedding_space_id = :s "
                                   "WHERE character_id = :c AND status = 'keyword_only'"), {"s": api.rt.space_id, "c": AMARA})
    assert await has_vectors(api.rt, [AMARA, "chr_seedVictor"])
