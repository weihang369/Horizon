"""One source's ingestion (knowledge-memory-storage design D1, D2, D6–D8, D19; doc 02 §3.8).

    original → extracted.md (page markers) → sections + child chunks (FTS by trigger) → vectors per non-retired space

Stages start at `extract`, `chunk` or `embed` (a seed source has no original, so it starts at `embed`; recovery starts
where the crash left it). The `knowledge_sources.status` column is the job record: every write is a compare-and-set on
an in-progress status, so a deleted source turns any late write into a no-op.

- **Extract.** MD/TXT/pasted text are read as UTF-8. PDF/DOCX go through the converter port; when it is the real one
  and conversion isn't ready, the source ends `failed` with the setup steps (D-96) and keeps its original.
- **Chunk.** Sections and chunks are replaced in one transaction (never a partial set), checked against the 3 000
  passages per character limit.
- **Embed.** Only with a key. Each batch is one paid call: `before_send` commits `embed_sent_at`, and the batch's vectors
  are written with the ledger row (`commit_with`), clearing the marker (D2). Any embedding failure (no key, a cap, a
  provider error, a malformed answer) ends `keyword_only`, readable, with no `error` (D8).
- **End.** `indexed` iff every chunk has a vector in the active space; else `keyword_only`; then one final
  `entity.changed` without `progress`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.chunker import CHUNKER_VERSION, TOKENIZER, Chunked, chunk
from horizon.ai.converter import ConversionError, ConvertedDoc, read_plain
from horizon.ai.embedder import Batch, BatchHooks
from horizon.db import spaces
from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.domain.timeutil import to_ms
from horizon.events.bus import GLOBAL
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.services.knowledge.sources import original_path, source_dir
from horizon.services.knowledge.validate import MAX_CHUNKS, MAX_PAGES
from horizon.storage.atomic import write_atomic

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.knowledge")

Stage = Literal["extract", "chunk", "embed"]
IN_PROGRESS = ("queued", "extracting", "chunking", "embedding")
PROGRESS_MIN_MS = 250
SETUP_STEPS = ("Reading PDF and DOCX files needs document conversion. Run `npm run setup:docling` and "
               "`horizon models fetch`, then Retry.")
S = t.knowledge_sources.c


class Stop(Exception):
    """The source was deleted (or changed hands) under the pipeline: stop quietly."""


class Pipeline:
    def __init__(self, rt: Runtime, source_id: str) -> None:
        self.rt = rt
        self.sid = source_id
        self.row: Any = None
        self.last_pct = 0.0
        self.last_emit_ms: float | None = None

    # ── row access ──
    async def load(self) -> Any:
        async with self.rt.db.read() as conn:
            self.row = (await conn.execute(select(t.knowledge_sources).where(S.id == self.sid))).mappings().first()
        if self.row is None:
            raise Stop()
        return self.row

    async def set_status(self, conn: AsyncConnection, status: str, **values: Any) -> None:
        res = await conn.execute(update(t.knowledge_sources).where(and_(S.id == self.sid, S.status.in_(IN_PROGRESS)))
                                 .values(status=status, **values))
        if res.rowcount != 1:
            raise Stop()

    async def stage(self, status: str, **values: Any) -> None:
        async with self.rt.db.write() as tx:
            await self.set_status(tx.conn, status, **values)

    # ── events ──
    def progress(self, stage: str, pct: float, *, throttle: bool = False) -> None:
        pct = round(max(self.last_pct, min(1.0, pct)), 4)
        now = float(to_ms(self.rt.clock.now()))
        if throttle and self.last_emit_ms is not None and now - self.last_emit_ms < PROGRESS_MIN_MS:
            return
        self.last_pct, self.last_emit_ms = pct, now
        self.rt.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": self.sid,
                                 "worldId": self.row["world_id"], "progress": {"stage": stage, "pct": pct}})

    async def finish(self, status: str, *, error: str | None = None, **values: Any) -> None:
        async with self.rt.db.write() as tx:
            await self.set_status(tx.conn, status, error={"message": error} if error else None, **values)
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": self.sid,
                                "worldId": self.row["world_id"]})

    # ── the run ──
    async def run(self, start: Stage) -> None:
        try:
            await self.load()
            doc: ConvertedDoc | None = None
            if start == "extract":
                doc = await self.extract()
                if doc is None:
                    return
            if start in ("extract", "chunk"):
                if not await self.chunk(doc):
                    return
            await self.embed()
        except Stop:
            log.info("knowledge source %s went away during indexing", self.sid)

    async def extract(self) -> ConvertedDoc | None:
        row = self.row
        await self.stage("extracting", error=None)
        self.progress("extracting", 0.05)
        path = original_path(self.rt, row)
        if path is None:
            await self.finish("failed", error="This source has no stored original to read.")
            return None
        kind = path.suffix.lstrip(".")
        doc: ConvertedDoc
        try:
            if kind in ("pdf", "docx"):
                converter = self.rt.ai.converter(self.rt.keys.status() == "set")
                if not converter.ready():
                    await self.finish("failed", error=SETUP_STEPS)
                    return None
                async with self.rt.docling_slots.slot():
                    converted: ConvertedDoc = await converter.convert(path, kind, title=row["title"])
                doc = converted
            else:
                doc = await read_plain(path)
        except ConversionError as e:
            await self.finish("failed", error=e.message)
            return None
        except UnicodeDecodeError:
            await self.finish("failed", error="This file isn't UTF-8 text.")
            return None
        if doc.pages is not None and doc.pages > MAX_PAGES:
            await self.finish("failed", error=f"This document has {doc.pages} pages; the limit is {MAX_PAGES}.")
            return None
        folder = source_dir(self.rt, row["world_id"], row["character_id"], self.sid)
        await asyncio.to_thread(write_atomic, folder / "extracted.md", doc.markdown.encode("utf-8"))
        await self.stage("extracting", extractor_version=doc.extractor, pages=doc.pages)
        self.progress("extracting", 0.45)
        return doc

    async def _stored_doc(self) -> ConvertedDoc | None:
        row = self.row
        md_path = source_dir(self.rt, row["world_id"], row["character_id"], self.sid) / "extracted.md"
        if not md_path.is_file():
            return None
        md = await asyncio.to_thread(md_path.read_text, "utf-8")
        return ConvertedDoc(markdown=md, pages=row["pages"], paged=row["mime"] == "application/pdf",
                            extractor=row["extractor_version"] or "")

    async def chunk(self, doc: ConvertedDoc | None) -> bool:
        row = self.row
        if doc is None:
            doc = await self._stored_doc()
            if doc is None:
                await self.finish("failed", error="This source's extracted text is missing; Retry reads it again.")
                return False
        await self.stage("chunking")
        self.progress("chunking", 0.55)
        out: Chunked = await asyncio.to_thread(chunk, doc.markdown, paged=doc.paged)
        children = out.children
        if not children:
            await self.finish("failed", error="This file has no readable text.", chunk_count=0)
            return False
        C = t.knowledge_chunks.c
        async with self.rt.db.write() as tx:
            conn = tx.conn
            others = (await conn.execute(select(func.count()).select_from(t.knowledge_chunks).where(and_(
                C.character_id == row["character_id"], C.source_id != self.sid)))).scalar_one()
            if int(others) + len(children) > MAX_CHUNKS:
                await self.set_status(conn, "failed", error={"message": (
                    f"This would give the character {int(others) + len(children):,} passages; the limit is "
                    f"{MAX_CHUNKS:,}. Delete a source first.")})
                tx.publish(GLOBAL, {"type": "entity.changed", "kind": "knowledge", "id": self.sid,
                                    "worldId": row["world_id"]})
                return False
            await conn.execute(delete(t.knowledge_sections).where(t.knowledge_sections.c.source_id == self.sid))
            idx = 0
            for si, sec in enumerate(out.sections):
                sec_id = new_id("ksec")
                await conn.execute(t.knowledge_sections.insert().values(
                    id=sec_id, source_id=self.sid, character_id=row["character_id"], world_id=row["world_id"], idx=si,
                    heading_path=sec.heading_path, page_start=sec.page_start, page_end=sec.page_end, text=sec.text,
                    token_count=sec.tokens, char_start=sec.char_start, char_end=sec.char_end))
                for ch in sec.children:
                    await conn.execute(t.knowledge_chunks.insert().values(
                        id=new_id("kch"), source_id=self.sid, section_id=sec_id, character_id=row["character_id"],
                        world_id=row["world_id"], idx=idx, locator=ch.locator, heading=ch.heading, text=ch.text,
                        token_count=ch.tokens, char_start=ch.char_start, char_end=ch.char_end))
                    idx += 1
            await self.set_status(conn, "chunking", chunk_count=len(children), chunker_version=CHUNKER_VERSION,
                                  tokenizer=TOKENIZER, embedding_space_id=None, pages=out.pages or doc.pages)
        self.progress("chunking", 0.65)
        return True

    async def embed(self) -> None:
        row = await self.load()
        rt = self.rt
        if not row["chunk_count"]:
            prior = row["error"].get("message") if isinstance(row["error"], dict) else None
            await self.finish("failed", error=prior or "Couldn't read this source.")
            return
        if rt.keys.status() != "set":
            await self.finish("keyword_only")
            return
        await self.stage("embedding")
        self.progress("embedding", 0.70)
        try:
            async with rt.embed_slots.slot():
                await self._embed_missing(row)
        except ProviderError as e:
            log.info("knowledge source %s stays keyword-only: embedding failed (%s)", self.sid, e.code)
        await self._end()

    async def _embed_missing(self, row: Any) -> None:
        rt = self.rt
        async with rt.db.read() as conn:
            targets = await spaces.non_retired(conn)
        embedder = rt.ai.embedder(True)
        ctx = call_ctx("embed_doc", world_id=row["world_id"], character_id=row["character_id"])
        for space in targets:
            _, kno = spaces.vec_tables(space.id)
            async with rt.db.read() as conn:
                todo = (await conn.execute(text(
                    f"SELECT rid, text FROM knowledge_chunks WHERE source_id = :s AND rid NOT IN (SELECT rid FROM {kno}) "
                    "ORDER BY idx"), {"s": self.sid})).all()
            if not todo:
                continue
            rids = [int(r[0]) for r in todo]
            done = 0
            total = len(rids)

            def hooks(batch: Batch, *, _rids: list[int] = rids, _kno: str = kno, _total: int = total) -> BatchHooks:
                async def before() -> None:
                    async with rt.db.write() as tx:
                        await self.set_status(tx.conn, "embedding", embed_sent_at=rt.now_iso())

                async def commit(conn: AsyncConnection, _row_id: str, b: Batch) -> None:
                    nonlocal done
                    exists = (await conn.execute(select(S.id).where(S.id == self.sid))).first()
                    if exists is None:
                        return  # deleted while the call was in flight: the row keeps the spend, no vectors (D18)
                    await _write_vectors(conn, _kno, row["character_id"], [_rids[i] for i in b.indices], b.vectors)
                    await conn.execute(update(t.knowledge_sources).where(S.id == self.sid).values(embed_sent_at=None))
                    done += len(b.indices)
                    self.progress("embedding", 0.70 + 0.25 * done / _total, throttle=True)

                return BatchHooks(before_send=before, commit_with=commit)

            out = await embedder.embed([str(r[1]) for r in todo], kind="document", space=space, ctx=ctx, hooks=hooks)
            if out.cached:
                async with rt.db.write() as tx:
                    await _write_vectors(tx.conn, kno, row["character_id"], [rids[i] for i in out.cached],
                                         [out.vectors[i] for i in out.cached])

    async def _end(self) -> None:
        rt = self.rt
        async with rt.db.read() as conn:
            active = await spaces.active(conn)
            _, kno = spaces.vec_tables(active.id)
            missing = (await conn.execute(text(
                f"SELECT count(*) FROM knowledge_chunks WHERE source_id = :s AND rid NOT IN (SELECT rid FROM {kno})"),
                {"s": self.sid})).scalar_one()
        if int(missing) == 0:
            await self.finish("indexed", embedding_space_id=active.id, indexed_at=rt.now_iso())
        else:
            await self.finish("keyword_only", embedding_space_id=None)


async def _write_vectors(conn: AsyncConnection, table: str, character_id: str, rids: list[int],
                         vectors: list[list[float]]) -> None:
    import sqlite_vec

    for rid, vec in zip(rids, vectors, strict=True):
        await conn.execute(text(f"DELETE FROM {table} WHERE rid = :r"), {"r": rid})
        await conn.execute(text(f"INSERT INTO {table}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                           {"r": rid, "c": character_id, "e": sqlite_vec.serialize_float32(vec)})
