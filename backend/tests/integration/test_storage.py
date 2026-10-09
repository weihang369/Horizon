"""Storage (tasks 4.2–4.5): migrations, the writer/reader engines, the SpaceManager, cascades and timestamps."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select, text

from horizon.db import spaces
from horizon.db import tables as t
from horizon.db.migrate import include_object, upgrade_head
from horizon.db.uow import Database
from horizon.domain.timeutil import normalise_iso
from tests.conftest import Api


def _migrated(tmp_path: Path) -> Path:
    db = tmp_path / "h.db"
    upgrade_head(db)
    return db


# ── 4.2 migrations ──
def test_migrate_twice_and_no_drift(tmp_path: Path) -> None:
    db = _migrated(tmp_path)
    upgrade_head(db)  # a second run changes nothing
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"include_object": include_object, "compare_type": True})
        diff = compare_metadata(ctx, t.metadata)
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        names = set(conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars())
    engine.dispose()
    assert diff == [], diff
    assert version == "0002"
    assert {"memory_fts", "knowledge_fts"} <= names
    assert not any("_vec__" in n for n in names)  # vec tables belong to the SpaceManager


def test_0002_marker_column_and_fts_secure_delete(tmp_path: Path) -> None:
    """knowledge-memory-storage 1.2: `embed_sent_at` exists and both FTS tables delete securely (design D2, D16)."""
    import sqlite3

    db = _migrated(tmp_path)
    conn = sqlite3.connect(db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(knowledge_sources)")}
        assert "embed_sent_at" in cols
        for fts in ("memory_fts", "knowledge_fts"):
            cfg = dict(conn.execute(f"SELECT k, v FROM {fts}_config").fetchall())
            assert cfg.get("secure-delete") == 1, (fts, cfg)
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert {"knowledge_chunks_ai", "knowledge_chunks_ad", "knowledge_chunks_au"} <= triggers
    finally:
        conn.close()


def test_0002_keeps_rows_of_an_m4_database(tmp_path: Path) -> None:
    import sqlite3

    from alembic import command

    from horizon.db.migrate import alembic_config

    db = tmp_path / "m4.db"
    command.upgrade(alembic_config(db), "0001")
    conn = sqlite3.connect(db)
    now = "2026-10-03T03:00:00.000Z"
    conn.execute("INSERT INTO worlds(id, name, cover, you, is_seed, created_at, updated_at, last_active_at) "
                 "VALUES ('wld_a', 'A', '{}', NULL, 0, ?, ?, ?)", (now, now, now))
    conn.commit()
    conn.close()
    upgrade_head(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT name FROM worlds").fetchall() == [("A",)]
    finally:
        conn.close()


async def test_writer_deletes_securely_and_readers_do_not_write(tmp_path: Path) -> None:
    db = Database(_migrated(tmp_path), publish=lambda ch, ev: None)
    async with db.write() as tx:
        assert (await tx.conn.execute(text("PRAGMA secure_delete"))).scalar_one() == 1
    # Readers never delete, so they keep the SQLite build's compile-time default: off in the Windows build, on in some
    # Linux builds (SQLITE_SECURE_DELETE). What matters is that only the writer forces it (M6 CI, Linux).
    with sqlite3.connect(":memory:") as raw:
        build_default = raw.execute("PRAGMA secure_delete").fetchone()[0]
    async with db.read() as conn:
        assert (await conn.execute(text("PRAGMA secure_delete"))).scalar_one() == build_default
    await db.dispose()


# ── 4.3 engines and the unit of work ──
async def test_writes_serialise_and_publish_after_commit(tmp_path: Path) -> None:
    published: list[str] = []
    db = Database(_migrated(tmp_path), publish=lambda ch, ev: published.append(ev["id"]))
    now = "2026-10-03T03:00:00.000Z"

    async def make(i: int) -> None:
        async with db.write() as tx:
            await tx.conn.execute(t.worlds.insert().values(id=f"wld_w{i}", name=f"W{i}", cover={"kind": "preset"}, you=None,
                                                           is_seed=False, created_at=now, updated_at=now, last_active_at=now))
            await asyncio.sleep(0)  # yield inside the transaction: the lock keeps writers apart
            tx.publish("global", {"id": f"wld_w{i}"})

    await asyncio.gather(*(make(i) for i in range(20)))
    async with db.read() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM worlds"))).scalar_one() == 20
    assert sorted(published) == sorted(f"wld_w{i}" for i in range(20))

    try:
        async with db.write() as tx:
            await tx.conn.execute(t.worlds.insert().values(id="wld_x", name="X", cover={"kind": "preset"}, you=None,
                                                           is_seed=False, created_at=now, updated_at=now, last_active_at=now))
            tx.publish("global", {"id": "wld_x"})
            raise RuntimeError("roll back")
    except RuntimeError:
        pass
    assert "wld_x" not in published
    async with db.read() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM worlds WHERE id='wld_x'"))).scalar_one() == 0
    await db.dispose()


async def test_reader_sees_committed_state_only(tmp_path: Path) -> None:
    db = Database(_migrated(tmp_path))
    now = "2026-10-03T03:00:00.000Z"
    async with db.write() as tx:
        await tx.conn.execute(t.worlds.insert().values(id="wld_a", name="A", cover={"kind": "preset"}, you=None,
                                                       is_seed=False, created_at=now, updated_at=now, last_active_at=now))
        async with db.read() as conn:  # a concurrent reader during the write transaction
            assert (await conn.execute(text("SELECT count(*) FROM worlds"))).scalar_one() == 0
    async with db.read() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM worlds"))).scalar_one() == 1
    await db.dispose()


async def test_a_disposed_database_never_reopens(tmp_path: Path) -> None:
    db = Database(_migrated(tmp_path))
    await db.dispose()
    with pytest.raises(RuntimeError, match="closed"):
        async with db.read():
            pass
    with pytest.raises(RuntimeError, match="closed"):
        async with db.write():
            pass



async def test_dispose_waits_for_a_read_under_way(tmp_path: Path) -> None:
    """engine.dispose() cannot close a checked-out connection: dispose waits for it to come back first."""
    db = Database(_migrated(tmp_path))
    entered, release = asyncio.Event(), asyncio.Event()

    async def reader() -> None:
        async with db.read() as conn:
            entered.set()
            await release.wait()
            await conn.execute(text("SELECT 1"))

    task = asyncio.create_task(reader())
    await entered.wait()
    disposing = asyncio.create_task(db.dispose())
    await asyncio.sleep(0.1)
    assert not disposing.done()
    release.set()
    await task
    await disposing
    assert db._checked_out() == 0

# ── 4.4 SpaceManager ──
async def test_default_space_once(tmp_path: Path) -> None:
    db = Database(_migrated(tmp_path))
    for _ in range(2):  # a restart changes nothing
        async with db.write() as tx:
            space = await spaces.ensure_active(tx.conn, "2026-10-03T03:00:00.000Z")
    mem, kno = spaces.vec_tables(space)
    async with db.read() as conn:
        rows = (await conn.execute(select(t.embedding_spaces))).mappings().all()
        assert [(r["id"], r["status"], r["dims"]) for r in rows] == [(space, "active", 1024)]
        for name in (mem, kno):
            assert (await conn.execute(text(f"SELECT count(*) FROM {name}"))).scalar_one() == 0
    await db.dispose()


# ── 4.5 cascades and timestamps ──
async def test_world_delete_clears_fts_and_vectors(api: Api) -> None:
    rt = api.rt
    mem_vec, kno_vec = spaces.vec_tables(rt.space_id or "")
    async with rt.db.write() as tx:  # give Amara's chunks and memories vectors, as M5 will
        for table, src in ((kno_vec, "knowledge_chunks"), (mem_vec, "memory_items")):
            await tx.conn.execute(text(f"INSERT INTO {table}(rid, character_id, embedding) "
                                       f"SELECT rid, character_id, :e FROM {src} WHERE world_id = 'wld_seedMeridian'"),
                                  {"e": json.dumps([0.1] * 1024)})
    async with rt.db.read() as conn:
        before = (await conn.execute(text(f"SELECT count(*) FROM {kno_vec}"))).scalar_one()
        assert before > 0
        assert (await conn.execute(text("SELECT count(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'triage'"))).scalar_one() > 0
    r = await api.client.delete("/api/v1/worlds/wld_seedMeridian")
    assert r.status_code == 204
    async with rt.db.read() as conn:
        assert (await conn.execute(text(f"SELECT count(*) FROM {kno_vec}"))).scalar_one() == 0
        assert (await conn.execute(text(f"SELECT count(*) FROM {mem_vec}"))).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'triage'"))).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM knowledge_chunks WHERE world_id='wld_seedMeridian'"))).scalar_one() == 0


def test_timestamp_normalisation() -> None:
    assert normalise_iso("2026-09-14T08:00:00Z") == "2026-09-14T08:00:00.000Z"
    assert normalise_iso("2026-09-14T16:00:00.5+08:00") == "2026-09-14T08:00:00.500Z"
    assert normalise_iso("2026-10-01T10:02:50.373456Z") == "2026-10-01T10:02:50.373Z"


async def test_seed_timestamps_are_stored_normalised(api_normal: Api) -> None:
    w = await api_normal.json("/api/v1/worlds/wld_seedMeridian")
    assert w["createdAt"] == "2026-09-14T08:00:00.000Z"
