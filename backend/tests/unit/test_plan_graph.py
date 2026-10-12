"""The turn-plan graph skeleton (turn-plan-emotion tasks 1.2–1.3; design D1, D3): its node path, the fallback when Jev
is late, and no socket opened by LangGraph itself."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from horizon.ai.agent.plan_graph import build_plan_graph, run_plan
from horizon.ai.decider import Choice, ChoiceAnswer, Decider, DecisionResult
from horizon.domain import vclock
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.gateway.context import CallContext, call_ctx
from horizon.gateway.decisions import DecisionsResponse
from horizon.gateway.types import Timeouts
from tests.gwkit import block_network

T0 = datetime(2026, 10, 12, 2, 0, tzinfo=UTC)
Q = {"emotion:chr_a": Choice("Which face?", {"happy": "pleased", "sad": "low", "none": "keep"})}
OK = {"emotion:chr_a": {"type": "choice", "choice": "happy", "confidence": 0.8, "probabilities": {"happy": 0.8}}}


class ParkedJev:
    """Answers after `delay_s` of clock time, or holds until `release` is set (`delay_s` None)."""

    def __init__(self, clock: FrozenClock, delay_s: float | None = 0.0) -> None:
        self.clock, self.delay_s = clock, delay_s
        self.release = asyncio.Event()
        self.outcomes: list[str | None] = []

    async def __call__(self, state: Any, wire: Mapping[str, Any], ctx: Any, *, finish: Any = None) -> DecisionsResponse:
        if self.delay_s is None:   # parked like FakeOpenRouter's park_decision: the token is given up while held
            holder = vclock.current_holder()
            if holder is not None:
                holder.drop()
            try:
                await self.release.wait()
            finally:
                if holder is not None:
                    holder.hold()
        elif self.delay_s:
            await self.clock.sleep(self.delay_s)
        self.outcomes.append(finish() if finish else None)
        return DecisionsResponse("dec-1", dict(OK), None, "typesafe/jev-1.13")


@dataclass(frozen=True)
class Req:
    started_at: datetime


class Steps:
    def __init__(self, decider: Decider) -> None:
        self.decider = decider

    async def state(self, req: Req) -> Any:
        return {"mode": "one_on_one"}

    async def ask(self, req: Req, state: Any) -> DecisionResult:
        async def fallback() -> dict[str, Any]:
            return {k: ChoiceAnswer("none") for k in Q}

        ctx: CallContext = call_ctx("turn_plan", category="decision", world_id="wld_x")
        call = self.decider.start(state, Q, ctx, purpose="turn_plan", fallback=fallback)
        try:
            return await call.by(req.started_at + timedelta(seconds=self.decider.timeout_for("turn_plan")))
        except asyncio.CancelledError:
            call.cancel()       # Stop during the plan (design D8): readers detach; the request still settles
            raise

    def decide(self, req: Req, state: Any, result: DecisionResult) -> Any:
        a = result.answers["emotion:chr_a"]
        return {"face": a.choice, "fallback": result.used_fallback}

    def route(self, req: Req, plan: Any) -> Any:
        return "quick"


def make(delay_s: float | None = 0.0) -> tuple[Any, ParkedJev, FrozenClock]:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    jev = ParkedJev(clock, delay_s)
    t = Timeouts(chat_first_token=20, chat_idle=30, image=180, embedding=30, meta=10,
                 decision={"turn_plan": 0.7, "default": 3.0})
    decider = Decider(jev, t, clock=clock, spawn=clock.activity.spawn)
    return build_plan_graph(Steps(decider)), jev, clock


async def test_path_and_plan_with_an_answer() -> None:
    graph, jev, clock = make(delay_s=0.4)
    task = clock.activity.spawn("plan", run_plan(graph, Req(clock.now())))
    await asyncio.sleep(0)
    await clock.advance(500)
    plan, path = await task
    assert path == ["state", "ask", "decide", "route"]
    assert plan == {"face": "happy", "fallback": False} and jev.outcomes == ["on_time"]


async def test_late_answer_falls_back_at_the_deadline() -> None:
    graph, jev, clock = make(delay_s=None)     # parked: never answers until released
    task = clock.activity.spawn("plan", run_plan(graph, Req(clock.now())))
    await asyncio.sleep(0)
    await clock.advance(700)
    plan, path = await task
    assert plan == {"face": "none", "fallback": True} and path == ["state", "ask", "decide", "route"]
    jev.release.set()                           # the late answer still lands and is recorded as late
    await clock.activity.settle()
    assert jev.outcomes == ["late"]


async def test_a_graph_run_opens_no_socket(monkeypatch: Any) -> None:
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING"):
        monkeypatch.delenv(name, raising=False)   # the flag unset, not just "false" (design D1)
    attempts = block_network(monkeypatch)
    graph, _jev, clock = make(delay_s=0.0)
    task = clock.activity.spawn("plan", run_plan(graph, Req(clock.now())))
    await clock.advance(10)
    plan, _ = await task
    assert plan["face"] == "happy" and attempts == []
