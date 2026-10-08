"""The Embedder port and the scripted embedding source (knowledge-memory-storage tasks 2.1–2.2; embedding-spaces spec,
provider-gateway "Scripted embedding source")."""

from __future__ import annotations

import math
from typing import Any

import pytest
from sqlalchemy import text

from horizon.ai.embedder import Batch, BatchHooks, HashEmbedder, QwenEmbedder, fit, request_text
from horizon.ai.scripted.ports import AiDeps
from horizon.db.spaces import DEFAULT_SPACE
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.gateway.fake import FakeOpenRouter
from horizon.gateway.pipeline import Caps
from tests.conftest import Api
from tests.gwkit import FakeKeys, block_network, build_gateway

CTX = call_ctx("embed_doc", world_id="wld_seedSunnyHollow", character_id="chr_seedHana")


async def rows(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text(
            "SELECT * FROM usage_records WHERE is_seed = 0 AND category = 'embedding' ORDER BY at, id"))).mappings())


def deps(api: Api, gw: Any) -> AiDeps:
    rt = api.rt
    return AiDeps(gateway=lambda: gw, decider=lambda: None, prices=rt.prices, timing=rt.runtime_cfg.timing,
                  clock=lambda: rt.clock)


def norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


# ── 2.1 the scripted source ──
async def test_scripted_batch_is_billed_and_offline(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = block_network(monkeypatch)
    gw = build_gateway(api, transport=FakeOpenRouter().transport())
    out = await HashEmbedder(deps(api, gw)).embed(["# Soups", "Miso first.", "Then tofu."], kind="document",
                                                  space=DEFAULT_SPACE, ctx=CTX)
    assert len(out.vectors) == 3 and all(len(v) == DEFAULT_SPACE.dims for v in out.vectors)
    assert all(abs(norm(v) - 1) < 1e-9 for v in out.vectors)
    [row] = await rows(api)
    assert row["provider"] == "scripted" and row["model"] == DEFAULT_SPACE.model and row["purpose"] == "embed_doc"
    assert row["tokens_in"] > 0 and row["cost_source"] == "provider"
    assert attempts == []


async def test_scripted_vectors_are_deterministic(api: Api) -> None:
    gw = build_gateway(api, transport=FakeOpenRouter().transport())
    a = await HashEmbedder(deps(api, gw)).embed(["Steep for three minutes."], kind="document", space=DEFAULT_SPACE, ctx=CTX)
    b = await HashEmbedder(deps(api, gw)).embed(["Steep for three minutes."], kind="document", space=DEFAULT_SPACE, ctx=CTX)
    assert a.vectors == b.vectors


async def test_scripted_cap_refusal_runs_no_hooks(api: Api) -> None:
    gw = build_gateway(api, transport=FakeOpenRouter().transport(),
                       caps=Caps(daily_cap_usd=0.0, creation_cap_usd=0.6, warn_at_pct=80))
    called: list[str] = []

    async def before() -> None:
        called.append("before")

    async def commit(_conn: Any, _row: str, _b: Batch) -> None:
        called.append("commit")

    with pytest.raises(ProviderError) as e:
        await HashEmbedder(deps(api, gw)).embed(["x"], kind="document", space=DEFAULT_SPACE, ctx=CTX,
                                                hooks=lambda b: BatchHooks(before, commit))
    assert e.value.code == "daily_budget_exceeded"
    assert called == [] and await rows(api) == []


async def test_hooks_store_vectors_in_the_ledger_transaction(api: Api) -> None:
    gw = build_gateway(api, transport=FakeOpenRouter().transport())
    seen: list[tuple[list[int], int, bool]] = []

    async def commit(conn: Any, row_id: str, b: Batch) -> None:
        has_row = (await conn.execute(text("SELECT count(*) FROM usage_records WHERE id = :i"), {"i": row_id})).scalar_one()
        seen.append((b.indices, len(b.vectors), bool(has_row)))

    await QwenEmbedder(deps(api, gw)).embed([f"t{i}" for i in range(40)], kind="document", space=DEFAULT_SPACE, ctx=CTX,
                                            hooks=lambda b: BatchHooks(None, commit))
    assert [(len(i), n, r) for i, n, r in seen] == [(32, 32, True), (8, 8, True)]


# ── 2.2 the naive embedder ──
async def test_the_space_model_is_billed_whatever_the_setting(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = build_gateway(api, transport=fake.transport())
    r = await api.client.patch("/api/v1/settings", json={"models": {"embedding": "some/other-embedder"}})
    assert r.status_code == 200, r.text
    await QwenEmbedder(deps(api, gw)).embed(["Rice first."], kind="document", space=DEFAULT_SPACE, ctx=CTX)
    import json

    body = json.loads(fake.requests[-1].content)
    assert body["model"] == DEFAULT_SPACE.model and body["dimensions"] == DEFAULT_SPACE.dims
    [row] = await rows(api)
    assert row["model"] == DEFAULT_SPACE.model


async def test_query_carries_the_instruction_and_passages_do_not(api: Api) -> None:
    import json

    fake = FakeOpenRouter()
    gw = build_gateway(api, transport=fake.transport())
    emb = QwenEmbedder(deps(api, gw))
    await emb.embed(["What about burnout?"], kind="query", space=DEFAULT_SPACE, ctx=call_ctx("query_embed"))
    await emb.embed(["Burnout passage."], kind="document", space=DEFAULT_SPACE, ctx=CTX)
    q, d = (json.loads(r.content)["input"] for r in fake.requests[-2:])
    assert q == [f"Instruct: {DEFAULT_SPACE.query_instruction}\nQuery: What about burnout?"]
    assert d == ["Burnout passage."]
    assert request_text("x", "query", DEFAULT_SPACE).startswith("Instruct: ")


async def test_long_vectors_are_cut_and_rescaled(api: Api) -> None:
    fake = FakeOpenRouter()
    fake.embed_dims = 4096
    gw = build_gateway(api, transport=fake.transport())
    out = await QwenEmbedder(deps(api, gw)).embed(["a", "b"], kind="document", space=DEFAULT_SPACE, ctx=CTX)
    assert [len(v) for v in out.vectors] == [1024, 1024]
    assert all(abs(norm(v) - 1) < 1e-9 for v in out.vectors)


async def test_short_vectors_fail_the_batch_and_store_nothing(api: Api) -> None:
    fake = FakeOpenRouter()
    fake.embed_dims = 512
    gw = build_gateway(api, transport=fake.transport())
    stored: list[int] = []

    async def commit(_c: Any, _r: str, b: Batch) -> None:
        stored.extend(b.indices)

    with pytest.raises(ProviderError) as e:
        await QwenEmbedder(deps(api, gw)).embed(["a"], kind="document", space=DEFAULT_SPACE, ctx=CTX,
                                                hooks=lambda b: BatchHooks(None, commit))
    assert "malformed" in e.value.message
    assert stored == []
    assert len(await rows(api)) == 1  # the provider charged: the row is kept, the vectors are not


async def test_repeated_query_is_served_from_the_cache(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = build_gateway(api, transport=fake.transport())
    emb = QwenEmbedder(deps(api, gw))
    ctx = call_ctx("query_embed", world_id="wld_seedMeridian")
    a = await emb.embed(["Same question?"], kind="query", space=DEFAULT_SPACE, ctx=ctx)
    b = await emb.embed(["Same question?"], kind="query", space=DEFAULT_SPACE, ctx=ctx)
    assert fake.counts["embeddings"] == 1 and len(await rows(api)) == 1
    assert a.vectors == b.vectors and b.cached == [0]
    await emb.embed(["Same question?"], kind="document", space=DEFAULT_SPACE, ctx=CTX)  # another form: a new input
    assert fake.counts["embeddings"] == 2


async def test_no_key_means_no_request_and_no_row(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = build_gateway(api, keys=FakeKeys(None), transport=fake.transport())
    for emb in (QwenEmbedder(deps(api, gw)), HashEmbedder(deps(api, gw))):
        with pytest.raises(ProviderError) as e:
            await emb.embed(["x"], kind="document", space=DEFAULT_SPACE, ctx=CTX)
        assert e.value.code == "missing_key"
    assert fake.counts["embeddings"] == 0 and await rows(api) == []


async def test_seventy_passages_three_rows_no_drain(api: Api) -> None:
    async with api.rt.db.read() as conn:
        before = (await conn.execute(text("SELECT energy_current FROM characters WHERE id = 'chr_seedHana'"))).scalar_one()
    gw = build_gateway(api, transport=FakeOpenRouter().transport())
    await QwenEmbedder(deps(api, gw)).embed([f"passage {i}" for i in range(70)], kind="document", space=DEFAULT_SPACE,
                                            ctx=CTX)
    got = await rows(api)
    assert [r["purpose"] for r in got] == ["embed_doc"] * 3
    assert all(r["character_id"] == "chr_seedHana" and r["energy_points"] in (None, 0) for r in got)
    async with api.rt.db.read() as conn:
        after = (await conn.execute(text("SELECT energy_current FROM characters WHERE id = 'chr_seedHana'"))).scalar_one()
    assert after == before


def test_fit_refuses_non_finite() -> None:
    with pytest.raises(ProviderError):
        fit([1.0, float("nan"), 0.0], 3)
    assert fit([3.0, 4.0, 99.0], 2) == [0.6, 0.8]
