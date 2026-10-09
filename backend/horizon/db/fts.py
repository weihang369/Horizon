"""FTS5 secure-delete state (knowledge-memory-storage design D16).

Migration 0002 turns on FTS5 `secure-delete` for `memory_fts` and `knowledge_fts` when the SQLite library supports it
(>= 3.44). A delete then removes the row's terms from the index segments. Startup records whether it is on; when it
isn't (an older library), Forget calls `scrub_index()` after its delete, which merges the segments and drops the
tombstoned terms (cost: O(index size), small for memories).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

FTS_TABLES = ("memory_fts", "knowledge_fts")


async def secure_delete_active(conn: AsyncConnection, table: str = "memory_fts") -> bool:
    row = (await conn.execute(text(f"SELECT v FROM {table}_config WHERE k = 'secure-delete'"))).first()
    return row is not None and int(row[0]) == 1


async def scrub_index(conn: AsyncConnection, table: str = "memory_fts") -> None:
    await conn.execute(text(f"INSERT INTO {table}({table}) VALUES ('optimize')"))
