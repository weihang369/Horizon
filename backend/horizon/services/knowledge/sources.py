"""Creating knowledge sources (knowledge-sources "Accepted inputs", "Knowledge limits"; design D3).

The upload has already been streamed and counted into `data/tmp/{uuid}.upload` (or is pasted text in memory) and its
content checked. One writer transaction then:
1. checks the character's source count against 20 (`details.limit: 20`);
2. refuses a duplicate SHA-256 on the same character (`conflict`, `details.existingSourceId`);
3. moves the original to `knowledge/{world}/{character}/{source}/original.{ext}` (atomic replace, before the commit,
   so the row never points to a missing file; removed again if the commit fails);
4. inserts the source as `queued` and announces it after the commit.

The caller then submits it to the ingestion worker. Counting inside the transaction closes the race between two
concurrent adds (the writer lock serialises them).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select, update

from horizon.api.errors import conflict, not_found
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.events.bus import GLOBAL
from horizon.services import reads
from horizon.services.knowledge.validate import MAX_SOURCES, MIME_OF, FileKind, too_many_sources
from horizon.storage.atomic import write_atomic

if TYPE_CHECKING:
    from horizon.runtime import Runtime

CHUNKER_VERSION = "para@1"
TOKENIZER = "utf8/4"
EXT: dict[str, str] = {"pdf": "pdf", "docx": "docx", "md": "md", "txt": "txt", "text": "txt"}


def source_dir(rt: Runtime, world_id: str, character_id: str, source_id: str) -> Path:
    return rt.cfg.knowledge_dir / world_id / character_id / source_id


def original_path(rt: Runtime, row: Any) -> Path | None:
    """The stored original of a source row, if it has one."""
    if not row["has_original"]:
        return None
    folder = source_dir(rt, row["world_id"], row["character_id"], row["id"])
    for ext in ("pdf", "docx", "md", "txt"):
        p = folder / f"original.{ext}"
        if p.is_file():
            return p
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


async def create_source(rt: Runtime, character_id: str, *, kind: FileKind | None, title: str, type_: str,
                        original_name: str | None, upload: Path | None = None, data: bytes | None = None) -> dict[str, Any]:
    """Insert a `queued` source for an upload already checked. Exactly one of `upload` (a temp file, moved) or `data`
    (pasted text) is given. Returns the wire `KnowledgeSource` (`status: "indexing"`)."""
    if (upload is None) == (data is None):
        raise ValueError("pass exactly one of upload and data")
    if upload is not None:
        sha, size = await asyncio.to_thread(_digest, upload)
    else:
        assert data is not None
        sha = hashlib.sha256(data).hexdigest()
        size = len(data)
    ext = EXT[kind or "text"]
    sid = new_id("kno")
    final: Path | None = None
    K = t.knowledge_sources.c
    try:
        async with rt.db.write() as tx:
            ch = await reads.character_row(tx.conn, character_id, allow_tombstone=False)
            world_id = str(ch["world_id"])
            count = (await tx.conn.execute(select(func.count()).select_from(t.knowledge_sources).where(
                K.character_id == character_id))).scalar_one()
            if int(count) >= MAX_SOURCES:
                raise too_many_sources()
            dup = (await tx.conn.execute(select(K.id, K.title).where(and_(K.character_id == character_id,
                                                                          K.sha256 == sha)))).first()
            if dup is not None:
                raise conflict(f"“{dup[1]}” already has this content.", {"existingSourceId": dup[0]})
            folder = source_dir(rt, world_id, character_id, sid)
            final = folder / f"original.{ext}"
            if upload is not None:
                await asyncio.to_thread(_move, upload, final)
            else:
                assert data is not None
                await asyncio.to_thread(write_atomic, final, data)
            now = rt.now_iso()
            row = {"id": sid, "character_id": character_id, "world_id": world_id, "title": title, "type": type_,
                   "url": None, "mime": MIME_OF[kind] if kind else "text/plain", "original_name": original_name,
                   "bytes": size, "pages": None, "sha256": sha, "status": "queued", "chunk_count": 0,
                   "extractor_version": None, "chunker_version": CHUNKER_VERSION, "tokenizer": TOKENIZER,
                   "embedding_space_id": None, "embed_sent_at": None, "has_original": True, "error": None,
                   "added_at": now, "indexed_at": None, "is_seed": False}
            await tx.conn.execute(t.knowledge_sources.insert().values(**row))
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": sid, "worldId": world_id})
    except BaseException:
        if final is not None:
            await asyncio.to_thread(shutil.rmtree, final.parent, True)
        raise
    finally:
        if upload is not None:
            await asyncio.to_thread(_discard, upload)
    return mp.knowledge_source_wire(row, 0)


def _digest(path: Path) -> tuple[str, int]:
    return sha256_file(path), path.stat().st_size


def _discard(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)


async def delete_source(rt: Runtime, source_id: str) -> None:
    """`DELETE /knowledge/{id}` (knowledge-sources "Delete a source"; design D18): stop its indexing first, then one
    transaction deletes the row (sections, chunks, FTS and vectors follow by cascade and triggers), then the folder."""
    async with rt.db.read() as conn:
        row = (await conn.execute(select(t.knowledge_sources).where(t.knowledge_sources.c.id == source_id))).mappings().first()
    if row is None:
        raise not_found("Source")
    await rt.ingest.cancel(source_id)
    async with rt.db.write() as tx:
        res = await tx.conn.execute(t.knowledge_sources.delete().where(t.knowledge_sources.c.id == source_id))
        if not res.rowcount:
            raise not_found("Source")
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": source_id, "worldId": row["world_id"]})
    await asyncio.to_thread(shutil.rmtree, source_dir(rt, row["world_id"], row["character_id"], source_id), True)


def _start_stage(rt: Runtime, row: Any) -> str:
    """The first stage whose stored output is out of date (design D2, knowledge-sources "Reindex")."""
    from horizon.ai.chunker import CHUNKER_VERSION as CURRENT_CHUNKER
    from horizon.ai.chunker import TOKENIZER as CURRENT_TOKENIZER

    if not row["has_original"]:
        return "embed"                      # seed: re-embed only, so chunk ids (and old citations) are kept
    if row["status"] == "failed" or not row["extractor_version"]:
        return "extract"
    folder = source_dir(rt, row["world_id"], row["character_id"], row["id"])
    if row["chunker_version"] != CURRENT_CHUNKER or row["tokenizer"] != CURRENT_TOKENIZER:
        return "chunk" if (folder / "extracted.md").is_file() else "extract"
    return "embed"


async def reindex_source(rt: Runtime, source_id: str) -> dict[str, Any]:
    """`POST /knowledge/{id}/reindex`: `conflict` while indexing or for a legacy `url` source; otherwise the source goes
    back to `indexing` from its lowest stale layer. A user Retry also clears an in-flight embedding marker (D2)."""
    K = t.knowledge_sources.c
    async with rt.db.write() as tx:
        row = (await tx.conn.execute(select(t.knowledge_sources).where(K.id == source_id))).mappings().first()
        if row is None:
            raise not_found("Source")
        if row["type"] == "url":
            raise conflict("Web page sources are read-only and can't be re-indexed.")
        if row["status"] in ("queued", "extracting", "chunking", "embedding") or rt.ingest.running(source_id):
            raise conflict("This source is already being indexed.")
        start = await asyncio.to_thread(_start_stage, rt, row)
        await tx.conn.execute(update(t.knowledge_sources).where(K.id == source_id).values(
            status="queued", embed_sent_at=None, error=row["error"] if start == "embed" else None))
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": source_id, "worldId": row["world_id"]})
        fresh = (await tx.conn.execute(select(t.knowledge_sources).where(K.id == source_id))).mappings().one()
        cited = (await tx.conn.execute(select(func.count()).select_from(t.message_citations).where(
            t.message_citations.c.source_id == source_id))).scalar_one()
    rt.ingest.submit(source_id, start)
    return mp.knowledge_source_wire(fresh, int(cited))
