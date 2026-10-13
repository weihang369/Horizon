"""The follow plan (group-watch task 4.1; design D4, D8; follow-plan "The follow plan's question", "Outcomes favour
silence"; system1-trace "Rows carry the call's purpose")."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from horizon.ai.agent.follow_plan import decide_second, follow_state
from horizon.ai.agent.planner import JevTurnPlanner
from horizon.ai.contexts import FollowPlan, FollowRequest
from horizon.ai.decider import ChoiceAnswer
from horizon.domain.clock import FrozenClock
from horizon.gateway.errors import ProviderError
from tests.unit.test_cast_plan import PROFILES, choice, make, session

FIRST, MEI, VICTOR = "chr_a", "chr_b", "chr_c"


def request(clock: FrozenClock, *, message: str = "Mei, is it worth it?", text: str = "It depends on the hours.",
            candidates: list[str] | None = None) -> FollowRequest:
    return FollowRequest(session=session(), first_id=FIRST, first_name="Amara Okafor", first_message_id="msg_1",
                         first_text=text, message=message, candidates=candidates or [MEI, VICTOR], cast=PROFILES,
                         turn_index=5, base_faces={MEI: "neutral", VICTOR: "thinking"},
                         turns_since={MEI: 3, VICTOR: None}, started_at=clock.now())


async def follow(planner: JevTurnPlanner, clock: FrozenClock, req: FollowRequest, *, end_ms: float = 30,
                 advance_ms: float = 800) -> tuple[FollowPlan, Any]:
    handle = planner.start_follow(req)
    assert handle is not None
    deadline = req.started_at + timedelta(milliseconds=end_ms + 400)   # turn.end + 400 ms
    task = clock.activity.spawn("follow", handle.by(deadline))
    await asyncio.sleep(0)
    await clock.advance(advance_ms)
    return await task, handle


def faces(face: str = "surprised", conf: float = 0.9) -> dict[str, Any]:
    return {f"emotion_reply:{c}": choice(face, conf) for c in (MEI, VICTOR)}


# ── the state ──
def test_the_state_holds_the_first_reply_the_message_and_the_lines_before_it() -> None:
    clock = make()[2]
    st = follow_state(request(clock)).state
    assert st["quoted_latest"] == "Amara Okafor: It depends on the hours."
    assert st["quoted_message"] == "Mei, is it worth it?"
    assert [r["text"] for r in st["quoted_recent"]] == ["Long day at the shop."]   # before the user's message
    assert [c["name"] for c in st["quoted_cast"]] == ["Mei Lin", "Victor Hale"]
    assert "energy" not in str(st).lower()


def test_a_long_message_is_cut_head_and_tail_then_further_to_fit() -> None:
    clock = make()[2]
    long = "word " * 2000
    st = follow_state(request(clock, message=long)).state
    assert " … " in st["quoted_message"] and len(st["quoted_message"]) < len(long)
    huge = follow_state(request(clock, message=long, text="x " * 4000))
    assert huge.tokens <= 2000


# ── the rule ──
def test_g2s_table() -> None:
    cands = [MEI, VICTOR]
    assert decide_second(ChoiceAnswer(MEI, 0.8), cands, floor=0.6, failure=None) == (MEI, "jev", 0.8)
    assert decide_second(ChoiceAnswer("none", 0.9), cands, floor=0.6, failure=None) == (None, "none", 0.9)
    assert decide_second(ChoiceAnswer(MEI, 0.3), cands, floor=0.6, failure=None) == (None, "below_floor", 0.3)
    assert decide_second(None, cands, floor=0.6, failure="timeout") == (None, "late", None)
    assert decide_second(ChoiceAnswer("chr_x", 0.9), cands, floor=0.6, failure=None)[1] == "fallback"


# ── through the planner ──
async def test_a_confident_pick_speaks_second_with_the_follow_plans_face() -> None:
    planner, jev, clock = make({"who_second": choice(VICTOR, 0.85, chr_c=0.85, none=0.15), **faces()})
    plan, _ = await follow(planner, clock, request(clock))
    assert set(jev.sent[0]) == {"who_second", f"emotion_reply:{MEI}", f"emotion_reply:{VICTOR}"}
    assert "none" in jev.sent[0]["who_second"]["criteria"]
    assert jev.sent[0]["who_second"]["instructions"].startswith("Amara Okafor has just answered quoted_message")
    assert plan.second == VICTOR and plan.outcome == "jev"
    tp = plan.for_speaker(VICTOR, answered="Amara")
    assert tp.cue == "second" and tp.emotion is not None and tp.emotion.face == "surprised"
    row = tp.rows[0]
    assert (row["purpose"], row["id"], row["answer"], row["result"], row["action"]) == (
        "follow_plan", "who_second", VICTOR, "used", "speaks second")
    assert {r["purpose"] for r in tp.rows} == {"follow_plan"}
    assert plan.calls[0]["purpose"] == "follow_plan" and "fallback" not in plan.calls[0]


async def test_none_gives_no_second_reply_and_rows_for_the_first() -> None:
    planner, _, clock = make({"who_second": choice("none", 0.9), **faces()})
    plan, _ = await follow(planner, clock, request(clock))
    assert plan.second is None and plan.outcome == "none"
    rows = plan.rows_for_first()
    assert rows[0]["answer"] == "none" and rows[0]["action"] == "no second reply"
    assert {r["result"] for r in rows[1:]} == {"not_used"}


async def test_unsure_gives_no_second_reply() -> None:
    planner, _, clock = make({"who_second": choice(MEI, 0.3), **faces()})
    plan, _ = await follow(planner, clock, request(clock))
    assert plan.second is None and plan.shared_rows[0]["result"] == "below_threshold"


async def test_late_gives_no_second_reply_and_nothing_hangs() -> None:
    planner, jev, clock = make(delay_s=None)
    plan, _ = await follow(planner, clock, request(clock), advance_ms=500)
    assert plan.second is None and plan.outcome == "late"
    row = plan.shared_rows[0]
    assert row["answer"] == "no second reply (late)" and row["result"] == "fallback" and "p" not in row
    assert plan.calls[0]["fallback"] is True and plan.calls[0]["latencyMs"] == 430.0
    jev.release.set()


async def test_a_failure_gives_no_second_reply() -> None:
    planner, _, clock = make(error=ProviderError("rate_limited", "429"))
    plan, _ = await follow(planner, clock, request(clock), advance_ms=10)
    assert plan.second is None and plan.outcome == "fallback"


async def test_nobody_left_to_ask_starts_nothing() -> None:
    planner, jev, clock = make()
    assert planner.start_follow(request(clock).model_copy(update={"candidates": []})) is None
    assert jev.sent == []


async def test_cancelling_the_wait_cancels_the_request() -> None:
    planner, jev, clock = make(delay_s=None)
    handle = planner.start_follow(request(clock))
    assert handle is not None
    task = clock.activity.spawn("follow", handle.by(clock.now() + timedelta(milliseconds=400)))
    await asyncio.sleep(0)
    task.cancel()
    jev.release.set()
    await clock.advance(100)
    assert task.cancelled()
