"""Doc 01's offline checks 1 and 2 for the turn-plan graph (turn-plan-emotion tasks 1.4–1.6; design D2, D8).

- Check 1, overhead: the compiled graph against the same node functions called in a row (real time, fixture answers).
- Check 1, settling: 100 planned runs on the virtual clock, with Jev answering at set virtual times (some past the
  deadline), run twice: no SettleTimeout, identical outputs, nothing left busy.
- Check 2: a run cancelled while its decision is parked, or while the reply after it streams, is gone within 500 ms of
  virtual time, leaves no task, and its decision ends `cancelled`. This harness has one cancel path (the runtime's
  `clear()` cancels the turn task the same way for Stop, leave, a cap pause and end); task 3.4 re-runs each of those
  through the real runtime.

The figures are printed (`pytest -s`) and copied into docs/ai/checks/m9.md.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

import pytest

from horizon.ai.agent.plan_graph import build_plan_graph, run_plan
from horizon.ai.decider import ChoiceAnswer, Decider, DeciderFixtures
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.gateway.types import Timeouts
from tests.unit.test_plan_graph import T0, ParkedJev, Req, Steps

TIMEOUTS = Timeouts(chat_first_token=20, chat_idle=30, image=180, embedding=30, meta=10,
                    decision={"turn_plan": 0.7, "default": 3.0})


def p95(xs: list[float]) -> float:
    return sorted(xs)[int(0.95 * (len(xs) - 1))]


async def test_check1_graph_overhead_is_under_50ms() -> None:
    fixtures = DeciderFixtures()
    fixtures.set("turn_plan", "emotion:chr_a", ChoiceAnswer("happy", confidence=0.8))

    async def never(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("fixtures answer every question")

    steps = Steps(Decider(never, TIMEOUTS, fixtures))
    graph = build_plan_graph(steps)

    async def plain(req: Req) -> Any:
        state = await steps.state(req)
        plan = steps.decide(req, state, await steps.ask(req, state))
        steps.route(req, plan)
        return plan

    for _ in range(20):    # warm both paths (first-run compilation, imports)
        await run_plan(graph, Req(T0))
        await plain(Req(T0))
    g_ms: list[float] = []
    p_ms: list[float] = []
    for _ in range(200):
        t = time.perf_counter()
        plan, path = await run_plan(graph, Req(T0))
        g_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        assert await plain(Req(T0)) == plan
        p_ms.append((time.perf_counter() - t) * 1000)
    diff = p95(g_ms) - p95(p_ms)
    print(f"\ncheck 1 overhead: graph p50 {statistics.median(g_ms):.2f} ms, p95 {p95(g_ms):.2f} ms; "
          f"plain p50 {statistics.median(p_ms):.3f} ms, p95 {p95(p_ms):.3f} ms; p95 difference {diff:.2f} ms")
    assert path == ["state", "ask", "decide", "route"]
    assert diff < 50


def _delays() -> list[float]:
    """Jev's answer time per run, in seconds: 0.1 … 1.0, so 3 runs in 10 (0.8–1.0 s) answer past the 700 ms deadline."""
    return [round(0.1 * (1 + i % 10), 1) for i in range(100)]


async def _hundred_runs() -> tuple[list[Any], dict[str, int], list[str | None]]:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    out: list[Any] = []
    outcomes: list[str | None] = []
    for delay in _delays():
        jev = ParkedJev(clock, delay)
        graph = build_plan_graph(Steps(Decider(jev, TIMEOUTS, clock=clock, spawn=clock.activity.spawn)))
        task = clock.activity.spawn("plan", run_plan(graph, Req(clock.now())))
        await asyncio.sleep(0)
        await clock.advance(1100)          # past the deadline and past the slowest answer
        out.append(await task)
        outcomes += jev.outcomes
    await clock.activity.settle()
    return out, clock.activity.busy, outcomes


