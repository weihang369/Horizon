"""Ingestion end to end (knowledge-memory-storage task 4.3; knowledge-sources "Indexing lifecycle", "Knowledge limits",
"Passages carry readable locators"; embedding-spaces "Embedding spend is labelled and capped")."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from horizon.gateway.pipeline import Caps
from tests import docs_kit
from tests.conftest import Api
from tests.knowledge.kit import (
    HANA,
    add_file,
    add_text,
    drain,
    embedding_rows,
    row,
    settle,
    source,
    vector_count,
)


async def test_markdown_with_a_key_is_indexed_with_progress(api: Api) -> None:
    await api.set_key()
    sub = api.rt.bus.subscribe("global")
    src = await add_file(api, "soups.md", b"# Soups\n\nMiso first.\n\nThen tofu.", "text/markdown")
    await settle(api)
    events = [e for e in drain(sub) if e.get("kind") == "knowledge" and e.get("id") == src["id"]]
    for e in events:
        api.rt.schema.check("GlobalEvent", e)
    progress = [e["progress"] for e in events if "progress" in e]
    assert len(progress) >= 3
    assert [p["pct"] for p in progress] == sorted(p["pct"] for p in progress)
    assert {p["stage"] for p in progress} == {"extracting", "chunking", "embedding"}
    assert "progress" not in events[-1] and "progress" not in events[0]
    got = await source(api, src["id"])
    assert got["source"]["status"] == "indexed" and got["source"]["chunks"] == 3
    assert [c["text"] for c in got["chunks"]] == ["# Soups", "Miso first.", "Then tofu."]
    for c in got["chunks"]:
        api.rt.schema.check("KnowledgeChunk", c)
    [usage] = await embedding_rows(api, HANA)
    assert usage["tokens_in"] > 0 and usage["model"] == "qwen/qwen3-embedding-8b" and usage["purpose"] == "embed_doc"
    assert await vector_count(api, src["id"]) == 3
    r = await row(api, src["id"])
    assert r["embed_sent_at"] is None and r["embedding_space_id"] == api.rt.space_id and r["indexed_at"]
    api.rt.bus.unsubscribe(sub)


async def test_without_a_key_it_ends_keyword_only_with_no_row(api: Api) -> None:
    src = await add_text(api, "Tea", "Steep for three minutes.")
    await settle(api)
    got = await source(api, src["id"])
    assert got["source"]["status"] == "keyword_only" and "error" not in got["source"]
    assert [c["text"] for c in got["chunks"]] == ["Steep for three minutes."]
    assert await embedding_rows(api) == []
    async with api.rt.db.read() as conn:
        hits = (await conn.execute(text("SELECT count(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'steep'"))).scalar_one()
    assert hits >= 1


async def test_cap_reached_ends_keyword_only_without_an_error(api: Api) -> None:
    await api.set_key()
    api.rt.gateway.caps = lambda: Caps(daily_cap_usd=0.0, creation_cap_usd=0.6, warn_at_pct=80)
    src = await add_text(api, "Tea", "Steep for three minutes.")
    await settle(api)
    got = await source(api, src["id"])
    assert got["source"]["status"] == "keyword_only" and "error" not in got["source"]
    assert await embedding_rows(api) == []


async def test_seventy_paragraphs_make_three_rows(api: Api) -> None:
    await api.set_key()
    body = "\n\n".join(f"Paragraph number {i} about rice." for i in range(70))
    src = await add_text(api, "Long", body)
    await settle(api)
    assert (await source(api, src["id"]))["source"]["status"] == "indexed"
    assert [r["purpose"] for r in await embedding_rows(api, HANA)] == ["embed_doc"] * 3


async def test_pdf_placeholders_in_test_mode(api: Api) -> None:
    src = await add_file(api, "Review.pdf", docs_kit.pdf(["Page one.", "Page two."]), "application/pdf")
    await settle(api)
    assert (await source(api, src["id"]))["source"]["status"] == "indexing"       # converting on the runtime clock
    await settle(api, 1000)
    got = await source(api, src["id"])
    assert got["source"]["status"] == "keyword_only"
    assert got["chunks"][0]["locator"] == "p. 1" and got["chunks"][0]["text"].startswith("Passage 1 of “Review.pdf”")


async def test_empty_markdown_fails_readably(api: Api) -> None:
    src = await add_file(api, "empty.md", b"   \n\n  ", "text/markdown")
    await settle(api)
    got = await source(api, src["id"])
    assert got["source"]["status"] == "failed" and got["source"]["error"] == "This file has no readable text."


async def _fill_chunks(api: Api, n: int) -> None:
    """Give Hana a bulk source with `n` passages (a fixture, written straight to the tables)."""
    now = api.rt.now_iso()
    async with api.rt.db.write() as tx:
        c = tx.conn
        await c.execute(text(
            "INSERT INTO knowledge_sources(id, character_id, world_id, title, type, status, chunk_count, chunker_version, "
            "tokenizer, has_original, added_at, is_seed) VALUES ('kno_bulk', :c, 'wld_seedSunnyHollow', 'Bulk', 'text', "
            "'keyword_only', :n, 'para@1', 'utf8/4', 0, :t, 0)"), {"c": HANA, "n": n, "t": now})
        await c.execute(text(
            "INSERT INTO knowledge_sections(id, source_id, character_id, world_id, idx, text, token_count, char_start, "
            "char_end) VALUES ('ksec_bulk', 'kno_bulk', :c, 'wld_seedSunnyHollow', 0, 'x', 1, 0, 1)"), {"c": HANA})
        rows: list[dict[str, Any]] = [{"i": f"kch_bulk{i}", "c": HANA, "x": i} for i in range(n)]
        await c.execute(text(
            "INSERT INTO knowledge_chunks(id, source_id, section_id, character_id, world_id, idx, text, token_count, "
            "char_start, char_end) VALUES (:i, 'kno_bulk', 'ksec_bulk', :c, 'wld_seedSunnyHollow', :x, 'filler', 1, 0, 6)"),
            rows)


async def test_too_many_passages_fails_and_keeps_the_others(api: Api) -> None:
    async with api.rt.db.read() as conn:
        seed = int((await conn.execute(text("SELECT count(*) FROM knowledge_chunks WHERE character_id = :c"), {"c": HANA}))
                   .scalar_one())
    await _fill_chunks(api, 2990 - seed)
    src = await add_text(api, "Twenty", "\n\n".join(f"Extra passage {i}." for i in range(20)))
    await settle(api)
    got = await source(api, src["id"])
    assert got["source"]["status"] == "failed" and "3,000" in got["source"]["error"]
    async with api.rt.db.read() as conn:
        total = (await conn.execute(text("SELECT count(*) FROM knowledge_chunks WHERE character_id = :c"), {"c": HANA})).scalar_one()
    assert total == 2990
