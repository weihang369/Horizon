"""The header space and `horizon space build` (doc 10 K3; rag design D4, D5, tasks 2.1–2.5; embedding-spaces "Queries and
documents are embedded differently", "Repeated text is not embedded twice", "The default space for new installs",
"A build copies vectors that would not change"; local-backend "Command-line interface")."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from sqlalchemy import text

from horizon.ai.embedder import PieceMeta, QwenEmbedder, request_text
from horizon.ai.scripted.ports import AiDeps
from horizon.db import spaces
from horizon.db.spaces import DEFAULT_SPACE, PLAIN_SPACE
from horizon.gateway.context import call_ctx
from horizon.gateway.fake import FakeOpenRouter
from horizon.services.knowledge import space_cli
from horizon.services.knowledge.build import build_space
from tests.conftest import Api
from tests.gwkit import build_gateway
from tests.knowledge.kit import API, add_text, seed_before_d110, settle

HANA = "chr_seedHana"
SEED_SRC = "kno_seedAmara1"


def deps(api: Api, gw: Any) -> AiDeps:
    rt = api.rt
    return AiDeps(gateway=lambda: gw, decider=lambda: None, prices=rt.prices, timing=rt.runtime_cfg.timing,
                  clock=lambda: rt.clock)


def inputs(fake: FakeOpenRouter) -> list[list[str]]:
    return [json.loads(r.content)["input"] for r in fake.requests if r.url.path.endswith("/embeddings")]


async def ledger(api: Api, purpose: str) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text(
            "SELECT * FROM usage_records WHERE is_seed = 0 AND purpose = :p ORDER BY at, id"), {"p": purpose})).mappings())


# ── 2.1 the header ──
def test_the_four_header_cases() -> None:
    sp = DEFAULT_SPACE
    head = PieceMeta(title="Shift Fatigue Review.pdf", heading="Long shift blocks", locator="p. 3")
    assert request_text("Staff working…", "knowledge", sp, head) == "Shift Fatigue Review\nLong shift blocks\n\nStaff working…"
    seed = PieceMeta(title="ED triage guidelines.PDF", heading="p. 2", locator="p. 2")      # heading == locator
    assert request_text("Triage starts…", "knowledge", sp, seed) == "ED triage guidelines\n\nTriage starts…"
    bare = PieceMeta(title="notes.md", heading=None, locator="¶ 3")
    assert request_text("A note.", "knowledge", sp, bare) == "notes\n\nA note."
    assert request_text("Kai likes rain.", "document", sp) == "Kai likes rain."                  # memories stay plain
    assert request_text("A note.", "knowledge", PLAIN_SPACE, bare) == "A note."                    # no template: plain
    braces = PieceMeta(title="{text} guide.txt", heading="{title}", locator="§ x")
    assert request_text("{heading}", "knowledge", sp, braces) == "{text} guide\n{title}\n\n{heading}"


def test_the_default_space() -> None:
    assert DEFAULT_SPACE.id == "qwen3-emb-8b@1024+h" and DEFAULT_SPACE.dims == 1024
    assert DEFAULT_SPACE.query_instruction == "Given a chat message, retrieve passages that help answer it"
    assert DEFAULT_SPACE.doc_template == "{title}\n{heading}\n\n{text}"
    assert spaces.vec_tables(DEFAULT_SPACE.id) == ("memory_vec__qwen3_emb_8b_1024_h", "knowledge_vec__qwen3_emb_8b_1024_h")


# ── 2.2 the cache and in-flight de-duplication ──
async def test_two_concurrent_embeds_of_one_message_make_one_call(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = build_gateway(api, transport=fake.transport())
    emb = QwenEmbedder(deps(api, gw))
    ctx = call_ctx("query_embed", world_id="wld_seedMeridian", character_id="chr_seedAmara")
    release = fake.park_embedding(1)
    a = asyncio.ensure_future(emb.embed(["And nights?"], kind="query", space=DEFAULT_SPACE, ctx=ctx))
    await asyncio.wait_for(fake.embed_parked.wait(), 5)
    b = asyncio.ensure_future(emb.embed(["And nights?"], kind="query", space=DEFAULT_SPACE, ctx=ctx))
    await asyncio.sleep(0.05)
    release.set()
    va, vb = await a, await b
    assert va.vectors == vb.vectors and vb.cached == [0]
    assert fake.counts["embeddings"] == 1
    assert len(await ledger(api, "query_embed")) == 1


async def test_a_failed_first_call_lets_the_waiter_send(api: Api) -> None:
    import httpx

    fake = FakeOpenRouter()
    gw = build_gateway(api, transport=fake.transport())
    emb = QwenEmbedder(deps(api, gw))
    ctx = call_ctx("query_embed", world_id="wld_seedMeridian")
    release = fake.park_embedding(1)
    fake.queued.append(httpx.Response(503, json={"error": {"message": "unavailable"}}))
    a = asyncio.ensure_future(emb.embed(["Why?"], kind="query", space=DEFAULT_SPACE, ctx=ctx))
    await asyncio.wait_for(fake.embed_parked.wait(), 5)
    b = asyncio.ensure_future(emb.embed(["Why?"], kind="query", space=DEFAULT_SPACE, ctx=ctx))
    await asyncio.sleep(0.05)
    release.set()
    with pytest.raises(Exception):  # noqa: B017 - the provider error, as before
        await a
    out = await b
    assert len(out.vectors) == 1 and fake.counts["embeddings"] == 2


async def test_a_changed_instruction_misses_the_cache(api: Api) -> None:
    from dataclasses import replace

    fake = FakeOpenRouter()
    gw = build_gateway(api, transport=fake.transport())
    emb = QwenEmbedder(deps(api, gw))
    ctx = call_ctx("query_embed", world_id="wld_seedMeridian")
    await emb.embed(["And nights?"], kind="query", space=DEFAULT_SPACE, ctx=ctx)
    await emb.embed(["And nights?"], kind="query", space=DEFAULT_SPACE, ctx=ctx)
    assert fake.counts["embeddings"] == 1
    other = replace(DEFAULT_SPACE, query_instruction="Given a question, retrieve passages that answer it")
    await emb.embed(["And nights?"], kind="query", space=other, ctx=ctx)
    assert fake.counts["embeddings"] == 2


# ── 2.3 the default space for new installs ──
async def test_a_fresh_install_starts_in_the_header_space(api: Api) -> None:
    assert api.rt.space_id == DEFAULT_SPACE.id
    async with api.rt.db.read() as conn:
        sp = await spaces.active(conn)
        names = {r[0] for r in (await conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))).all()}
    assert sp == DEFAULT_SPACE
    assert set(spaces.vec_tables(DEFAULT_SPACE.id)) <= names


async def test_an_existing_install_keeps_its_space(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "old"
    first: Api = await make_api(data_dir=data)
    await first.set_key()
    await build_space(first.rt, PLAIN_SPACE)           # an install from before M12
    await first.rt.stop()
    second: Api = await make_api(data_dir=data)
    assert second.rt.space_id == PLAIN_SPACE.id
    async with second.rt.db.read() as conn:
        assert (await spaces.active(conn)) == PLAIN_SPACE


async def test_seed_indexing_embeds_with_the_header(api: Api) -> None:
    await seed_before_d110(api)
    await api.set_key()
    r = await api.client.post(f"{API}/_test/ai-profile", json={"profile": "scripted", "overrides": {"embedder": "naive"}})
    assert r.status_code == 204
    assert (await api.client.post(f"{API}/knowledge/{SEED_SRC}/reindex")).status_code == 200
    await settle(api)
    fake = api.rt.fake
    assert fake is not None
    [sent] = inputs(fake)
    assert all(t.startswith("Meridian Shift Fatigue Review 2025\n") for t in sent)   # the title heads every piece
    [row] = await ledger(api, "embed_doc")
    assert row["character_id"] == "chr_seedAmara"


# ── 2.4 the build copies what wouldn't change ──
async def _plain_with_memories(api: Api, n: int) -> None:
    """An install on the plain space with `n` memories that have vectors there, and one indexed user source."""
    await seed_before_d110(api)
    await api.set_key()
    r = await api.client.post(f"{API}/_test/ai-profile", json={"profile": "scripted", "overrides": {"embedder": "naive"}})
    assert r.status_code == 204
    await build_space(api.rt, PLAIN_SPACE)
    mem, _ = spaces.vec_tables(PLAIN_SPACE.id)
    async with api.rt.db.write() as tx:
        for i in range(n):
            res = await tx.conn.execute(text(
                "INSERT INTO memory_items (id, character_id, world_id, kind, text, importance, created_at, is_seed) "
                "VALUES (:id, :c, 'wld_seedSunnyHollow', 'fact', :t, 0.5, :at, 0)"),
                {"id": f"mem_test{i:03d}", "c": HANA, "t": f"Memory {i} about rice.", "at": api.rt.now_iso()})
            await tx.conn.execute(text(f"INSERT INTO {mem}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                                  {"r": res.lastrowid, "c": HANA, "e": sqlite_vec.serialize_float32([1.0] + [0.0] * 1023)})
    await add_text(api, "Rice notes.md", "# Washing\n\nWash the rice twice.\n\n# Soaking\n\nSoak it for half an hour.")
    await settle(api)


async def test_building_the_header_space_copies_memories_and_reembeds_pieces(api: Api) -> None:
    await _plain_with_memories(api, 40)
    fake = api.rt.fake
    assert fake is not None
    docs_before = len(await ledger(api, "embed_doc"))
    sent_before = len(inputs(fake))
    report = await build_space(api.rt, DEFAULT_SPACE)
    assert report.copied_memories == 40 and report.memories == 0
    assert report.chunks == 2 and report.copied_chunks == 0
    rows = await ledger(api, "embed_doc")
    assert len(rows) == docs_before + 1 and rows[-1]["character_id"] == HANA      # the pieces, under the header
    new = [t for batch in inputs(fake)[sent_before:] for t in batch]
    assert new == ["Rice notes\nWashing\n\n# Washing\n\nWash the rice twice.",
                   "Rice notes\nSoaking\n\n# Soaking\n\nSoak it for half an hour."]
    mem, _ = spaces.vec_tables(DEFAULT_SPACE.id)
    async with api.rt.db.read() as conn:
        assert (await conn.execute(text(f"SELECT count(*) FROM {mem}"))).scalar_one() == 40
    assert api.rt.space_id == DEFAULT_SPACE.id


async def test_the_build_fills_only_the_kinds_asked(api: Api) -> None:
    await _plain_with_memories(api, 3)
    report = await build_space(api.rt, DEFAULT_SPACE, kinds=("memory",))
    assert (report.chunks, report.copied_memories) == (0, 3)
    with pytest.raises(ValueError):
        await build_space(api.rt, PLAIN_SPACE, kinds=("messages",))


# ── 2.5 the command ──
async def test_space_build_declined_spends_nothing(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "declined"
    first: Api = await make_api(data_dir=data)
    await seed_before_d110(first)
    await first.set_key()
    cfg = first.rt.cfg
    await first.rt.stop()
    lines: list[str] = []
    rc = await asyncio.to_thread(space_cli.run, cfg, PLAIN_SPACE.id, False, ask=lambda _q: "n", out=lines.append)
    assert rc == 1 and "nothing was spent" in lines[-1]
    assert any("embed 0 passages" in ln for ln in lines)
    second: Api = await make_api(data_dir=data)
    assert second.rt.space_id == DEFAULT_SPACE.id
    assert await ledger(second, "embed_doc") == []


async def test_space_build_starts_nothing_that_could_spend(make_api: Any, tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit C-P1-6: the command's start-up recovers no job, re-embeds nothing, runs no memory pass and no cost
    correction before the estimate and the "N" (the next real start does them)."""
    from horizon.runtime import Runtime
    from horizon.services.corrector import CostCorrector
    from horizon.services.jobs.scheduler import JobScheduler

    data = tmp_path / "offline"
    first: Api = await make_api(data_dir=data)
    await first.set_key()
    cfg = first.rt.cfg
    await first.rt.stop()
    started: list[str] = []

    async def mark(name: str) -> None:
        started.append(name)
    monkeypatch.setattr(JobScheduler, "recover", lambda self: mark("jobs"))
    monkeypatch.setattr(Runtime, "_recover_m5", lambda self: mark("re-embed"))
    monkeypatch.setattr(CostCorrector, "scan", lambda self: mark("corrector"))
    rc = await asyncio.to_thread(space_cli.run, cfg, PLAIN_SPACE.id, False, ask=lambda _q: "n", out=lambda _l: None)
    assert rc == 1 and started == []


async def test_space_build_yes_on_the_fake_provider(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "yes"
    first: Api = await make_api(data_dir=data)
    await first.set_key()
    cfg = first.rt.cfg
    await first.rt.stop()
    lines: list[str] = []
    rc = await asyncio.to_thread(space_cli.run, cfg, PLAIN_SPACE.id, True, out=lines.append)
    assert rc == 0 and f"{PLAIN_SPACE.id} is active" in lines[-1]
    second: Api = await make_api(data_dir=data)
    assert second.rt.space_id == PLAIN_SPACE.id


async def test_space_build_refuses_while_the_server_runs(api: Api) -> None:
    lines: list[str] = []
    rc = await asyncio.to_thread(space_cli.run, api.rt.cfg, None, True, out=lines.append)
    assert rc == 2 and "a backend is running" in lines[-1]
    assert api.rt.space_id == DEFAULT_SPACE.id


def test_space_build_names_unknown_spaces(tmp_path: Path) -> None:
    from horizon.config import load_config

    cfg = load_config()
    lines: list[str] = []
    assert space_cli.run(cfg, "nope@1", True, out=lines.append) == 2 and "known:" in lines[-1]