async def test_check1_runs_settle_on_the_virtual_clock_and_repeat() -> None:
    first, busy1, outcomes1 = await _hundred_runs()
    second, busy2, outcomes2 = await _hundred_runs()
    assert first == second and outcomes1 == outcomes2
    assert busy1 == {} and busy2 == {}
    late = sum(1 for plan, _ in first if plan["fallback"])
    print(f"\ncheck 1 settling: 100 runs × 2 settled; {late} fell back at the deadline; outcomes "
          f"{ {o: outcomes1.count(o) for o in set(outcomes1)} }")
    assert late == 30 and outcomes1.count("late") == 30 and outcomes1.count("on_time") == 70


@pytest.mark.parametrize("during", ["plan", "reply"])
async def test_check2_a_cancelled_run_leaves_nothing(during: str) -> None:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    jev = ParkedJev(clock, None if during == "plan" else 0.2)
    graph = build_plan_graph(Steps(Decider(jev, TIMEOUTS, clock=clock, spawn=clock.activity.spawn)))
    streamed: list[int] = []

    async def turn() -> None:
        await run_plan(graph, Req(clock.now()))
        for i in range(100):               # the reply: a chunk every 50 ms
            await clock.sleep(0.05)
            streamed.append(i)

    task = clock.activity.spawn("turn", turn())
    await asyncio.sleep(0)
    await clock.advance(300 if during == "plan" else 600)   # the decision is parked / the reply is streaming
    stop_at = clock.now()
    task.cancel()
    await clock.advance(500)                # NFR-20: gone within 500 ms
    assert task.done() and task.cancelled()
    assert (clock.now() - stop_at).total_seconds() <= 0.5
    if during == "plan":
        assert streamed == [] and jev.outcomes == []
        jev.release.set()                   # the request already sent finishes and is recorded
    await clock.activity.settle()
    assert clock.activity.busy == {}
    if during == "plan":
        assert jev.outcomes == ["cancelled"]
    else:
        assert jev.outcomes == ["on_time"] and 0 < len(streamed) < 100
    print(f"\ncheck 2 ({during}): cancelled, settled, nothing busy; decision outcomes {jev.outcomes}")


# ── M10 (group-watch task 2.5; design D4): check 1's settling, repeated for the cast plan ──
async def _hundred_cast_plans() -> tuple[list[Any], dict[str, int], list[str | None]]:
    from horizon.ai.agent.planner import JevTurnPlanner
    from tests.unit.test_cast_plan import CastDeps, choice, faces, request
    from tests.unit.test_planner import Jev

    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    out: list[Any] = []
    outcomes: list[str | None] = []
    for delay in _delays():
        jev = Jev(clock, {"who_first": choice("chr_b", 0.8, chr_b=0.7, chr_a=0.2, chr_c=0.1), **faces()}, delay)
        planner = JevTurnPlanner(CastDeps(Decider(jev, TIMEOUTS, clock=clock, spawn=clock.activity.spawn)))
        task = clock.activity.spawn("plan", planner.plan_cast(request(clock)))
        await asyncio.sleep(0)
        await clock.advance(1100)
        plan = await task
        assert plan is not None
        out.append(plan.model_dump(mode="json"))
        outcomes += jev.outcomes
    await clock.activity.settle()
    return out, clock.activity.busy, outcomes


async def test_check1_cast_plans_settle_on_the_virtual_clock_and_repeat() -> None:
    first, busy1, outcomes1 = await _hundred_cast_plans()
    second, busy2, outcomes2 = await _hundred_cast_plans()
    assert first == second and outcomes1 == outcomes2 and busy1 == {} and busy2 == {}
    late = sum(1 for p in first if p["who"]["source"] == "late")
    print(f"\nM10 cast plan settling: 100 runs × 2 settled; {late} fell back at the deadline; outcomes "
          f"{ {o: outcomes1.count(o) for o in set(outcomes1)} }")
    assert late == 30 and outcomes1.count("late") == 30 and outcomes1.count("on_time") == 70
