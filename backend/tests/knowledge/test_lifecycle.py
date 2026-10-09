"""Recovery, re-embedding, delete, reindex and resets (knowledge-memory-storage tasks 4.4–4.5; knowledge-sources
"Indexing survives a restart", "Keyword-only user sources are re-embedded when a key appears", "Reindex", "Delete a
source"; demo-data "Indexed seed source after reset"; local-backend "Orphaned knowledge folder")."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import sqlite_vec
from sqlalchemy import text

from horizon.db import spaces
from horizon.runtime import sweep
from tests.conftest import Api
from tests.knowledge.kit import API, add_text, embedding_rows, row, settle, source, vector_count

AMARA = "chr_seedAmara"
SEED_SRC = "kno_seedAmara1"


def write_key(data_dir: Path) -> None:
    """A saved key without going through the API (setting it live would start the background re-embed)."""
    (data_dir / "secrets.local.json").write_text(json.dumps({"openRouterKey": "sk-or-test-0001"}), encoding="utf-8")


async def seventy(api: Api) -> str:
    src = await add_text(api, "Long", "\n\n".join(f"Paragraph number {i} about rice." for i in range(70)))
    await settle(api)
    assert (await source(api, src["id"]))["source"]["status"] == "keyword_only"
    return str(src["id"])


async def partly_embedded(api: Api, sid: str, n: int, *, sent: bool) -> None:
    """The state a crash leaves: the first `n` vectors stored, status `embedding`, the in-flight marker as given."""
    _, kno = spaces.vec_tables(api.rt.space_id or "")
    async with api.rt.db.write() as tx:
        rids = (await tx.conn.execute(text("SELECT rid FROM knowledge_chunks WHERE source_id = :s ORDER BY idx LIMIT :n"),
                                      {"s": sid, "n": n})).scalars().all()
        for rid in rids:
            await tx.conn.execute(text(f"INSERT INTO {kno}(rid, character_id, embedding) VALUES (:r, 'chr_seedHana', :e)"),
                                  {"r": rid, "e": sqlite_vec.serialize_float32([1.0] + [0.0] * 1023)})
        await tx.conn.execute(text("UPDATE knowledge_sources SET status = 'embedding', embed_sent_at = :t WHERE id = :s"),
                              {"t": api.rt.now_iso() if sent else None, "s": sid})


async def test_crash_between_batches_sends_only_the_rest(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "between"
    first: Api = await make_api(data_dir=data)
    sid = await seventy(first)
    await partly_embedded(first, sid, 64, sent=False)
    await first.rt.stop()
    write_key(data)
    second: Api = await make_api(data_dir=data)
    await settle(second)
    assert (await source(second, sid))["source"]["status"] == "indexed"
    assert await vector_count(second, sid) == 70
    assert len(await embedding_rows(second)) == 1   # only the last 6 passages were sent


async def test_crash_during_a_batch_waits_for_a_user_retry(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "during"
    first: Api = await make_api(data_dir=data)
    sid = await seventy(first)
    await partly_embedded(first, sid, 32, sent=True)
    await first.rt.stop()
    write_key(data)
    second: Api = await make_api(data_dir=data)
    await settle(second)
    r = await row(second, sid)
    assert r["status"] == "keyword_only" and r["embed_sent_at"] is not None
    assert await embedding_rows(second) == []       # nothing re-sent, not even by the background re-embed
    re = await second.client.post(f"{API}/knowledge/{sid}/reindex")
    assert re.status_code == 200 and re.json()["status"] == "indexing"
    await settle(second)
    assert (await source(second, sid))["source"]["status"] == "indexed"
    assert len(await embedding_rows(second)) == 2   # the 38 passages without vectors: two batches
    assert (await row(second, sid))["embed_sent_at"] is None


async def test_restart_while_chunking_resumes(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "chunking"
    first: Api = await make_api(data_dir=data)
    src = await add_text(first, "Tea", "Steep.\n\nServe.")
    await settle(first)
    async with first.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE knowledge_sources SET status = 'chunking' WHERE id = :s"), {"s": src["id"]})
    await first.rt.stop()
    second: Api = await make_api(data_dir=data)
    await settle(second)
    got = await source(second, src["id"])
    assert got["source"]["status"] == "keyword_only" and [c["text"] for c in got["chunks"]] == ["Steep.", "Serve."]


async def test_key_added_after_uploads_reembeds_user_sources_only(api: Api) -> None:
    src = await add_text(api, "Tea", "Steep for three minutes.")
    await settle(api)
    assert (await source(api, src["id"]))["source"]["status"] == "keyword_only"
    await api.set_key()
    await settle(api)
    assert (await source(api, src["id"]))["source"]["status"] == "indexed"
    assert (await source(api, SEED_SRC))["source"]["status"] == "keyword_only"


async def test_seed_reindex_keeps_chunk_ids_and_conflicts_while_indexing(api: Api) -> None:
    await api.set_key()
    before = [c["id"] for c in (await source(api, SEED_SRC))["chunks"]]
    r = await api.client.post(f"{API}/knowledge/{SEED_SRC}/reindex")
    assert r.status_code == 200 and r.json()["status"] == "indexing"
    again = await api.client.post(f"{API}/knowledge/{SEED_SRC}/reindex")
    assert again.status_code == 409 and again.json()["error"]["code"] == "conflict"
    await settle(api)
    after = await source(api, SEED_SRC)
    assert after["source"]["status"] == "indexed" and [c["id"] for c in after["chunks"]] == before
    assert (await api.client.post(f"{API}/knowledge/kno_nope/reindex")).status_code == 404


async def test_seed_failure_fails_again_with_its_reason(api: Api) -> None:
    async with api.rt.db.read() as conn:
        sid = (await conn.execute(text("SELECT id FROM knowledge_sources WHERE status = 'failed' AND is_seed = 1"))).scalar()
    if sid is None:
        return
    before = (await source(api, sid))["source"]["error"]
    assert (await api.client.post(f"{API}/knowledge/{sid}/reindex")).status_code == 200
    await settle(api)
    got = (await source(api, sid))["source"]
    assert got["status"] == "failed" and got["error"] == before


async def test_cited_source_deleted_keeps_message_citations(api: Api) -> None:
    async def cites() -> list[Any]:
        msgs = (await api.client.get(f"{API}/sessions/ses_seedDebate4Day/messages")).json()
        return [c for m in msgs["items"] for c in (m.get("citations") or []) if c["sourceId"] == SEED_SRC]

    before = await cites()
    assert before
    assert (await api.client.delete(f"{API}/knowledge/{SEED_SRC}")).status_code == 204
    assert (await api.client.get(f"{API}/knowledge/{SEED_SRC}")).status_code == 404
    assert await cites() == before
    assert (await api.client.delete(f"{API}/knowledge/{SEED_SRC}")).status_code == 404


async def test_delete_while_indexing_leaves_nothing_and_does_not_resume(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "deleting"
    api: Api = await make_api(data_dir=data)
    await api.set_key()
    r = await api.client.post(f"{API}/_test/ai-profile", json={"profile": "scripted", "overrides": {"embedder": "naive"}})
    assert r.status_code == 204
    fake = api.rt.fake
    assert fake is not None
    release = fake.park_embedding(fake.counts["embeddings"] + 1)
    src = await add_text(api, "Tea", "Steep.\n\nServe.")
    await asyncio.wait_for(fake.embed_parked.wait(), 10)
    folder = api.rt.cfg.knowledge_dir / "wld_seedSunnyHollow" / "chr_seedHana" / src["id"]
    assert folder.is_dir()
    deleting = asyncio.create_task(api.client.delete(f"{API}/knowledge/{src['id']}"))
    await asyncio.sleep(0.05)
    release.set()
    assert (await deleting).status_code == 204
    async with api.rt.db.read() as conn:
        for table in ("knowledge_sources", "knowledge_sections", "knowledge_chunks"):
            col = "id" if table == "knowledge_sources" else "source_id"
            n = (await conn.execute(text(f"SELECT count(*) FROM {table} WHERE {col} = :s"), {"s": src["id"]})).scalar_one()
            assert n == 0, table
        _, kno = spaces.vec_tables(api.rt.space_id or "")
        assert (await conn.execute(text(f"SELECT count(*) FROM {kno} WHERE character_id = 'chr_seedHana'"))).scalar_one() == 0
    assert not folder.exists()
    await api.rt.stop()
    again: Api = await make_api(data_dir=data)
    await settle(again)
    assert src["id"] not in again.rt.ingest.submitted


async def test_reset_returns_seed_sources_to_keyword_only(api: Api) -> None:
    await api.set_key()
    assert (await api.client.post(f"{API}/knowledge/{SEED_SRC}/reindex")).status_code == 200
    await settle(api)
    assert (await source(api, SEED_SRC))["source"]["status"] == "indexed"
    mine = await add_text(api, "Shift notes", "Night shift starts at seven.", character=AMARA)
    await settle(api)
    shipped = [c["text"] for c in (await source(api, SEED_SRC))["chunks"]]
    assert (await api.client.post(f"{API}/admin/reset-demo", json={"confirm": True})).status_code in (200, 204)
    await settle(api)
    seed = await source(api, SEED_SRC)
    assert seed["source"]["status"] == "keyword_only" and [c["text"] for c in seed["chunks"]] == shipped
    assert (await source(api, mine["id"]))["source"]["status"] == "indexed"


def test_sweeper_removes_orphaned_knowledge_folders(tmp_path: Path) -> None:
    data = tmp_path / "data"
    keep = data / "knowledge" / "wld_a" / "chr_a" / "kno_keep"
    orphan = data / "knowledge" / "wld_a" / "chr_a" / "kno_gone"
    fresh = data / "knowledge" / "wld_a" / "chr_a" / "kno_new"
    for f in (keep, orphan, fresh):
        f.mkdir(parents=True)
        (f / "original.txt").write_text("x")
    (data / "tmp").mkdir()
    old_upload = data / "tmp" / "abc.upload"
    old_upload.write_bytes(b"x")
    hour_ago = time.time() - 7200
    for p in (keep, orphan, old_upload):
        os.utime(p, (hour_ago, hour_ago))
    sweep(data, {"knowledge/wld_a/chr_a/kno_keep"})
    assert keep.is_dir() and not orphan.exists() and fresh.is_dir() and not old_upload.exists()
