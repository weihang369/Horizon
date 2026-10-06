"""Overrun bound and cancelled streams (tasks 6.4, 6.5; budget-caps "Bounded overrun", spend-ledger "Estimate rows")."""

from __future__ import annotations

import asyncio
import json
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
from tests.gwkit import SlowStream, build_gateway, load

CHAT = f"{BASE_URL}/v1/chat/completions"
REQ = ChatRequest(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}], max_tokens=16)


async def ledger(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text("SELECT * FROM usage_records WHERE is_seed = 0"))).mappings())


@respx.mock
async def test_concurrent_preflights_overshoot_at_most_the_estimate_error(api: Api) -> None:
    estimate, actual, cap = 0.004, 0.007, 0.05
    body = load("chat_ok")["body"]

    async def slow(_req: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={**body, "usage": {**body["usage"], "cost": actual}})

    route = respx.post(CHAT).mock(side_effect=slow)
    gw = build_gateway(api, caps=Caps(daily_cap_usd=cap, creation_cap_usd=1, warn_at_pct=80))
    ctx = call_ctx("host", world_id="wld_seedMeridian")
    results = await asyncio.gather(*(gw.chat_complete(REQ, ctx, estimate=estimate) for _ in range(20)),
                                   return_exceptions=True)
    admitted = [r for r in results if not isinstance(r, BaseException)]
    refused = [r for r in results if isinstance(r, ProviderError)]
    assert len(admitted) + len(refused) == 20 and refused and admitted
    assert all(e.code == "daily_budget_exceeded" for e in refused)
    rows = await ledger(api)
    assert route.call_count == len(admitted) == len(rows)  # every refused call made no request
    spent = sum(r["cost_usd"] for r in rows)
    assert spent <= cap + sum(r["cost_usd"] - r["estimated_cost_usd"] for r in rows) + 1e-9
    assert gw.book.total() == 0


def stream_parts(gid: str, n: int) -> list[str]:
    def chunk(i: int) -> str:
        return "data: " + json.dumps({"id": gid, "provider": "DeepSeek", "choices": [{"delta": {"content": f"w{i} "}}]}) + "\n\n"
    return [chunk(i) for i in range(n)]


@respx.mock
async def test_stopped_stream_records_its_estimate(api: Api) -> None:
    parts = [(0.0, p) for p in stream_parts("gen-stop-1", 6)]
    respx.post(CHAT).mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                      stream=SlowStream(parts)))
    corrections: list[str] = []
    gw = build_gateway(api, on_estimate_row=corrections.append)
    agen = gw.chat_stream(REQ, call_ctx("host", world_id="wld_seedMeridian"), estimate=0.0006)
    got = [await agen.__anext__() for _ in range(3)]
    await agen.aclose()  # the user pressed Stop
    assert [c.content for c in got] == ["w0 ", "w1 ", "w2 "]
    (row,) = await ledger(api)
    assert row["cost_source"] == "estimate" and row["cost_usd"] == 0.0006 and row["generation_id"] == "gen-stop-1"
    assert corrections == [row["id"]] and gw.book.total() == 0


@respx.mock
async def test_cancelled_task_still_records(api: Api) -> None:
    parts = [(0.0, p) for p in stream_parts("gen-cancel-1", 3)] + [(30.0, "data: [DONE]\n\n")]
    respx.post(CHAT).mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                      stream=SlowStream(parts)))
    gw = build_gateway(api)
    seen: list[str] = []
    three = asyncio.Event()

    async def consume() -> None:
        async for ch in gw.chat_stream(REQ, call_ctx("reply", world_id="wld_seedMeridian", character_id="chr_seedHana"),
                                       estimate=0.0005):
            seen.append(ch.content or "")
            if len(seen) == 3:
                three.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(three.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await gw.drain_background()
    (row,) = await ledger(api)
    assert row["cost_source"] == "estimate" and row["generation_id"] == "gen-cancel-1" and row["purpose"] == "reply"
    async with api.rt.db.read() as conn:
        spent = (await conn.execute(text("SELECT energy_spent_today FROM characters WHERE id = 'chr_seedHana'"))).scalar_one()
    assert spent >= 5  # D-77: a stopped reply still drains its (estimated) cost
    assert gw.book.total() == 0


@respx.mock
async def test_completed_stream_records_provider_cost(api: Api) -> None:
    from tests.gwkit import response
    respx.post(CHAT).mock(return_value=response("chat_stream_ok"))
    gw = build_gateway(api)
    chunks = [c async for c in gw.chat_stream(REQ, call_ctx("host", world_id="wld_seedMeridian"))]
    assert len(chunks) == 5
    (row,) = await ledger(api)
    assert row["cost_source"] == "provider" and row["cost_usd"] == 0.00042 and row["tokens_cached"] == 1024


async def test_a_hold_released_during_the_spend_read_still_counts(api: Api) -> None:
    """A call commits its row and releases its hold while a preflight awaits the ledger, whose snapshot predates the
    commit: the hold must still be counted, or the call is counted nowhere and one more fits under the cap."""
    gw = build_gateway(api, caps=Caps(daily_cap_usd=0.05, creation_cap_usd=1, warn_at_pct=80))
    other = gw.book.reserve(0.047)

    async def stale_spent_today() -> float:
        gw.book.release(other)  # the other call finishes mid-read
        return 0.0              # but this read's snapshot predates its row

    gw.ledger.spent_today = stale_spent_today
    with pytest.raises(ProviderError) as e:
        await gw._preflight(call_ctx("host", world_id="wld_seedMeridian"), 0.004)
    assert e.value.code == "daily_budget_exceeded"
    assert gw.book.total() == 0
