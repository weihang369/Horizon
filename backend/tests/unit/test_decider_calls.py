"""The Decider's start/by/final/cancel on the virtual clock, the size check and the 429 policy (decider spec;
ai-foundation design D4, D5, D7, D8; tasks 1.4–1.6)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from horizon.ai.decider import (
    Choice,
    ChoiceAnswer,
    Decider,
    DecisionCancelled,
    DecisionUnavailable,
    Noul,
    NoulAnswer,
)
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.gateway.context import call_ctx
from horizon.gateway.decisions import DecisionsResponse
from horizon.gateway.errors import ProviderError
from horizon.gateway.types import Timeouts

T0 = datetime(2026, 10, 10, 2, 0, tzinfo=UTC)
Q = {"who": Choice("Who?", {"chr_a": "Ann", "chr_b": "Bo", "none": "nobody"})}
OK = {"who": {"type": "choice", "choice": "chr_a", "confidence": 0.9, "probabilities": {"chr_a": 0.9}}}


class FakeJev:
    """A decide() stand-in: answers after `delay_s` of clock time; records each call and how the call ended."""

    def __init__(self, clock: FrozenClock, delay_s: float = 0.0, answers: Mapping[str, Any] = OK,
                 errors: list[ProviderError] | None = None) -> None:
        self.clock, self.delay_s, self.answers = clock, delay_s, answers
        self.errors = list(errors or [])
        self.calls = 0
        self.outcomes: list[str | None] = []

    async def __call__(self, state: Any, wire: Mapping[str, Any], ctx: Any, *, finish: Any = None) -> DecisionsResponse:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        if self.delay_s:
            await self.clock.sleep(self.delay_s)
        self.outcomes.append(finish() if finish else None)
        return DecisionsResponse("dec-1", dict(self.answers), None, "typesafe/jev-1.13")


def make(delay_s: float = 0.0, **kw: Any) -> tuple[Decider, FakeJev, FrozenClock]:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    jev = FakeJev(clock, delay_s, **kw)
    t = Timeouts(chat_first_token=20, chat_idle=30, image=180, embedding=30, meta=10,
                 decision={"route": 0.4, "importance": 3.0, "guardrail": 0.7, "guardrail_prompt": 1.5, "default": 3.0})
    return Decider(jev, t, clock=clock, spawn=clock.activity.spawn), jev, clock


async def fallback() -> dict[str, Any]:
    return {"who": ChoiceAnswer("chr_b"), "p": NoulAnswer(0.0)}


def ctx(purpose: str = "route") -> Any:
    return call_ctx(purpose, world_id="wld_x")


async def run_until(clock: FrozenClock, coro: Any, advance_ms: float) -> Any:
    task = asyncio.ensure_future(coro)
    await asyncio.sleep(0)
    await clock.advance(advance_ms)
    return await task


async def test_on_time_answer() -> None:
    d, jev, clock = make(delay_s=0.2)
    call = d.start({}, Q, ctx(), purpose="route", fallback=fallback)
    r = await run_until(clock, call.by(T0 + timedelta(milliseconds=400)), 500)
    assert r.answers["who"].source == "jev" and jev.calls == 1 and jev.outcomes == ["on_time"]


async def test_deadline_then_full_answer_one_request() -> None:
    d, jev, clock = make(delay_s=0.62)
    calls = 0

    async def fb() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"who": ChoiceAnswer("chr_b")}

    call = d.start({}, Q, ctx(), purpose="route", fallback=fb)
    first = asyncio.ensure_future(call.by(T0 + timedelta(milliseconds=500)))
    second = asyncio.ensure_future(call.by(T0 + timedelta(milliseconds=450)))
    await asyncio.sleep(0)
    await clock.advance(1000)
    a, b = await first, await second
    assert a.answers["who"].source == b.answers["who"].source == "fallback" and calls == 1   # the fallback runs once
    full = await call.final()
    assert full.answers["who"] == ChoiceAnswer("chr_a", 0.9, {"chr_a": 0.9})
    assert jev.calls == 1 and jev.outcomes == ["late"]


async def test_final_only_outcome() -> None:
    d, jev, clock = make(delay_s=0.1)
    call = d.start({}, Q, ctx(), purpose="route", fallback=fallback)
    r = await run_until(clock, call.final(), 200)
    assert r.answers["who"].source == "jev" and jev.outcomes == ["final"]


async def test_cancel_detaches_readers_but_the_request_settles() -> None:
    d, jev, clock = make(delay_s=0.2)
    ran = False

    async def fb() -> dict[str, Any]:
        nonlocal ran
        ran = True
        return {"who": ChoiceAnswer("chr_b")}

    call = d.start({}, Q, ctx(), purpose="route", fallback=fb)
    reader = asyncio.ensure_future(call.final())
    await asyncio.sleep(0)
    call.cancel()
    with pytest.raises(DecisionCancelled):
        await reader
    await clock.advance(300)
    await d.idle()
    assert jev.calls == 1 and jev.outcomes == ["cancelled"] and not ran


async def test_stop_aborts_in_flight() -> None:
    d, _jev, _clock = make(delay_s=5.0)
    call = d.start({}, Q, ctx(), purpose="route", fallback=fallback)
    await asyncio.sleep(0)
    await d.stop()
    assert call._task is not None and call._task.cancelled()


async def test_ask_is_start_by() -> None:
    d, _, clock = make(delay_s=0.6)
    r = await run_until(clock, d.ask({}, Q, ctx(), purpose="route", fallback=fallback), 1000)
    assert r.failure == "timeout" and r.answers["who"].source == "fallback"


async def test_partial_validation_on_final() -> None:
    bad = {"who": {"choice": "chr_zzz"}, "p": {"noul": 0.7}}
    d, _, _clock = make(answers=bad)
    qs = {**Q, "p": Noul("Is it?", "yes", "no")}
    r = await d.start({}, qs, ctx(), purpose="route", fallback=fallback).final()
    assert r.answers["who"].source == "fallback" and r.answers["p"] == NoulAnswer(0.7)


# ── 1.5: the size check ──
@pytest.mark.parametrize(("chars", "sent"), [(89_000, True), (90_100, False)])
async def test_size_limit_on_state_plus_longest_question(chars: int, sent: bool) -> None:
    d, jev, _ = make()
    r = await d.start({"t": "x" * chars}, Q, ctx(), purpose="route", fallback=fallback).final()
    assert (jev.calls == 1) is sent
    assert (r.failure == "too_large") is (not sent)


async def test_size_counted_in_bytes() -> None:
    d, jev, _ = make()
    # 31,000 Chinese characters = 93,000 UTF-8 bytes = 31,000 tokens at 3 bytes/token: refused, though short in chars.
    r = await d.start({"t": "字" * 31_000}, Q, ctx(), purpose="route", fallback=fallback).final()
    assert jev.calls == 0 and r.failure == "too_large"


@pytest.mark.parametrize(("n", "sent"), [(64, True), (65, False)])
async def test_question_count_limit(n: int, sent: bool) -> None:
    d, jev, _ = make(answers={})
    qs = {f"q{i}": Noul("Is it?", "yes", "no") for i in range(n)}

    async def fb() -> dict[str, Any]:
        return {k: NoulAnswer(0.0) for k in qs}

    await d.start({}, qs, ctx(), purpose="route", fallback=fb).final()
    assert (jev.calls == 1) is sent


async def test_too_large_without_fallback_raises() -> None:
    d, _, _ = make()
    with pytest.raises(DecisionUnavailable):
        await d.start({"t": "x" * 100_000}, Q, ctx(), purpose="route").final()


# ── 1.6: the 429 policy ──
async def test_hot_path_429_falls_back_without_retry() -> None:
    d, jev, _ = make(errors=[ProviderError("rate_limited", status=429)])
    r = await d.start({}, Q, ctx(), purpose="route", fallback=fallback).final()
    assert r.failure == "rate_limited" and jev.calls == 1


async def test_background_429_retries_once_after_a_second() -> None:
    d, jev, clock = make(errors=[ProviderError("rate_limited", status=429)])
    call = d.start({}, Q, ctx("importance"), purpose="importance", fallback=fallback)
    r = await run_until(clock, call.final(), 1500)
    assert r.answers["who"].source == "jev" and jev.calls == 2


async def test_background_429_gives_up_when_the_deadline_cannot_be_met() -> None:
    d, jev, _clock = make(errors=[ProviderError("rate_limited", status=429, retry_after=4)])
    d.timeouts = Timeouts(chat_first_token=20, chat_idle=30, image=180, embedding=30, meta=10, decision={"importance": 2.0})
    r = await d.start({}, Q, ctx("importance"), purpose="importance", fallback=fallback).final()
    assert r.failure == "rate_limited" and jev.calls == 1


# ── 1.7: deadlines keyed per question ──
async def test_ask_uses_the_question_deadline_key() -> None:
    from horizon.ai.decider import QMeta

    d, _, clock = make(delay_s=1.0)
    meta = QMeta(id="prompt_check", version=1, label="unsafe?", purpose="guardrail", deadline="guardrail_prompt",
                 state={})
    q = {"x": Noul("Unsafe?", "yes", "no", meta=meta)}

    async def fb() -> dict[str, Any]:
        return {"x": NoulAnswer(0.0)}

    r = await run_until(clock, d.ask({}, q, ctx("guardrail"), purpose="guardrail", fallback=fb), 2000)
    assert r.failure is None   # 1,000 ms < guardrail_prompt's 1,500 ms (the output check's 700 would have missed)
