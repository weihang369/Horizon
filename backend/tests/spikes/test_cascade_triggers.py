"""Spike (b): FTS5 external-content and vec0 AFTER DELETE triggers fire on FK-cascade deletes, keyed by a stable rid."""
import json
from pathlib import Path
from typing import Any

import sqlite_vec
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

DDL = [
    "create table parent (id text primary key)",
    """create table child (rid integer primary key, id text not null unique,
         parent_id text not null references parent(id) on delete cascade, body text not null)""",
    "create virtual table child_fts using fts5(body, content='child', content_rowid='rid', tokenize='porter unicode61')",
    "create virtual table child_vec using vec0(rid integer primary key, parent_id text partition key, e float[2])",
    """create trigger child_ai after insert on child begin
         insert into child_fts(rowid, body) values (new.rid, new.body); end""",
    """create trigger child_ad after delete on child begin
         insert into child_fts(child_fts, rowid, body) values ('delete', old.rid, old.body);
         delete from child_vec where rid = old.rid; end""",
]


async def _count(conn: AsyncConnection, sql: str) -> int:
    return int((await conn.execute(text(sql))).scalar_one())


async def test_cascade_clears_fts_and_vec(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_conn: Any, _rec: Any) -> None:
        async def load(conn: Any) -> None:
            await conn.enable_load_extension(True)
            await conn.load_extension(sqlite_vec.loadable_path())
        dbapi_conn.run_async(load)
        cur = dbapi_conn.cursor()
        cur.execute("pragma foreign_keys=on")
        cur.close()

    async with engine.begin() as conn:
        for s in DDL:
            await conn.execute(text(s))
        for p in ("p1", "p2"):
            await conn.execute(text("insert into parent values (:p)"), {"p": p})
        rows = [("c1", "p1", "triage fever"), ("c2", "p1", "triage burns"), ("c3", "p2", "fever chart")]
        for i, (cid, pid, body) in enumerate(rows, start=1):
            await conn.execute(text("insert into child(rid, id, parent_id, body) values (:r, :i, :p, :b)"),
                               {"r": i, "i": cid, "p": pid, "b": body})
            await conn.execute(text("insert into child_vec(rid, parent_id, e) values (:r, :p, :e)"),
                               {"r": i, "p": pid, "e": json.dumps([float(i), 1.0])})

    async with engine.begin() as conn:
        await conn.execute(text("delete from parent where id = 'p1'"))  # cascade → child → triggers
        assert await _count(conn, "select count(*) from child") == 1
        assert await _count(conn, "select count(*) from child_vec") == 1
        assert await _count(conn, "select count(*) from child_fts where child_fts match 'triage'") == 0
        assert await _count(conn, "select count(*) from child_fts where child_fts match 'fever'") == 1

    async with engine.connect() as conn:
        await conn.execute(text("vacuum"))
        hit = (await conn.execute(text(
            "select c.id from child_fts f join child c on c.rid = f.rowid where child_fts match 'fever'"))).scalar_one()
        assert hit == "c3"
    await engine.dispose()
