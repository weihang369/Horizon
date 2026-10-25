"""Cost corrector (task 7.1, spend-ledger "Estimates are corrected exactly once")."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import text

from horizon.domain.timeutil import ms_from_iso, to_iso
from horizon.gateway.chat import ChatRequest
from horizon.gateway.client import BASE_URL
from horizon.gateway.context import call_ctx
from horizon.gateway.meta import GenerationInfo
from horizon.services.corrector import CostCorrector
from horizon.services.energy_writes import EnergyLocks, EnergyParams
from tests.conftest import Api
from tests.gwkit import SlowStream, build_gateway, response

CHAT = f"{BASE_URL}/v1/chat/completions"
GEN = f"{BASE_URL}/v1/generation"
REQ = ChatRequest(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}], max_tokens=16)


async def no_sleep(_s: float) -> None:
    return None


def corrector(api: Api, gw: Any, **kw: Any) -> CostCorrector:
    def params() -> EnergyParams:
        return EnergyParams(now_ms=ms_from_iso(to_iso(api.rt.clock.now())), frozen=False, est_reply_points=4,
                            usd_per_point=0.0001, utc_offset_min=480)
    return CostCorrector(api.rt.db, api.rt.clock, gw.meta.generation, EnergyLocks(), params, sleeper=no_sleep, **kw)


async def stopped_stream(api: Api, gw: Any, *, purpose: str = "host", character: str | None = None, estimate: float) -> None:
    chunk = "data: " + json.dumps({"id": "gen-rec-000001", "provider": "DeepSeek", "choices": [{"delta": {"content": "w "}}]})
    respx.post(CHAT).mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                      stream=SlowStream([(0.0, chunk + "\n\n")] * 3)))
    agen = gw.chat_stream(REQ, call_ctx(purpose, world_id="wld_seedMeridian", character_id=character), estimate=estimate)
    for _ in range(3):
        await agen.__anext__()
    await agen.aclose()


async def the_row(api: Api) -> Any:
    async with api.rt.db.read() as conn:
        return (await conn.execute(text("SELECT * FROM usage_records WHERE is_seed = 0"))).mappings().one()


@respx.mock
async def test_cancelled_stream_is_corrected(api: Api) -> None:
    queued: list[str] = []
    gw = build_gateway(api, on_estimate_row=queued.append)
    await stopped_stream(api, gw, estimate=0.0006)
    respx.get(GEN).mock(return_value=response("generation_ok"))
    cc = corrector(api, gw)
    cc.enqueue(queued[0])
    await cc.idle()
    row = await the_row(api)
    assert row["cost_usd"] == 0.00041 and row["cost_source"] == "provider" and row["estimated_cost_usd"] == 0.0006
    assert row["tokens_cached"] == 1024


@respx.mock
async def test_second_lookup_changes_nothing(api: Api) -> None:
    queued: list[str] = []
    gw = build_gateway(api, on_estimate_row=queued.append)
    await stopped_stream(api, gw, estimate=0.0006)
    respx.get(GEN).mock(return_value=response("generation_ok"))
    cc = corrector(api, gw)
    row = await the_row(api)
    assert await cc.apply(row, GenerationInfo("gen-rec-000001", 0.00041, "DeepSeek", None, None, None)) is True
    assert await cc.apply(row, GenerationInfo("gen-rec-000001", 0.9, "DeepSeek", None, None, None)) is False
    assert (await the_row(api))["cost_usd"] == 0.00041


@respx.mock
async def test_404_404_200_corrects_on_the_third_try(api: Api) -> None:
    queued: list[str] = []
    gw = build_gateway(api, on_estimate_row=queued.append)
    await stopped_stream(api, gw, estimate=0.0006)
    route = respx.get(GEN).mock(side_effect=[response("generation_404"), response("generation_404"), response("generation_ok")])
    sleeps: list[float] = []

    async def record_sleep(s: float) -> None:
        sleeps.append(s)

    cc = corrector(api, gw)
    cc.sleeper = record_sleep
    cc.enqueue(queued[0])
    await cc.idle()
    assert route.call_count == 3 and sleeps == [2.0, 5.0]
    assert (await the_row(api))["cost_source"] == "provider"


@respx.mock
async def test_reply_delta_adjusts_energy(api: Api) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE characters SET energy_current = 500, energy_spent_today = 0, energy_as_of = :a "
                                   "WHERE id = 'chr_seedHana'"), {"a": to_iso(api.rt.clock.now())})
    queued: list[str] = []
    gw = build_gateway(api, on_estimate_row=queued.append)
    await stopped_stream(api, gw, purpose="reply", character="chr_seedHana", estimate=0.0006)  # drains 6 ⚡
    respx.get(GEN).mock(return_value=response("generation_ok"))  # actual 0.00041 → 5 ⚡: refund 1
    cc = corrector(api, gw)
    cc.enqueue(queued[0])
    await cc.idle()
    async with api.rt.db.read() as conn:
        cur, spent = (await conn.execute(text(
            "SELECT energy_current, energy_spent_today FROM characters WHERE id = 'chr_seedHana'"))).one()
    assert (cur, spent) == (pytest.approx(495), pytest.approx(5))


@respx.mock
async def test_missing_key_stops_quietly(api: Api) -> None:
    queued: list[str] = []
    gw = build_gateway(api, on_estimate_row=queued.append)
    await stopped_stream(api, gw, estimate=0.0006)
    gw.core.keys.key = None
    cc = corrector(api, gw)
    cc.enqueue(queued[0])
    await cc.idle()
    assert (await the_row(api))["cost_source"] == "estimate"


async def test_enqueue_after_stop_is_a_no_op(api: Api) -> None:
    """A late shielded record on the way out must not start a task that outlives stop() (factory reset, Windows)."""
    cc = corrector(api, build_gateway(api))
    await cc.stop()
    cc.enqueue("use_late")
    assert cc.pending == 0
