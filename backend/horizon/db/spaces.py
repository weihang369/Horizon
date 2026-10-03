"""The SpaceManager (doc 02 §3.9, D-64): embedding spaces and their vec0 tables.

vec tables are created here at runtime, never by Alembic. For the active space it ensures:
- `memory_vec__{space}` and `knowledge_vec__{space}` (vec0, `character_id` partition key, cosine distance);
- `AFTER DELETE` triggers on `memory_items` / `knowledge_chunks` that delete the vector by `rid`
  (spike 02: they fire on FK-cascade deletes too).
Everything is idempotent, so restarts change nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db.tables import embedding_spaces


@dataclass(frozen=True)
class SpaceSpec:
    id: str
    model: str
    provider: str
    dims: int
    query_instruction: str | None = None
    normalized: bool = True


# Design D4 / OQ-12: the final model and dims are chosen at the AI stage; changing them is a space switch.
DEFAULT_SPACE = SpaceSpec(
    id="qwen3-emb-8b@1024", model="qwen/qwen3-embedding-8b", provider="Nebius", dims=1024,
    query_instruction="Given a question, retrieve passages that answer it",
)


def table_suffix(space_id: str) -> str:
    """`qwen3-emb-8b@1024` → `qwen3_emb_8b_1024` (a safe SQL identifier)."""
    return re.sub(r"[^0-9A-Za-z]+", "_", space_id).strip("_").lower()


def vec_tables(space_id: str) -> tuple[str, str]:
    s = table_suffix(space_id)
    return f"memory_vec__{s}", f"knowledge_vec__{s}"


def _ddl(space_id: str, dims: int) -> list[str]:
    mem, kno = vec_tables(space_id)
    s = table_suffix(space_id)
    return [
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {mem} USING vec0(rid INTEGER PRIMARY KEY, "
        f"character_id TEXT PARTITION KEY, embedding FLOAT[{dims}] distance_metric=cosine)",
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {kno} USING vec0(rid INTEGER PRIMARY KEY, "
        f"character_id TEXT PARTITION KEY, embedding FLOAT[{dims}] distance_metric=cosine)",
        f"CREATE TRIGGER IF NOT EXISTS memory_items_vec_ad__{s} AFTER DELETE ON memory_items BEGIN "
        f"DELETE FROM {mem} WHERE rid = old.rid; END",
        f"CREATE TRIGGER IF NOT EXISTS knowledge_chunks_vec_ad__{s} AFTER DELETE ON knowledge_chunks BEGIN "
        f"DELETE FROM {kno} WHERE rid = old.rid; END",
    ]


async def ensure_active(conn: AsyncConnection, now_iso: str, default: SpaceSpec = DEFAULT_SPACE) -> str:
    """Make sure one active space exists, with its vec tables and triggers. Returns the active space id."""
    row = (await conn.execute(select(embedding_spaces).where(embedding_spaces.c.status == "active"))).mappings().first()
    if row is None:
        await conn.execute(embedding_spaces.insert().values(
            id=default.id, model=default.model, provider=default.provider, dims=default.dims, dtype="float32",
            normalized=default.normalized, query_instruction=default.query_instruction, doc_template=None,
            status="active", created_at=now_iso,
        ))
        space_id, dims = default.id, default.dims
    else:
        space_id, dims = str(row["id"]), int(row["dims"])
    for stmt in _ddl(space_id, dims):
        await conn.execute(text(stmt))
    return space_id


async def drop_retired(conn: AsyncConnection) -> None:
    """Startup step: retired spaces' tables are dropped on the next start (doc 02 §3.9)."""
    rows = (await conn.execute(select(embedding_spaces.c.id).where(embedding_spaces.c.status == "retired"))).scalars().all()
    for space_id in rows:
        s = table_suffix(space_id)
        mem, kno = vec_tables(space_id)
        for stmt in (f"DROP TRIGGER IF EXISTS memory_items_vec_ad__{s}", f"DROP TRIGGER IF EXISTS knowledge_chunks_vec_ad__{s}",
                     f"DROP TABLE IF EXISTS {mem}", f"DROP TABLE IF EXISTS {kno}"):
            await conn.execute(text(stmt))
