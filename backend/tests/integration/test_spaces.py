"""SpaceManager switch operations (knowledge-memory-storage task 1.3, design D9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select, text

from horizon.db import spaces
from horizon.db import tables as t
from horizon.db.migrate import upgrade_head
from horizon.db.uow import Database

NOW = "2026-10-08T03:00:00.000Z"
TEST_SPACE = spaces.SpaceSpec(id="hash@64", model="test/hash", provider="scripted", dims=64)


async def _db(tmp_path: Path) -> Database:
    path = tmp_path / "h.db"
    upgrade_head(path)
    db = Database(path)
    async with db.write() as tx:
        await spaces.ensure_active(tx.conn, NOW)
    return db


async def _tables(db: Database) -> set[str]:
    async with db.read() as conn:
        return set((await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).scalars())


async def test_building_space_has_tables_and_dual_write_order(tmp_path: Path) -> None:
    db = await _db(tmp_path)
    async with db.write() as tx:
        await spaces.create_building(tx.conn, TEST_SPACE, NOW)
    mem, kno = spaces.vec_tables(TEST_SPACE.id)
    assert {mem, kno} <= await _tables(db)
    async with db.read() as conn:
        ids = [s.id for s in await spaces.non_retired(conn)]
        assert ids == [spaces.DEFAULT_SPACE.id, TEST_SPACE.id]
        assert (await spaces.active(conn)).id == spaces.DEFAULT_SPACE.id
        assert (await spaces.building(conn)) == TEST_SPACE
    async with db.write() as tx:
        with pytest.raises(RuntimeError):
            await spaces.create_building(tx.conn, TEST_SPACE, NOW)
    await db.dispose()


async def test_flip_leaves_one_active_space_and_moves_full_sources(tmp_path: Path) -> None:
    db = await _db(tmp_path)
    _, kno = spaces.vec_tables(TEST_SPACE.id)
    async with db.write() as tx:
        await spaces.create_building(tx.conn, TEST_SPACE, NOW)
        c = tx.conn
        await c.execute(t.worlds.insert().values(id="wld_a", name="A", cover={}, you=None, is_seed=False, created_at=NOW,
                                                 updated_at=NOW, last_active_at=NOW))
        await c.execute(t.characters.insert().values(
            id="chr_a", world_id="wld_a", status="approved", seed_prompt="", intent="", advisory=False, profile={},
            appearance={}, palette_id="p", emotion_set={}, version=1, energy_max=100, energy_current=100.0,
            energy_as_of=NOW, energy_spent_today=0.0, energy_day="2026-10-08", is_seed=False, created_at=NOW,
            updated_at=NOW))
        for sid, n in (("kno_full", 2), ("kno_part", 2)):
            await c.execute(t.knowledge_sources.insert().values(
                id=sid, character_id="chr_a", world_id="wld_a", title=sid, type="text", status="indexed", chunk_count=n,
                chunker_version="para@1", tokenizer="utf8/4", embedding_space_id=spaces.DEFAULT_SPACE.id,
                has_original=False, added_at=NOW, is_seed=False))
            await c.execute(t.knowledge_sections.insert().values(
                id=f"ksec_{sid}", source_id=sid, character_id="chr_a", world_id="wld_a", idx=0, text="x",
                token_count=1, char_start=0, char_end=1))
            for i in range(n):
                await c.execute(t.knowledge_chunks.insert().values(
                    id=f"kch_{sid}{i}", source_id=sid, section_id=f"ksec_{sid}", character_id="chr_a", world_id="wld_a",
                    idx=i, text=f"t{i}", token_count=1, char_start=0, char_end=2))
        rids = (await c.execute(select(t.knowledge_chunks.c.rid, t.knowledge_chunks.c.source_id))).all()
        for rid, sid in rids:
            if sid == "kno_full" or rid == min(r for r, s in rids if s == "kno_part"):
                await c.execute(text(f"INSERT INTO {kno}(rid, character_id, embedding) VALUES (:r, 'chr_a', :e)"),
                                {"r": rid, "e": json.dumps([0.125] * 64)})
    async with db.write() as tx:
        await spaces.flip(tx.conn, TEST_SPACE.id)
    async with db.read() as conn:
        rows = (await conn.execute(select(t.embedding_spaces.c.id, t.embedding_spaces.c.status))).all()
        assert dict(rows) == {spaces.DEFAULT_SPACE.id: "retired", TEST_SPACE.id: "active"}
        src = dict((await conn.execute(select(t.knowledge_sources.c.id, t.knowledge_sources.c.embedding_space_id))).all())
        st = dict((await conn.execute(select(t.knowledge_sources.c.id, t.knowledge_sources.c.status))).all())
    assert src == {"kno_full": TEST_SPACE.id, "kno_part": None}
    assert st == {"kno_full": "indexed", "kno_part": "keyword_only"}
    await db.dispose()


async def test_restart_drops_retired_tables_and_ensure_active_is_idempotent(tmp_path: Path) -> None:
    db = await _db(tmp_path)
    async with db.write() as tx:
        await spaces.create_building(tx.conn, TEST_SPACE, NOW)
    async with db.write() as tx:
        await spaces.flip(tx.conn, TEST_SPACE.id)
    old_mem, old_kno = spaces.vec_tables(spaces.DEFAULT_SPACE.id)
    assert {old_mem, old_kno} <= await _tables(db)
    async with db.write() as tx:  # the startup steps
        await spaces.drop_retired(tx.conn)
        assert await spaces.ensure_active(tx.conn, NOW) == TEST_SPACE.id
        assert await spaces.ensure_active(tx.conn, NOW) == TEST_SPACE.id
    names = await _tables(db)
    assert old_mem not in names and old_kno not in names
    assert set(spaces.vec_tables(TEST_SPACE.id)) <= names
    with pytest.raises(RuntimeError):
        async with db.write() as tx:
            await spaces.flip(tx.conn, TEST_SPACE.id)  # not building any more
    await db.dispose()
