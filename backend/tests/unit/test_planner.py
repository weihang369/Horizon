"""The `agent` turn planner on the plan graph (turn-plan-emotion task 3.1; design D4, D7, D8, D10–D13; turn-plan "Jev
call 1 is one request…", "The plan has a deadline and a fallback")."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from horizon.ai.agent.planner import JevTurnPlanner, plan_state_input
from horizon.ai.contexts import CharacterView, MessageView, ParticipantView, PlanRequest, SessionContext, WorldView
from horizon.ai.decider import ChoiceAnswer, Decider, DeciderFixtures
from horizon.domain import vclock
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.gateway.decisions import DecisionsResponse
from horizon.gateway.errors import ProviderError
from horizon.gateway.types import Timeouts

T0 = datetime(2026, 10, 12, 2, 0, tzinfo=UTC)
KEY = "emotion_reply:chr_a"
TIMEOUTS = Timeouts(chat_first_token=20, chat_idle=30, image=180, embedding=30, meta=10,
                    decision={"turn_plan": 0.7, "default": 3.0})
AMARA = CharacterView(id="chr_a", name="Amara Okafor", profile={"personality": {"summary": "Calm under pressure. Dry."}})


class Jev:
    """A decide() stand-in: answers `answers` after `delay_s`, or holds (token given up) until `release`, or raises."""

    def __init__(self, clock: FrozenClock, answers: Mapping[str, Any] | None = None, delay_s: float | None = 0.1,
                 error: ProviderError | None = None) -> None:
        self.clock, self.answers, self.delay_s, self.error = clock, answers or {}, delay_s, error
        self.release = asyncio.Event()
        self.sent: list[Mapping[str, Any]] = []
        self.states: list[Any] = []
        self.outcomes: list[str | None] = []

    async def __call__(self, state: Any, wire: Mapping[str, Any], ctx: Any, *, finish: Any = None) -> DecisionsResponse:
        self.sent.append(wire)
        self.states.append(state)
        if self.error is not None:
            raise self.error
        if self.delay_s is None:
            holder = vclock.current_holder()
            if holder is not None:
                holder.drop()
            try:
                await self.release.wait()
            finally:
                if holder is not None:
                    holder.hold()
        else:
            await self.clock.sleep(self.delay_s)
        self.outcomes.append(finish() if finish else None)
        return DecisionsResponse("dec-1", dict(self.answers), None, "typesafe/jev-1.13")


class Deps:
    def __init__(self, decider: Decider) -> None:
        self._d = decider

    def decider(self) -> Decider:
        return self._d

    def emotion_fade(self) -> frozenset[str]:
        return frozenset({"surprised", "embarrassed"})

    @property
    def prices(self) -> Any:
        class P:
            class decision:
                model = "typesafe/jev-1.13"
        return P


def request(clock: FrozenClock, *, base: str = "thinking", kind: str = "reply", manual: bool = False) -> PlanRequest:
    recent = [MessageView(id="m1", seq=1, author_type="character", character_id="chr_a", name="Amara Okafor",
                          kind="chat", content="Long shift."),
              MessageView(id="m2", seq=2, author_type="user", name="Kai", kind="chat", content="My dog died today.")]
    s = SessionContext(session_id="ses_1", seed="s1", world=WorldView(id="w", name="Meridian", you={"displayName": "Kai"}),
                       mode="one_on_one", title="t", recent=recent,
                       participants=[ParticipantView(character_id="chr_a", name="Amara Okafor", role="speaker",
                                                     character_role="Emergency physician", emotion=base,
                                                     energy={"current": 500})])
    return PlanRequest(session=s, speaker_id="chr_a", cast=[AMARA], message_id="msg_1", kind=kind,  # type: ignore[arg-type]
                       latest="My dog died today." if kind == "reply" else "", turn_index=3, base_face=base,
                       manual=manual, started_at=clock.now())


def make(answers: Mapping[str, Any] | None = None, *, delay_s: float | None = 0.1, error: ProviderError | None = None,
         budget: int | None = None, fixtures: DeciderFixtures | None = None) -> tuple[JevTurnPlanner, Jev, FrozenClock]:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    jev = Jev(clock, answers, delay_s, error)
    kw: dict[str, Any] = {"budget": budget} if budget is not None else {}
    d = Decider(jev, TIMEOUTS, fixtures, clock=clock, spawn=clock.activity.spawn, **kw)
    return JevTurnPlanner(Deps(d)), jev, clock


async def run(planner: JevTurnPlanner, clock: FrozenClock, req: PlanRequest, advance_ms: float = 800) -> Any:
    task = clock.activity.spawn("plan", planner.plan(req))
    await asyncio.sleep(0)
    await clock.advance(advance_ms)
    return await task


def jev_answer(choice: str, conf: float, **probs: float) -> dict[str, Any]:
    return {KEY: {"type": "choice", "choice": choice, "confidence": conf, "probabilities": probs or {choice: conf}}}


async def test_confident_pick_one_request_and_the_state() -> None:
    planner, jev, clock = make(jev_answer("sad", 0.74, sad=0.6, thinking=0.2, none=0.1, happy=0.1))
    plan = await run(planner, clock, request(clock))
    assert len(jev.sent) == 1 and list(jev.sent[0]) == [KEY]
    assert set(jev.states[0]) == {"mode", "quoted_user", "quoted_cast", "quoted_latest", "quoted_recent"}
    assert jev.states[0]["quoted_latest"] == "My dog died today."
    assert [r["text"] for r in jev.states[0]["quoted_recent"]] == ["Long shift."]   # the latest isn't repeated
    assert plan.emotion.face == "sad" and plan.emotion.source == "classifier" and plan.seed == "s1:3"
    assert plan.rows[0]["about"] == "chr_a" and plan.rows[0]["action"] == "shown" and plan.calls == []
    assert plan.graph_path == ["state", "ask", "decide", "route"] and plan.state_tokens > 0
    assert "Which face fits how Amara Okafor feels" in jev.sent[0][KEY]["instructions"]


async def test_greeting_asks_the_greeting_question() -> None:
    planner, jev, clock = make({"emotion_greeting:chr_a": {"type": "choice", "choice": "happy", "confidence": 0.8,
                                                           "probabilities": {"happy": 0.8}}})
    plan = await run(planner, clock, request(clock, kind="greeting"))
    assert list(jev.sent[0]) == ["emotion_greeting:chr_a"] and "quoted_latest" not in jev.states[0]
    assert plan.kind == "greeting" and plan.emotion.face == "happy"


async def test_none_keeps_and_below_the_floor_keeps() -> None:
    planner, _, clock = make(jev_answer("none", 0.9))
    assert (await run(planner, clock, request(clock))).emotion.face == "thinking"
    planner, _, clock = make(jev_answer("angry", 0.15))   # the bank floor is 0.2 since M9 9.3 (D36)
    plan = await run(planner, clock, request(clock))
    assert plan.emotion.face == "thinking" and plan.rows[0]["result"] == "below_threshold"


async def test_late_answer_falls_back_at_the_deadline_and_is_still_recorded() -> None:
    planner, jev, clock = make(jev_answer("sad", 0.9), delay_s=None)
    plan = await run(planner, clock, request(clock, base="surprised"), advance_ms=700)
    assert plan.emotion.outcome == "late" and plan.emotion.face == "neutral" and plan.rows[0]["result"] == "fallback"
    assert plan.calls[0]["fallback"] is True and plan.calls[0]["latencyMs"] == 700.0
    jev.release.set()
    await clock.activity.settle()
    assert jev.outcomes == ["late"]


async def test_a_429_falls_back_at_once_with_no_retry() -> None:
    planner, jev, clock = make(error=ProviderError("rate_limited", "Rate limit exceeded"))
    plan = await run(planner, clock, request(clock), advance_ms=10)
    assert plan.emotion.outcome == "fallback" and plan.emotion.face == "thinking" and len(jev.sent) == 1


async def test_too_large_is_refused_before_sending() -> None:
    planner, jev, clock = make(jev_answer("sad", 0.9), budget=10)
    plan = await run(planner, clock, request(clock), advance_ms=10)
    assert plan.emotion.outcome == "fallback" and jev.sent == []


async def test_fixture_answer_sends_nothing() -> None:
    fx = DeciderFixtures()
    fx.set("turn_plan", KEY, ChoiceAnswer("happy", confidence=0.9, probabilities={"happy": 0.9}))
    planner, jev, clock = make(fixtures=fx)
    plan = await run(planner, clock, request(clock), advance_ms=10)
    assert plan.emotion.face == "happy" and jev.sent == []


async def test_cancelled_plan_detaches_and_the_request_settles() -> None:
    planner, jev, clock = make(jev_answer("sad", 0.9), delay_s=None)
    task = clock.activity.spawn("plan", planner.plan(request(clock)))
    await asyncio.sleep(0)
    await clock.advance(300)
    task.cancel()
    await clock.advance(100)
    assert task.cancelled()
    jev.release.set()
    await clock.activity.settle()
    assert jev.outcomes == ["cancelled"] and clock.activity.busy == {}


@pytest.mark.parametrize(("name", "expect"), [("Amara Okafor", "Amara Okafor"), ("A" * 30 + " " + "B" * 20, "A" * 30)])
async def test_long_names_use_the_first_name(name: str, expect: str) -> None:
    from horizon.ai.agent.planner import _name
    assert _name(name) == expect


def test_state_input_never_repeats_the_latest_line() -> None:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    inp = plan_state_input(request(clock))
    assert inp.latest == "My dog died today." and [r["text"] for r in inp.recent] == ["Long shift."]
    assert inp.candidates[0].turns_since == 0 and inp.candidates[0].face == "thinking"
    assert inp.candidates[0].about_source.startswith("Calm under pressure")


async def test_a_planner_bug_keeps_the_face_instead_of_failing_the_turn(monkeypatch: Any) -> None:
    planner, _, clock = make(jev_answer("sad", 0.9))

    async def broken(req: Any) -> Any:
        raise RuntimeError("bug")

    monkeypatch.setattr(planner, "state", broken)
    planner.graph = __import__("horizon.ai.agent.plan_graph", fromlist=["x"]).build_plan_graph(planner)
    plan = await run(planner, clock, request(clock, base="surprised"), advance_ms=10)
    assert plan.emotion.outcome == "fallback" and plan.emotion.face == "neutral" and plan.branch == "quick"


# ── M10 (group-watch task 2.2): the scripted and naive planners plan no group, and never raise ──
async def test_scripted_planner_swallows_a_cap_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The port never raises: M10 found the scripted planner's simulated call raising a cap refusal out of the plan
    task. The reply's own preflight takes the pause (M9 D7)."""
    from horizon.ai.scripted import ports as scripted

    class Gw:
        async def simulated_call(self, *a: Any, **kw: Any) -> Any:
            raise ProviderError("daily_budget_exceeded", "Today's spending cap is reached.")

    class D:
        prices = type("P", (), {"decision": type("Dp", (), {"model": "typesafe/jev-1.13"})})

        def gateway(self) -> Gw:
            return Gw()

        def system1_row(self, qid: str, answer: str) -> None:
            return None

    monkeypatch.setattr(scripted, "decision_cost", lambda *a, **kw: 0.0)
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    plan = await scripted.ScriptedTurnPlanner(D(), simulate=True).plan(request(clock))   # type: ignore[arg-type]
    assert plan is not None and plan.emotion is None


async def test_scripted_and_naive_planners_leave_group_and_watch_alone() -> None:
    from horizon.ai.naive.noop import NoPlanner
    from horizon.ai.scripted.ports import ScriptedTurnPlanner

    for p in (NoPlanner(), ScriptedTurnPlanner(None)):   # type: ignore[arg-type]
        assert p.decides_retrieval is False
        assert await p.plan_cast(None) is None and p.start_follow(None) is None   # type: ignore[arg-type]
