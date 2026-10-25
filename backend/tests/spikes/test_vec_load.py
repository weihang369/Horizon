"""Spike (a): sqlite-vec loads under aiosqlite through AdaptedConnection.run_async (doc 01 §3)."""
import json
from pathlib import Path
from typing import Any

import sqlite_vec
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine


def _load_vec(dbapi_conn: Any) -> None:
    # run_async hands us the aiosqlite.Connection; its extension methods are coroutines run on aiosqlite's thread.
    async def load(conn: Any) -> None:
        await conn.enable_load_extension(True)
        await conn.load_extension(sqlite_vec.loadable_path())
        await conn.enable_load_extension(False)

    dbapi_conn.run_async(load)


async def test_vec_loads_and_knn(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'v.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_conn: Any, _rec: Any) -> None:
        _load_vec(dbapi_conn)

    async with engine.begin() as conn:
        version = (await conn.execute(text("select vec_version()"))).scalar_one()
        assert version.startswith("v")
        await conn.execute(text("create virtual table v using vec0("
                                "rid integer primary key, c text partition key, e float[3] distance_metric=cosine)"))
        for rid, vec in [(1, [1, 0, 0]), (2, [0, 1, 0]), (3, [0.9, 0.1, 0])]:
            await conn.execute(text("insert into v(rid, c, e) values (:r, 'a', :e)"), {"r": rid, "e": json.dumps(vec)})
        rows = (await conn.execute(text("select rid from v where e match :q and c = 'a' and k = 2 order by distance"),
                                   {"q": json.dumps([1, 0, 0])})).scalars().all()
    await engine.dispose()
    assert rows == [1, 3]
