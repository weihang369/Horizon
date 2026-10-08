"""The SpaceManager (doc 02 §3.9, D-64): embedding spaces and their vec0 tables.

vec tables are created here at runtime, never by Alembic. For the active space (and a `building` one during a switch,
knowledge-memory-storage design D9) it ensures:
- `memory_vec__{space}` and `knowledge_vec__{space}` (vec0, `character_id` partition key, cosine distance);
- `AFTER DELETE` triggers on `memory_items` / `knowledge_chunks` that delete the vector by `rid`
  (spike 02: they fire on FK-cascade deletes too).
Everything is idempotent, so restarts change nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db.tables import embedding_spaces, knowledge_sources


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


def spec_of(row: Any) -> SpaceSpec:
    return SpaceSpec(id=str(row["id"]), model=str(row["model"]), provider=str(row["provider"]), dims=int(row["dims"]),
                     query_instruction=row["query_instruction"], normalized=bool(row["normalized"]))


async def active(conn: AsyncConnection) -> SpaceSpec:
    row = (await conn.execute(select(embedding_spaces).where(embedding_spaces.c.status == "active"))).mappings().first()
    if row is None:
        raise RuntimeError("no active embedding space")
    return spec_of(row)


async def building(conn: AsyncConnection) -> SpaceSpec | None:
    row = (await conn.execute(select(embedding_spaces).where(embedding_spaces.c.status == "building"))).mappings().first()
    return spec_of(row) if row is not None else None


async def non_retired(conn: AsyncConnection) -> list[SpaceSpec]:
    """The spaces every new vector is written to: the active one first, then a building one (dual-write, D9)."""
    rows = (await conn.execute(select(embedding_spaces).where(embedding_spaces.c.status.in_(("active", "building")))
                               .order_by(embedding_spaces.c.status))).mappings().all()   # 'active' < 'building'
    return [spec_of(r) for r in rows]


async def create_building(conn: AsyncConnection, spec: SpaceSpec, now_iso: str) -> None:
    """Start a switch: register `spec` as `building` with its vec tables and delete triggers. One build at a time."""
    if await building(conn) is not None:
        raise RuntimeError("an embedding space is already building")
    await conn.execute(embedding_spaces.insert().values(
        id=spec.id, model=spec.model, provider=spec.provider, dims=spec.dims, dtype="float32",
        normalized=spec.normalized, query_instruction=spec.query_instruction, doc_template=None,
        status="building", created_at=now_iso))
    for stmt in _ddl(spec.id, spec.dims):
        await conn.execute(text(stmt))


async def flip(conn: AsyncConnection, building_id: str) -> None:
    """The switch, in the caller's transaction (D9): building → active, active → retired. A source whose every chunk
    has a vector in the new space moves its `embedding_space_id` there; the others become keyword-only."""
    row = (await conn.execute(select(embedding_spaces).where(embedding_spaces.c.id == building_id))).mappings().first()
    if row is None or row["status"] != "building":
        raise RuntimeError(f"{building_id} is not building")
    _, kno = vec_tables(building_id)
    S = knowledge_sources.c
    await conn.execute(update(embedding_spaces).where(embedding_spaces.c.status == "active").values(status="retired"))
    await conn.execute(update(embedding_spaces).where(embedding_spaces.c.id == building_id).values(status="active"))
    full = text(f"SELECT s.id FROM knowledge_sources s WHERE s.chunk_count > 0 AND NOT EXISTS ("
                f"SELECT 1 FROM knowledge_chunks c WHERE c.source_id = s.id AND c.rid NOT IN (SELECT rid FROM {kno}))")
    ids = [r[0] for r in (await conn.execute(full)).all()]
    await conn.execute(update(knowledge_sources).where(S.id.in_(ids)).values(embedding_space_id=building_id))
    await conn.execute(update(knowledge_sources).where(S.id.not_in(ids), S.embedding_space_id.is_not(None))
                       .values(embedding_space_id=None))
    await conn.execute(update(knowledge_sources).where(S.id.not_in(ids), S.status == "indexed")
                       .values(status="keyword_only"))
