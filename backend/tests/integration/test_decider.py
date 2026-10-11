"""Decider (tasks 8.1, 8.2; decider spec): one call per state, validation with partial fallback, timeouts, fixtures."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import text

from horizon.ai.decider import (
    Choice,
    ChoiceAnswer,
    Decider,
    DeciderFixtures,
    DecisionUnavailable,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
)
from horizon.gateway.client import BASE_URL
from horizon.gateway.context import call_ctx
from tests.conftest import Api
from tests.gwkit import build_gateway, gateway_config, load

URL = f"{BASE_URL}/alpha/decisions"
QS = {
    "route": Choice("Who speaks next?", {"chr_seedAmara": "Amara", "chr_seedHana": "Hana", "none": "nobody"}),
    "gate": Noul("Does this need knowledge?", "yes", "no"),
    "tone": Score("How warm?", ["cold", "neutral", "warm", "glowing"]),
}


def ctx(purpose: str = "route") -> Any:
    return call_ctx(purpose, world_id="wld_seedMeridian", character_id="chr_seedHana")


def decider(api: Api, fixtures: DeciderFixtures | None = None, **timeouts: float) -> tuple[Decider, Any]:
    gw = build_gateway(api)
    cfg = gateway_config()
    t = replace(cfg.timeouts, decision={**cfg.timeouts.decision, **timeouts}) if timeouts else cfg.timeouts
    return Decider(gw.decide, t, fixtures), gw


async def ledger(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text("SELECT * FROM usage_records WHERE is_seed = 0"))).mappings())


async def fallback() -> dict[str, Any]:
    return {"route": ChoiceAnswer("chr_seedHana"), "gate": NoulAnswer(1.0), "tone": ScoreAnswer(1.0)}


@respx.mock
async def test_batched_questions_one_call(api: Api) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=load("decisions_ok")["body"]))
    d, _ = decider(api)
    r = await d.ask({"last": "hi"}, QS, ctx(), purpose="route")
    assert route.call_count == 1
    assert set(json.loads(route.calls.last.request.content)["questions"]) == {"route", "gate", "tone"}
    assert r.answers["route"] == ChoiceAnswer("chr_seedAmara", 0.82, {"chr_seedAmara": 0.82, "chr_seedHana": 0.15, "none": 0.03})
    assert r.answers["gate"] == NoulAnswer(0.71) and isinstance(r.answers["tone"], ScoreAnswer)
    assert all(a.source == "jev" for a in r.answers.values())
    (row,) = await ledger(api)
    assert row["category"] == "decision" and row["purpose"] == "route" and row["model"] == "typesafe/jev-1.13"


@respx.mock
async def test_over_budget_sends_nothing(api: Api) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=load("decisions_ok")["body"]))
    d, _ = decider(api)
    huge = {"text": "x" * 93_000}  # 31,000 tokens at 3 bytes/token: over the 30k check
    r = await d.ask(huge, QS, ctx(), purpose="route", fallback=fallback)
    assert route.call_count == 0 and r.failure and all(a.source == "fallback" for a in r.answers.values())
    with pytest.raises(DecisionUnavailable):
        await d.ask(huge, QS, ctx(), purpose="route")


@respx.mock
async def test_one_bad_answer_falls_back_alone(api: Api) -> None:
    body = load("decisions_ok")["body"]
    bad = {**body, "answers": {**body["answers"], "route": {"choice": "chr_notOffered", "confidence": 0.9}}}
    respx.post(URL).mock(return_value=httpx.Response(200, json=bad))
    d, _ = decider(api)
    r = await d.ask({}, QS, ctx(), purpose="route", fallback=fallback)
    assert r.answers["route"] == ChoiceAnswer("chr_seedHana", source="fallback")
    assert r.answers["gate"].source == "jev" and r.answers["gate"] == NoulAnswer(0.71)


@respx.mock
async def test_late_answer_is_discarded_but_recorded(api: Api) -> None:
    async def slow(_r: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.65)
        return httpx.Response(200, json=load("decisions_ok")["body"])

    respx.post(URL).mock(side_effect=slow)
    d, _ = decider(api, route=0.4)
    loop = asyncio.get_running_loop()
    started = loop.time()
    r = await d.ask({}, QS, ctx(), purpose="route", fallback=fallback)
    assert loop.time() - started < 0.6
    assert r.failure == "timeout" and r.answers["route"].source == "fallback"
    assert await ledger(api) == []
    await d.idle()
    (row,) = await ledger(api)
    assert row["category"] == "decision" and row["cost_usd"] == 0.00003528


@respx.mock
async def test_no_fallback_raises(api: Api) -> None:
    respx.post(URL).mock(return_value=httpx.Response(502, json={"error": {"message": "down"}}))
    d, _ = decider(api)
    with pytest.raises(DecisionUnavailable):
        await d.ask({}, QS, ctx(), purpose="route")


@respx.mock
async def test_route_decision_does_not_drain(api: Api) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json=load("decisions_ok")["body"]))
    async with api.rt.db.read() as conn:
        before = (await conn.execute(text("SELECT energy_current, energy_spent_today FROM characters WHERE id = 'chr_seedHana'"))).one()
    d, _ = decider(api)
    await d.ask({}, {"gate": QS["gate"]}, ctx("route"), purpose="route")
    async with api.rt.db.read() as conn:
        after = (await conn.execute(text("SELECT energy_current, energy_spent_today FROM characters WHERE id = 'chr_seedHana'"))).one()
    assert tuple(before) == tuple(after)
    assert [r["purpose"] for r in await ledger(api)] == ["route"]


@respx.mock
async def test_fixture_answer_without_a_request(api: Api) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=load("decisions_ok")["body"]))
    fx = DeciderFixtures()
    fx.set("route", "route", ChoiceAnswer("chr_seedAmara"))
    d, _ = decider(api, fx)
    r = await d.ask({}, {"route": QS["route"]}, ctx(), purpose="route")
    assert r.answers["route"] == ChoiceAnswer("chr_seedAmara", source="fixture")
    assert route.call_count == 0 and await ledger(api) == []


async def test_context_must_match_purpose(api: Api) -> None:
    d, _ = decider(api)
    with pytest.raises(ValueError):
        await d.ask({}, QS, ctx("reaction"), purpose="route")


# ── 8.2: per-purpose timeouts come from config, overridable per call ──
def test_timeouts_from_config() -> None:
    t = gateway_config().timeouts
    assert (t.for_decision("route"), t.for_decision("turn_plan"), t.for_decision("follow_plan"),
            t.for_decision("debate_plan")) == (0.4, 0.7, 0.4, 0.5)
    assert (t.for_decision("guardrail"), t.for_decision("guardrail_prompt"), t.for_decision("reaction"),
            t.for_decision("face_check")) == (0.7, 1.5, 1.5, 1.5)
    assert t.for_decision("importance") == 3.0  # the default
    assert not {"gate", "rerank", "emotion"} & set(t.decision)  # removed with their purposes (design D9, D10)


@respx.mock
async def test_config_and_per_call_override_change_the_timeout(api: Api) -> None:
    async def slow(_r: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.3)
        return httpx.Response(200, json=load("decisions_ok")["body"])

    respx.post(URL).mock(side_effect=slow)
    d, _ = decider(api, route=0.05)
    assert (await d.ask({}, QS, ctx(), purpose="route", fallback=fallback)).failure == "timeout"
    ok = await d.ask({}, QS, ctx(), purpose="route", fallback=fallback, timeout_ms=2000)
    assert ok.failure is None and ok.answers["route"].source == "jev"
    await d.idle()


# ── 1.8: the purpose cleanup ──
def test_removed_purposes_and_eval_judge() -> None:
    for gone in ("gate", "rerank", "emotion", "watch_end"):
        with pytest.raises(ValueError):
            call_ctx(gone)
    assert call_ctx("eval_judge").category == "decision"


# ── 1.10: the estimate counts the state once (group A A1: Jev bills the state once per request) ──
async def test_decision_estimate_counts_the_state_once(api: Api) -> None:
    from horizon.ai.decider import wire_question
    from horizon.domain.pricing import count_tokens

    gw = build_gateway(api)
    state = {"quoted_recent": ["word " * 360]}           # ≈ 600 tokens at 3 bytes/token
    one = {"q0": wire_question(QS["gate"])}
    eight = {f"q{i}": wire_question(QS["gate"]) for i in range(8)}
    per_q = count_tokens(json.dumps(one["q0"], ensure_ascii=False))
    price = gw.prices.decision.input_per_m / 1e6
    assert gw.decision_estimate(state, eight) - gw.decision_estimate(state, one) == pytest.approx(7 * per_q * price)
    st = count_tokens(json.dumps(state, ensure_ascii=False))
    assert gw.decision_estimate(state, eight) == pytest.approx((st + 8 * per_q) * price)


# ── ai-foundation 2.2 (design D6): how a decision ended is in its ledger row ──
@respx.mock
async def test_late_and_cancelled_decisions_are_marked(api: Api) -> None:
    async def slow(_r: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.3)
        return httpx.Response(200, json=load("decisions_ok")["body"])

    respx.post(URL).mock(side_effect=slow)
    d, _ = decider(api, route=0.05)
    r = await d.ask({}, QS, ctx(), purpose="route", fallback=fallback)
    assert r.failure == "timeout"
    call = d.start({}, QS, ctx(), purpose="route", fallback=fallback)
    call.cancel()
    await d.idle()
    rows = await ledger(api)
    assert sorted(r["finish_reason"] for r in rows) == ["cancelled", "late"]


@respx.mock
async def test_on_time_decision_is_marked(api: Api) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json=load("decisions_ok")["body"]))
    d, _ = decider(api)
    await d.ask({}, QS, ctx(), purpose="route")
    (row,) = await ledger(api)
    assert row["finish_reason"] == "on_time"
