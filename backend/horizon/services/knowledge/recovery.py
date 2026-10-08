"""Restart recovery and background re-embedding (knowledge-memory-storage design D2, D8; knowledge-sources "Indexing
survives a restart", "Keyword-only user sources are re-embedded when a key appears").

At startup, every source still in progress resumes from the stage it reached:

| Status at the crash                 | Recovery                                                                    |
|-------------------------------------|-----------------------------------------------------------------------------|
| `queued`, `extracting`              | from extraction (or embedding, for a source with no original)               |
| `chunking`                          | from chunking (the chunk swap is one transaction: never a partial set)      |
| `embedding`, no `embed_sent_at`     | embedding, only the chunks with no vector (recorded batches aren't re-sent) |
| `embedding`, `embed_sent_at` set    | a batch was in flight: `keyword_only`, marker kept, until a user Retry      |

Background re-embed runs at startup with a key set and when the key becomes `set`: user-added `keyword_only` sources
with passages and no in-flight marker. Seed sources wait for their explicit Index (D11).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import and_, select, update

from horizon.db import tables as t
from horizon.events.bus import GLOBAL

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.knowledge")
S = t.knowledge_sources.c


async def recover(rt: Runtime) -> None:
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(S.id, S.status, S.has_original, S.embed_sent_at, S.world_id).where(
            S.status.in_(("queued", "extracting", "chunking", "embedding"))))).all()
    for sid, status, has_original, sent_at, world_id in rows:
        if status == "embedding" and sent_at is not None:
            async with rt.db.write() as tx:
                await tx.conn.execute(update(t.knowledge_sources).where(and_(S.id == sid, S.status == "embedding"))
                                      .values(status="keyword_only", embedding_space_id=None))
                tx.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": sid, "worldId": world_id})
            log.warning("knowledge source %s had an embedding batch in flight at the last stop; it stays keyword-only "
                        "until it is re-indexed (never paid twice)", sid)
            continue
        if status == "embedding":
            rt.ingest.submit(sid, "embed")
        elif status == "chunking":
            rt.ingest.submit(sid, "chunk")
        else:
            rt.ingest.submit(sid, "extract" if has_original else "embed")


async def reembed_user_sources(rt: Runtime) -> None:
    if rt.keys.status() != "set":
        return
    async with rt.db.write() as tx:
        ids = list((await tx.conn.execute(select(S.id).where(and_(
            S.is_seed.is_(False), S.status == "keyword_only", S.embed_sent_at.is_(None), S.chunk_count > 0)))).scalars())
        if ids:
            await tx.conn.execute(update(t.knowledge_sources).where(and_(S.id.in_(ids), S.status == "keyword_only"))
                                  .values(status="queued"))
    for sid in ids:
        rt.ingest.submit(sid, "embed")
    if ids:
        log.info("re-embedding %d keyword-only source(s) now that a key is set", len(ids))
