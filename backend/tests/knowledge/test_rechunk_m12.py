"""Existing sources under `pack@2` (doc 10 K12; rag design D3, task 1.4; knowledge-sources "A source chunked by an older
version is re-chunked on reindex").

- A user source chunked by `para@1` keeps its pieces until reindexed; Reindex re-chunks it from the `chunk` stage, with
  new piece IDs, so an old citation's piece is gone and the viewer shows its "re-indexed" notice.
- Seed sources only re-embed and keep their IDs (`test_lifecycle.py::test_seed_reindex_keeps_chunk_ids…`).
- Startup never re-chunks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text

from horizon.ai.chunker import CHUNKER_VERSION
from tests.conftest import Api
from tests.knowledge.kit import API, add_text, embedding_rows, row, settle, source

OLD = ["# Soups", "Miso first.", "Then tofu."]          # what `para@1` stored for this text


async def as_para1(api: Api, sid: str) -> list[str]:
    """Rewrite a source's stored pieces as `para@1` left them (three pieces, the heading on its own), as an install from
    before M12 has them. Returns the old piece IDs."""
    async with api.rt.db.write() as tx:
        c = tx.conn
        [sec] = (await c.execute(text("SELECT id, character_id, world_id FROM knowledge_sections WHERE source_id = :s"),
                                 {"s": sid})).mappings().all()
        await c.execute(text("DELETE FROM knowledge_chunks WHERE source_id = :s"), {"s": sid})
        ids = [f"kch_old{i}" for i in range(3)]
        for i, (cid, body) in enumerate(zip(ids, OLD, strict=True)):
            await c.execute(text(
                "INSERT INTO knowledge_chunks (id, source_id, section_id, character_id, world_id, idx, locator, heading, "
                "text, token_count, char_start, char_end) VALUES (:id, :s, :sec, :c, :w, :i, '§ Soups', 'Soups', :t, 3, "
                "0, 1)"), {"id": cid, "s": sid, "sec": sec["id"], "c": sec["character_id"], "w": sec["world_id"],
                           "i": i, "t": body})
        await c.execute(text("UPDATE knowledge_sources SET chunker_version = 'para@1', chunk_count = 3 WHERE id = :s"),
                        {"s": sid})
    return ids


async def cite(api: Api, chunk_id: str, source_id: str) -> str:
    """A seed message that cited the old piece (its stored snapshot is the message's own)."""
    async with api.rt.db.write() as tx:
        mid = (await tx.conn.execute(text("SELECT id FROM messages ORDER BY id LIMIT 1"))).scalar_one()
        await tx.conn.execute(text("INSERT INTO message_citations (message_id, n, chunk_id, source_id) "
                                   "VALUES (:m, 99, :c, :s)"), {"m": mid, "c": chunk_id, "s": source_id})
    return str(mid)


async def test_a_para1_source_is_rechunked_on_reindex(api: Api) -> None:
    src = await add_text(api, "Soups", "# Soups\n\nMiso first.\n\nThen tofu.")
    await settle(api)
    sid = src["id"]
    old = await as_para1(api, sid)
    await cite(api, old[1], sid)
    assert [c["text"] for c in (await source(api, sid))["chunks"]] == OLD     # kept until reindexed
    r = await api.client.post(f"{API}/knowledge/{sid}/reindex")
    assert r.status_code == 200
    await settle(api)
    got = await source(api, sid)
    assert [(c["text"], c["locator"]) for c in got["chunks"]] == [("# Soups\n\nMiso first.\n\nThen tofu.", "§ Soups")]
    assert not {c["id"] for c in got["chunks"]} & set(old)          # new IDs: the old citation's piece is gone
    assert (await row(api, sid))["chunker_version"] == CHUNKER_VERSION == "pack@2"
    async with api.rt.db.read() as conn:
        kept = (await conn.execute(text("SELECT chunk_id FROM message_citations WHERE n = 99"))).scalar_one()
    assert kept == old[1]   # the citation row stays: the viewer finds no such piece and shows "it was re-indexed"


async def test_startup_never_rechunks(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "old"
    first: Api = await make_api(data_dir=data)
    src = await add_text(first, "Soups", "# Soups\n\nMiso first.\n\nThen tofu.")
    await settle(first)
    old = await as_para1(first, src["id"])
    await first.rt.stop()
    second: Api = await make_api(data_dir=data)
    await settle(second, 2000)
    got = await source(second, src["id"])
    assert [c["id"] for c in got["chunks"]] == old and [c["text"] for c in got["chunks"]] == OLD
    assert (await row(second, src["id"]))["chunker_version"] == "para@1"
    assert await embedding_rows(second) == []
