"""Database access (doc 01 §3): a writer engine (one connection, `BEGIN IMMEDIATE`, guarded by a process lock)
and a reader engine (a small pool, deferred read transactions).

Every connection: WAL, synchronous=NORMAL, foreign_keys=ON, busy_timeout=5000, and sqlite-vec loaded through
`AdaptedConnection.run_async` (spike 01). The writer also runs `secure_delete=ON`: deleted and rewritten cells and
freed pages are zeroed, so forgotten memory text leaves the file (knowledge-memory-storage design D16).
pysqlite's own transaction handling is switched off (`isolation_level=None`), so the `begin` event decides how each
transaction opens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlite_vec
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PRAGMAS = ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", "PRAGMA foreign_keys=ON", "PRAGMA busy_timeout=5000")
WRITER_PRAGMAS = ("PRAGMA secure_delete=ON",)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _on_connect(dbapi_conn: Any, _record: Any, *, extra: tuple[str, ...] = ()) -> None:
    async def load(conn: Any) -> None:
        await conn.enable_load_extension(True)
        await conn.load_extension(sqlite_vec.loadable_path())
        await conn.enable_load_extension(False)

    dbapi_conn.run_async(load)
    dbapi_conn.isolation_level = None
    cur = dbapi_conn.cursor()
    for p in (*PRAGMAS, *extra):
        cur.execute(p)
    cur.close()


def _make(url: str, *, begin_sql: str, pool_size: int, max_overflow: int,
          extra: tuple[str, ...] = ()) -> AsyncEngine:
    engine = create_async_engine(url, pool_size=pool_size, max_overflow=max_overflow, json_serializer=dumps,
                                 json_deserializer=json.loads)
    event.listen(engine.sync_engine, "connect", lambda c, r: _on_connect(c, r, extra=extra))

    @event.listens_for(engine.sync_engine, "begin")
    def _begin(conn: Connection) -> None:
        conn.exec_driver_sql(begin_sql)

    return engine


def make_engines(db_path: Path) -> tuple[AsyncEngine, AsyncEngine]:
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    writer = _make(url, begin_sql="BEGIN IMMEDIATE", pool_size=1, max_overflow=0, extra=WRITER_PRAGMAS)
    reader = _make(url, begin_sql="BEGIN", pool_size=4, max_overflow=4)
    return writer, reader
