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
    assert version == "0006"  # M14: message_ai_meta.safety
    assert {"message_ai_meta", "message_index"} <= names
    assert {"memory_fts", "knowledge_fts", "message_fts"} <= names
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


def test_0003_ai_foundation_columns_and_table(tmp_path: Path) -> None:
    """ai-foundation 2.1 (data-storage "AI foundation migration"): an M6 database keeps its ledger rows, the new
    columns read NULL, `ai_calls` exists empty, and deleting a world cascades to its captured calls."""
    import sqlite3

    from alembic import command

    from horizon.db.migrate import alembic_config

    db = tmp_path / "m6.db"
    command.upgrade(alembic_config(db), "0002")
    conn = sqlite3.connect(db)
    now = "2026-10-10T03:00:00.000Z"
    conn.execute("INSERT INTO usage_records(id, at, local_day, category, cost_usd, is_seed) "
                 "VALUES ('use_a', ?, '2026-10-10', 'chat', 0.001, 0)", (now,))
    conn.commit()
    conn.close()
    upgrade_head(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute("SELECT finish_reason, tokens_reasoning FROM usage_records").fetchall() == [(None, None)]
        assert conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone() == (0,)
        conn.execute("INSERT INTO worlds(id, name, cover, you, is_seed, created_at, updated_at, last_active_at) "
                     "VALUES ('wld_a', 'A', '{}', NULL, 0, ?, ?, ?)", (now, now, now))
        conn.execute("INSERT INTO ai_calls(id, kind, created_at, world_id, request) "
                     "VALUES ('aic_a', 'call', ?, 'wld_a', '{}')", (now,))
        conn.execute("DELETE FROM worlds WHERE id = 'wld_a'")
        assert conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone() == (0,)   # the world's rows cascade
    finally:
        conn.close()


def test_0005_memory_up_and_down(tmp_path: Path) -> None:
    """memory 1.1 (data-storage "The memory migration"): an M12 database's sessions get their checkpoint at their
    highest message `seq` (an empty one at 0), `message_index` cascades from messages and feeds `message_fts` by
    trigger, and the downgrade leaves every other table as it was."""
    from alembic import command
    from sqlalchemy import inspect

    from horizon.db.migrate import alembic_config

    db = tmp_path / "m12.db"
    command.upgrade(alembic_config(db), "0004")
    eng = create_engine(f"sqlite:///{db.as_posix()}")
    before = set(inspect(eng).get_table_names())
    before_cols = {c["name"] for c in inspect(eng).get_columns("sessions")}
    eng.dispose()
    now = "2026-10-16T03:00:00.000Z"
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO worlds(id, name, cover, is_seed, created_at, updated_at, last_active_at) "
                 "VALUES ('wld_a', 'A', '{}', 0, ?, ?, ?)", (now, now, now))
    for sid in ("ses_long", "ses_empty"):
        conn.execute("INSERT INTO sessions(id, world_id, title, title_is_custom, mode, status, emotion_mode, "
                     "music_policy, readable_mode, is_seed, cost_usd, message_count, created_at, updated_at) "
                     "VALUES (?, 'wld_a', 'T', 0, 'one_on_one', 'active', 'auto', 'off', 0, 0, 0, 0, ?, ?)",
                     (sid, now, now))
    for seq in range(1, 58):
        conn.execute("INSERT INTO messages(id, session_id, seq, author_type, kind, content, status, created_at) "
                     "VALUES (?, 'ses_long', ?, 'user', 'chat', 'hi', 'complete', ?)", (f"msg_{seq:02d}", seq, now))
    conn.commit()
    conn.close()
    upgrade_head(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        seqs = dict(conn.execute("SELECT id, memory_seq FROM sessions").fetchall())
        assert seqs == {"ses_long": 57, "ses_empty": 0}
        assert conn.execute("SELECT memory_reread, memory_tries FROM sessions WHERE id = 'ses_long'").fetchone()             == ("[]", 0)
        conn.execute("INSERT INTO message_index(message_id, session_id, seq, author, text, created_at) "
                     "VALUES ('msg_03', 'ses_long', 3, 'Kai', 'Kai: my sister Mia works nights', ?)", (now,))
        hits = conn.execute("SELECT rowid FROM message_fts WHERE message_fts MATCH 'sister'").fetchall()
        assert len(hits) == 1
        cfg = dict(conn.execute("SELECT k, v FROM message_fts_config").fetchall())
        assert cfg.get("secure-delete") == 1
        conn.execute("DELETE FROM messages WHERE id = 'msg_03'")              # the index row cascades
        assert conn.execute("SELECT count(*) FROM message_index").fetchone() == (0,)
        assert conn.execute("SELECT rowid FROM message_fts WHERE message_fts MATCH 'sister'").fetchall() == []
        conn.commit()
    finally:
        conn.close()
    command.downgrade(alembic_config(db), "0004")
    eng = create_engine(f"sqlite:///{db.as_posix()}")
    assert set(inspect(eng).get_table_names()) == before
    assert {c["name"] for c in inspect(eng).get_columns("sessions")} == before_cols
    eng.dispose()


def test_0006_safety_up_and_down(tmp_path: Path) -> None:
    """safety 1.4 (data-storage "The safety migration"): an M13 database's `message_ai_meta` rows read `safety` NULL
    (not flagged), the column takes the stored answers, and the downgrade drops it with the rewrites unchanged."""
    from alembic import command
    from sqlalchemy import inspect

    from horizon.db.migrate import alembic_config

    db = tmp_path / "m13.db"
    command.upgrade(alembic_config(db), "0005")
    now = "2026-10-17T03:00:00.000Z"
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO worlds(id, name, cover, is_seed, created_at, updated_at, last_active_at) "
                 "VALUES ('wld_a', 'A', '{}', 0, ?, ?, ?)", (now, now, now))
    conn.execute("INSERT INTO sessions(id, world_id, title, title_is_custom, mode, status, emotion_mode, "
                 "music_policy, readable_mode, is_seed, cost_usd, message_count, created_at, updated_at) "
                 "VALUES ('ses_a', 'wld_a', 'T', 0, 'one_on_one', 'active', 'auto', 'off', 0, 0, 0, 0, ?, ?)",
                 (now, now))
    for i in (1, 2):
        conn.execute("INSERT INTO messages(id, session_id, seq, author_type, kind, content, status, created_at) "
                     "VALUES (?, 'ses_a', ?, 'user', 'chat', 'hi', 'complete', ?)", (f"msg_{i}", i, now))
    rewrites = json.dumps({"chr_a": {"text": "night shift rest days", "at": now}})
    conn.execute("INSERT INTO message_ai_meta(message_id, rewrites, updated_at) VALUES ('msg_1', ?, ?)", (rewrites, now))
    conn.commit()
    conn.close()
    upgrade_head(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute("SELECT safety FROM message_ai_meta").fetchall() == [(None,)]   # old rows: not flagged
        flags = json.dumps({"steer": True, "care": False, "pInput": 0.93, "pCare": 0.02, "at": now,
                            "v": {"unsafe_request": 1, "at_risk": 1}})
        conn.execute("INSERT INTO message_ai_meta(message_id, safety, updated_at) VALUES ('msg_2', ?, ?)", (flags, now))
        assert json.loads(conn.execute("SELECT safety FROM message_ai_meta WHERE message_id = 'msg_2'").fetchone()[0])["steer"]
        conn.execute("DELETE FROM messages WHERE id = 'msg_2'")              # the row cascades
        assert conn.execute("SELECT count(*) FROM message_ai_meta").fetchone() == (1,)
        conn.commit()
    finally:
        conn.close()
    command.downgrade(alembic_config(db), "0005")
    eng = create_engine(f"sqlite:///{db.as_posix()}")
    assert "safety" not in {c["name"] for c in inspect(eng).get_columns("message_ai_meta")}
    eng.dispose()
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT message_id, rewrites FROM message_ai_meta").fetchall() == [("msg_1", rewrites)]
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


async def test_message_vectors_live_beside_the_others(tmp_path: Path) -> None:
    """memory 1.2 (data-storage "Message vector tables exist at startup"): the active space gets
    `message_vec__{space}` partitioned by session; a restart keeps its rows; deleting the index row (or its message, by
    cascade) deletes the vector; dropping a retired space drops it."""
    import sqlite_vec

    db = Database(_migrated(tmp_path))
    now = "2026-10-16T03:00:00.000Z"
    async with db.write() as tx:
        space = await spaces.ensure_active(tx.conn, now)
    msg = spaces.message_vec_table(space)
    async with db.write() as tx:
        c = tx.conn
        await c.execute(text("INSERT INTO worlds(id, name, cover, is_seed, created_at, updated_at, last_active_at) "
                             "VALUES ('wld_a', 'A', '{}', 0, :n, :n, :n)"), {"n": now})
        await c.execute(text("INSERT INTO sessions(id, world_id, title, title_is_custom, mode, status, emotion_mode, "
                             "music_policy, readable_mode, is_seed, cost_usd, message_count, created_at, updated_at) "
                             "VALUES ('ses_a', 'wld_a', 'T', 0, 'one_on_one', 'active', 'auto', 'off', 0, 0, 0, 0, "
                             ":n, :n)"), {"n": now})
        await c.execute(text("INSERT INTO messages(id, session_id, seq, author_type, kind, content, status, created_at) "
                             "VALUES ('msg_a', 'ses_a', 1, 'user', 'chat', 'hi', 'complete', :n)"), {"n": now})
        rid = (await c.execute(text("INSERT INTO message_index(message_id, session_id, seq, author, text, created_at) "
                                    "VALUES ('msg_a', 'ses_a', 1, 'Kai', 'Kai: hi', :n) RETURNING rid"),
                               {"n": now})).scalar_one()
        await c.execute(text(f"INSERT INTO {msg}(rid, session_id, embedding) VALUES (:r, 'ses_a', :e)"),
                        {"r": rid, "e": sqlite_vec.serialize_float32([0.1] * 1024)})
    async with db.write() as tx:   # a restart changes nothing
        await spaces.ensure_active(tx.conn, now)
    async with db.read() as conn:
        assert (await conn.execute(text(f"SELECT count(*) FROM {msg}"))).scalar_one() == 1
    async with db.write() as tx:
        await tx.conn.execute(text("DELETE FROM messages WHERE id = 'msg_a'"))   # cascades to the index row
    async with db.read() as conn:
        assert (await conn.execute(text(f"SELECT count(*) FROM {msg}"))).scalar_one() == 0
    async with db.write() as tx:
        await spaces._drop(tx.conn, space)
    async with db.read() as conn:
        names = set((await conn.execute(text("SELECT name FROM sqlite_master"))).scalars())
    assert msg not in names and f"message_index_vec_ad__{spaces.table_suffix(space)}" not in names
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
