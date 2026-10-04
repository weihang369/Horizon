"""Paid-call pipeline (task 6.3, provider-gateway "Paid-call pipeline", budget-caps "Daily cap", "Warning on crossing")."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import text

from horizon.gateway.chat import ChatRequest
from horizon.gateway.client import BASE_URL
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.gateway.pipeline import Caps
from tests.conftest import Api
from tests.gwkit import FakeKeys, build_gateway, load

CHAT = f"{BASE_URL}/v1/chat/completions"
REQ = ChatRequest(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}], max_tokens=16)
CTX = call_ctx("host", world_id="wld_seedMeridian")


def chat_ok(cost: float) -> httpx.Response:
    body = load("chat_ok")["body"]
    return httpx.Response(200, json={**body, "usage": {**body["usage"], "cost": cost}})


async def spend(api: Api, usd: float) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text(
            "INSERT INTO usage_records(id, at, local_day, category, cost_usd, cost_source, counts_to_creation_cap, is_seed) "
            "VALUES (:id, '2026-10-03T02:00:00.000Z', '2026-10-03', 'chat', :c, 'provider', 0, 0)"),
            {"id": f"use_pre{int(usd * 1e6)}", "c": usd})


async def new_rows(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text("SELECT * FROM usage_records WHERE is_seed = 0 AND id NOT LIKE 'use_pre%'"))).mappings())


@respx.mock
async def test_refused_before_spend(api: Api) -> None:
    route = respx.post(CHAT).mock(return_value=chat_ok(0.0001))
    events: list[Any] = []
    gw = build_gateway(api, events=events)
    await spend(api, 0.999)
    with pytest.raises(ProviderError) as e:
        await gw.chat_complete(REQ, CTX, estimate=0.002)
    assert e.value.code == "daily_budget_exceeded"
    assert route.call_count == 0 and await new_rows(api) == [] and gw.book.total() == 0
    (ev,) = events
    assert ev == {"type": "budget.reached", "scope": "daily", "spentUsd": 0.999, "capUsd": 1.0}
    api.rt.schema.check("GlobalEvent", ev)


@respx.mock
async def test_creation_cap_refuses_before_spend(api: Api) -> None:
    route = respx.post(f"{BASE_URL}/v1/images").mock(return_value=httpx.Response(200, json=load("images_ok")["body"]))
    gw = build_gateway(api)
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text(
            "INSERT INTO usage_records(id, at, local_day, category, cost_usd, cost_source, counts_to_creation_cap, is_seed, character_id) "
            "VALUES ('use_preCreation', '2026-10-02T02:00:00.000Z', '2026-10-02', 'image', 0.59, 'provider', 1, 0, 'chr_seedHana')"))
    ctx = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_seedHana", creation=True)
    with pytest.raises(ProviderError) as e:
        await gw.generate_image(ctx, model="bytedance-seed/seedream-5-0-flash", prompt="p")
    assert e.value.code == "creation_budget_exceeded" and route.call_count == 0


@respx.mock
async def test_success_records_and_releases(api: Api) -> None:
    respx.post(CHAT).mock(return_value=chat_ok(0.00042))
    gw = build_gateway(api)
    r = await gw.chat_complete(REQ, CTX)
    assert r.content == "ok" and gw.book.total() == 0
    (row,) = await new_rows(api)
    assert row["cost_usd"] == 0.00042 and row["cost_source"] == "provider" and row["purpose"] == "host"
    assert row["estimated_cost_usd"] > 0 and row["generation_id"] == "gen-rec-000002"


@respx.mock
async def test_reservation_released_on_provider_error(api: Api) -> None:
    respx.post(CHAT).mock(return_value=httpx.Response(500, json={"error": {"message": "boom"}}))
    gw = build_gateway(api)
    with pytest.raises(ProviderError):
        await gw.chat_complete(REQ, CTX, estimate=0.002)
    assert gw.book.total() == 0 and await new_rows(api) == []  # an error status was never billed


@respx.mock
async def test_crossing_publishes_exactly_one_warning(api: Api) -> None:
    respx.post(CHAT).mock(return_value=chat_ok(0.02))
    events: list[Any] = []
    gw = build_gateway(api, events=events)
    await spend(api, 0.79)
    await gw.chat_complete(REQ, CTX, estimate=0.02)
    await gw.chat_complete(REQ, CTX, estimate=0.02)
    warnings = [e for e in events if e["type"] == "budget.warning"]
    assert warnings == [{"type": "budget.warning", "scope": "daily", "spentUsd": 0.81, "capUsd": 1.0}]
    api.rt.schema.check("GlobalEvent", warnings[0])


@respx.mock
async def test_failing_hook_still_returns(api: Api) -> None:
    respx.post(CHAT).mock(return_value=chat_ok(0.0001))
    seen: list[Any] = []

    def hook(ctx: Any, summary: Any, outcome: Any) -> None:
        seen.append((ctx.purpose, summary, outcome))
        raise RuntimeError("evaluation store down")

    gw = build_gateway(api, on_call=hook)
    assert (await gw.chat_complete(REQ, CTX)).content == "ok"
    assert seen and seen[0][0] == "host" and seen[0][2]["costSource"] == "provider"


@respx.mock
async def test_missing_key_wins_over_caps(api: Api) -> None:
    gw = build_gateway(api, keys=FakeKeys(None), caps=Caps(0.0, 0.0, 80))
    with pytest.raises(ProviderError) as e:
        await gw.chat_complete(REQ, CTX)
    assert e.value.code == "missing_key"


@respx.mock
async def test_embed_seventy_texts_three_rows(api: Api) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        import json
        n = len(json.loads(request.content)["input"])
        return httpx.Response(200, json={"id": f"gen-e{n}", "data": [{"index": i, "embedding": [float(i)]} for i in range(n)],
                                         "usage": {"prompt_tokens": n, "cost": 0.000001}})

    respx.post(f"{BASE_URL}/v1/embeddings").mock(side_effect=answer)
    gw = build_gateway(api)
    vecs = await gw.embed([str(i) for i in range(70)], call_ctx("embed_doc", world_id="wld_seedMeridian"),
                          model="qwen/qwen3-embedding-8b")
    assert len(vecs) == 70
    assert [r["category"] for r in await new_rows(api)] == ["embedding"] * 3
