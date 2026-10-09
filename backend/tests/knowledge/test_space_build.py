"""The embedding space build (knowledge-memory-storage task 8.1; embedding-spaces "Source added during a build",
"Atomic switch", "Retired tables removed"; design D9). A second test space, `hash@64`, through the scripted embedder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text

from horizon.ai.ports import Insert, MemoryDraft
from horizon.db import spaces
from horizon.db.spaces import DEFAULT_SPACE, SpaceSpec
from horizon.services.knowledge.build import build_space
from horizon.services.knowledge.index import ScopedIndex
from tests.conftest import Api
from tests.knowledge.kit import HANA, SUNNY, add_text, row, settle, source, vector_count

HASH64 = SpaceSpec(id="hash@64", model=DEFAULT_SPACE.model, provider="test", dims=64,
                   query_instruction=DEFAULT_SPACE.query_instruction)
NOTE = "Hana keeps bees behind the bakery. The hives sit under the plum tree and give about ten jars a summer."


async def space_rows(api: Api) -> dict[str, str]:
    async with api.rt.db.read() as conn:
        return {str(r[0]): str(r[1]) for r in (await conn.execute(text("SELECT id, status FROM embedding_spaces"))).all()}


async def tables(api: Api) -> set[str]:
    async with api.rt.db.read() as conn:
        return {str(r[0]) for r in (await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND (name GLOB 'memory_vec__*' OR name GLOB 'knowledge_vec__*')"))).all()}


async def memory_vectors(api: Api, space_id: str, character: str = HANA) -> int:
    mem, _ = spaces.vec_tables(space_id)
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text(f"SELECT count(*) FROM {mem} WHERE character_id = :c"),
                                       {"c": character})).scalar_one())


async def indexed_note(api: Api) -> dict[str, Any]:
    src = await add_text(api, "Bees", NOTE)
    await settle(api)
    assert (await source(api, src["id"]))["source"]["status"] == "indexed"
    return src


async def test_atomic_switch(api: Api) -> None:
    await api.set_key()
    old = api.rt.space_id or ""
    src = await indexed_note(api)
    await api.rt.memory.apply(HANA, SUNNY, [Insert(MemoryDraft("fact", "Hana's plum tree flowers in March.", 0.6))])
    assert await memory_vectors(api, old) >= 1
    async with api.rt.db.read() as conn:
        seed_before = {str(x[0]): (x[1], x[2]) for x in (await conn.execute(text(
            "SELECT id, status, embedding_space_id FROM knowledge_sources WHERE is_seed = 1"))).all()}
    report = await build_space(api.rt, HASH64)
    assert report.chunks == (await row(api, src["id"]))["chunk_count"] and report.memories >= 1
    assert await space_rows(api) == {old: "retired", "hash@64": "active"}
    assert api.rt.space_id == "hash@64"
    r = await row(api, src["id"])
    assert r["status"] == "indexed" and r["embedding_space_id"] == "hash@64"
    assert await vector_count(api, src["id"], "hash@64") == r["chunk_count"]
    # Seed knowledge stays as it was: a build never indexes it on the user's behalf (D-91).
    async with api.rt.db.read() as conn:
        after = {str(x[0]): (x[1], x[2]) for x in (await conn.execute(text(
            "SELECT id, status, embedding_space_id FROM knowledge_sources WHERE is_seed = 1"))).all()}
        seed_vectors = (await conn.execute(text(
            "SELECT count(*) FROM knowledge_vec__hash_64 WHERE rid IN (SELECT c.rid FROM knowledge_chunks c "
            "JOIN knowledge_sources s ON s.id = c.source_id WHERE s.is_seed = 1)"))).scalar_one()
    assert after == seed_before and seed_vectors == 0
    # KNN answers from the new space only (64-dim vectors; the old 1 024-dim table is not consulted).
    idx = ScopedIndex(api.rt, SUNNY, HANA, api.rt.space_id or "")
    hits = await idx.knowledge_knn([1.0] + [0.0] * 63, 10)
    async with api.rt.db.read() as conn:
        mine = {int(x[0]) for x in (await conn.execute(text("SELECT rid FROM knowledge_chunks WHERE source_id = :s"),
                                                       {"s": src["id"]})).all()}
    assert hits and {h.rid for h in hits} <= mine


async def test_source_added_during_a_build(api: Api) -> None:
    await api.set_key()
    old = api.rt.space_id or ""
    async with api.rt.db.write() as tx:
        await spaces.create_building(tx.conn, HASH64, api.rt.now_iso())
    src = await indexed_note(api)                       # dual-written while hash@64 is building
    n = (await row(api, src["id"]))["chunk_count"]
    assert await vector_count(api, src["id"], old) == n and await vector_count(api, src["id"], "hash@64") == n
    await api.rt.memory.apply(HANA, SUNNY, [Insert(MemoryDraft("fact", "Hana sells honey on Saturdays.", 0.5))])
    assert await memory_vectors(api, "hash@64") >= 1
    report = await build_space(api.rt, HASH64)          # resumes the build: nothing left to embed for that source
    assert report.chunks == 0
    r = await row(api, src["id"])
    assert r["status"] == "indexed" and r["embedding_space_id"] == "hash@64"


async def test_a_source_not_fully_embedded_becomes_keyword_only(api: Api) -> None:
    await api.set_key()
    src = await indexed_note(api)
    async with api.rt.db.write() as tx:
        await spaces.create_building(tx.conn, HASH64, api.rt.now_iso())
        await tx.conn.execute(text("UPDATE knowledge_sources SET status = 'keyword_only' WHERE id = :s"), {"s": src["id"]})
    await build_space(api.rt, HASH64)                   # the build skips keyword-only sources
    r = await row(api, src["id"])
    assert r["status"] == "keyword_only" and r["embedding_space_id"] is None


async def test_retired_tables_removed_after_a_restart(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "build"
    first: Api = await make_api(data_dir=data)
    await first.set_key()
    old = first.rt.space_id or ""
    await indexed_note(first)
    await build_space(first.rt, HASH64)
    old_mem, old_kno = spaces.vec_tables(old)
    assert {old_mem, old_kno} <= await tables(first)    # dropped on the next start, not during the flip
    await first.rt.stop()
    second: Api = await make_api(data_dir=data)
    assert second.rt.space_id == "hash@64"
    left = await tables(second)
    assert old_mem not in left and old_kno not in left
    assert set(spaces.vec_tables("hash@64")) <= left
