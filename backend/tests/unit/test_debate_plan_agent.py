"""The debate plan in `agent` (debate tasks 3.3, 3.9; design D5, D6, D8, D27; debate-plan "The member question and its
state", "The member is fixed by a deadline", "The faces are used if they land before the turn starts")."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any

from horizon.ai.agent.planner import JevTurnPlanner
from horizon.ai.contexts import DebateFacts, DebatePlan, DebateRequest
from horizon.ai.decider import Decider
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.gateway.errors import ProviderError
from tests.unit.test_cast_plan import PROFILES, CastDeps, choice, session
from tests.unit.test_planner import T0, TIMEOUTS, Jev

A, B = "chr_a", "chr_b"
DEADLINE_S = 0.5


def make(answers: dict[str, Any] | None = None, *, delay_s: float | None = 0.1,
         error: ProviderError | None = None) -> tuple[JevTurnPlanner, Jev, FrozenClock]:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    jev = Jev(clock, answers, delay_s, error)
    d = Decider(jev, TIMEOUTS, None, clock=clock, spawn=clock.activity.spawn)
    return JevTurnPlanner(CastDeps(d)), jev, clock


def request(clock: FrozenClock, candidates: list[str] | None = None, *, side: str | None = "prop",
            phase: str = "rebuttal", turn: int = 4) -> DebateRequest:
    cands = candidates or [A, B]
    long = " ".join(["word"] * 90)
    facts = DebateFacts(motion="This house would ban homework", phase=phase, side=side,
                        last_opposing="Victor Hale: Homework teaches discipline.",
                        latest_by_candidate={A: long, B: "Children need rest."})
    return DebateRequest(session=session("debate"), phase=phase, iteration=1, side=side, candidates=cands,
                         cast=[p for p in PROFILES if p.id in cands], facts=facts,
                         latest="Victor Hale: Homework teaches discipline.", turn_index=turn,
                         base_faces={c: "neutral" for c in cands}, started_at=clock.now())


async def fixed(planner: JevTurnPlanner, clock: FrozenClock, req: DebateRequest,
                advance_ms: float = 600) -> tuple[DebatePlan, DebatePlan]:
    """`member` by turn.end + 500 ms, then `faces` at the turn's start (1.5 s later)."""
    call = planner.start_debate(req)
    assert call is not None
    task = clock.activity.spawn("member", call.member(req.started_at + timedelta(seconds=DEADLINE_S)))
    await asyncio.sleep(0)
    await clock.advance(advance_ms)
    member = await task
    face_task = clock.activity.spawn("faces", call.faces(req.started_at + timedelta(seconds=2.0)))
    await asyncio.sleep(0)
    await clock.advance(2000)
    return member, await face_task


def faces(face: str = "angry", conf: float = 0.9) -> dict[str, Any]:
    return {f"emotion_line:{c}": choice(face, conf) for c in (A, B)}


# ── the request and the state (D6) ──
async def test_two_candidates_ask_the_member_and_every_face_in_one_request_with_the_debate_state() -> None:
    planner, jev, clock = make({"member_rebuttal": choice(B, 0.9, chr_b=0.9, chr_a=0.1), **faces()})
    member, _ = await fixed(planner, clock, request(clock))
    assert len(jev.sent) == 1
    assert set(jev.sent[0]) == {"member_rebuttal", f"emotion_line:{A}", f"emotion_line:{B}"}
    assert "none" not in jev.sent[0]["member_rebuttal"]["criteria"]
    st = jev.states[0]
    assert "last_spoke" not in json.dumps(st) and "energy" not in json.dumps(st).lower()
    assert st["quoted_arguments"]["last_opposing"].startswith("Victor Hale:")
    assert all(len(v.removesuffix(" …").split()) <= 60 for v in st["quoted_arguments"]["latest_by_candidate"].values())
    assert st["phase"] == "rebuttal" and st["side"] == "prop"
    assert member.member == B and member.outcome == "jev"


async def test_one_candidate_asks_only_the_face() -> None:
    planner, jev, clock = make({f"emotion_line:{A}": choice("happy", 0.9)})
    member, plan = await fixed(planner, clock, request(clock, [A]))
    assert set(jev.sent[0]) == {f"emotion_line:{A}"}
    assert member.outcome == "single" and plan.member == A
    tp = plan.for_speaker(A)
    assert tp.emotion is not None and tp.emotion.face == "happy"
    assert [r["id"] for r in tp.rows] == ["emotion_line"]
    assert set(jev.states[0]) <= {"mode", "quoted_user", "quoted_cast", "quoted_latest", "quoted_recent"}


async def test_a_panel_asks_member_panel_without_a_side() -> None:
    planner, jev, clock = make({"member_panel": choice(A, 0.9), **faces()})
    await fixed(planner, clock, request(clock, side=None))
    assert "member_panel" in jev.sent[0]
    assert "side" not in jev.states[0]


async def test_a_closing_asks_member_closing() -> None:
    planner, jev, clock = make({"member_closing": choice(A, 0.9), **faces()})
    await fixed(planner, clock, request(clock, phase="closing"))
    assert "member_closing" in jev.sent[0]


# ── D8's outcome table ──
async def test_a_confident_pick_is_used_with_its_row() -> None:
    planner, _, clock = make({"member_rebuttal": choice(B, 0.9, chr_b=0.9, chr_a=0.1), **faces()})
    member, plan = await fixed(planner, clock, request(clock))
    assert (member.member, member.outcome) == (B, "jev")
    assert member.who is not None and member.who.reason == "Side by the debate order; speaker chosen by Jev"
    assert member.who.candidates[0] == {"characterId": B, "p": 0.9}
    row = plan.for_speaker(B).rows[0]
    assert (row["purpose"], row["id"], row["answer"], row["result"], row["action"]) == (
        "debate_plan", "member_rebuttal", B, "used", "speaks")
    assert row["compared"] == [{"name": "confidence", "value": 0.9, "threshold": 0.6}]
    tp = plan.for_speaker(B)
    assert tp.emotion is not None and tp.emotion.face == "angry"
    assert {r["about"]: r["result"] for r in tp.rows if r["id"] == "emotion_line"} == {A: "not_used", B: "used"}


async def test_below_the_floor_takes_the_first_in_fixed_order() -> None:
    planner, _, clock = make({"member_rebuttal": choice(B, 0.4), **faces()})
    member, plan = await fixed(planner, clock, request(clock))
    assert (member.member, member.outcome) == (A, "below_floor")
    assert member.who is not None and member.who.reason.endswith(", next in order: Jev was unsure")
    row = plan.for_speaker(A).rows[0]
    assert (row["answer"], row["result"], row["action"]) == (B, "below_threshold", "next in order (unsure)")


async def test_a_failure_takes_the_first_in_fixed_order() -> None:
    planner, _, clock = make(error=ProviderError("provider_error"))
    member, plan = await fixed(planner, clock, request(clock))
    assert (member.member, member.outcome) == (A, "fallback")
    row = plan.for_speaker(A).rows[0]
    assert (row["answer"], row["result"]) == ("next in order", "fallback")
    assert plan.calls and plan.calls[0]["fallback"] is True


async def test_a_late_member_with_an_on_time_face() -> None:
    """Jev answers at 900 ms: past the member's 500 ms, inside the 1.5 s pause; the member is fixed order, the face is
    Jev's."""
    planner, _, clock = make({"member_rebuttal": choice(B, 0.9), **faces("happy")}, delay_s=0.9)
    member, plan = await fixed(planner, clock, request(clock))
    assert (member.member, member.outcome) == (A, "late")
    assert member.who is not None and member.who.reason.endswith(", next in order: Jev was late")
    tp = plan.for_speaker(A)
    assert tp.emotion is not None and tp.emotion.face == "happy" and tp.emotion.source == "classifier"
    row = tp.rows[0]
    assert (row["answer"], row["result"], row["action"]) == (B, "fallback", "next in order (Jev answered late)")


async def test_too_late_for_the_face_the_late_rows_carry_jevs_answer() -> None:
    planner, _, clock = make({"member_rebuttal": choice(B, 0.9), **faces("happy")}, delay_s=3.0)
    req = request(clock)
    call = planner.start_debate(req)
    assert call is not None
    t = clock.activity.spawn("m", call.member(req.started_at + timedelta(seconds=DEADLINE_S)))
    await asyncio.sleep(0)
    await clock.advance(600)
    assert (await t).outcome == "late"
    f = clock.activity.spawn("f", call.faces(req.started_at + timedelta(seconds=2.0)))
    await asyncio.sleep(0)
    await clock.advance(1500)
    plan = await f
    assert plan.faces[A].source != "classifier"
    assert not call.landed
    late = clock.activity.spawn("late", call.late_rows())
    await asyncio.sleep(0)
    await clock.advance(2000)
    rows = await late
    assert rows is not None and call.landed
    face = rows.face_rows[A]
    assert (face["result"], face["answer"]) == ("fallback", "happy")
    assert rows.shared_rows[0]["answer"] == B and rows.shared_rows[0]["result"] == "fallback"


async def test_cancel_ends_the_readers_and_records_cancelled() -> None:
    planner, jev, clock = make({"member_rebuttal": choice(B, 0.9), **faces()}, delay_s=None)
    req = request(clock)
    call = planner.start_debate(req)
    assert call is not None
    late = clock.activity.spawn("late", call.late_rows())
    await asyncio.sleep(0)
    await clock.advance(100)
    call.cancel()
    await clock.advance(10)
    assert await late is None
    jev.release.set()
    await clock.advance(10)
    await clock.activity.settle()
    assert jev.outcomes == ["cancelled"]


# ── 3.9: settling, run twice ──
def _delays() -> list[float]:
    """Jev's answer time per slot: 0.1 … 1.0 s, so slots answering at 0.6–1.0 s miss the 500 ms member deadline and
    those at ≥ 0.6 still land inside the 1.5 s pause."""
    return [round(0.1 * (1 + i % 10), 1) for i in range(50)]


async def _fifty_slots() -> tuple[list[tuple[str, str, str | None]], dict[str, int]]:
    out: list[tuple[str, str, str | None]] = []
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    for i, delay in enumerate(_delays()):
        jev = Jev(clock, {"member_rebuttal": choice(B, 0.9), **faces("happy")}, delay)
        planner = JevTurnPlanner(CastDeps(Decider(jev, TIMEOUTS, None, clock=clock, spawn=clock.activity.spawn)))
        req = request(clock, turn=i)
        call = planner.start_debate(req)
        assert call is not None
        m = clock.activity.spawn("member", call.member(req.started_at + timedelta(seconds=DEADLINE_S)))
        await asyncio.sleep(0)
        await clock.advance(600)
        member = await m
        f = clock.activity.spawn("faces", call.faces(req.started_at + timedelta(seconds=2.0)))
        await asyncio.sleep(0)
        await clock.advance(1500)
        plan = await f
        face = plan.faces[member.member]
        out.append((member.member, member.outcome, face.face if face.source == "classifier" else None))
    await clock.activity.settle()
    return out, clock.activity.busy


async def test_fifty_debate_slots_settle_and_repeat() -> None:
    first, busy1 = await _fifty_slots()
    second, busy2 = await _fifty_slots()
    assert first == second and busy1 == {} and busy2 == {}
    late = sum(1 for _, o, _ in first if o == "late")
    print(f"\ndebate check 1 settling: 50 slots × 2 settled; {late} members fell back at 500 ms, every face on time")
    assert late == 25 and all(f == "happy" for _, _, f in first)


# ── 4.1: the two forced debate kinds of `plan_cast` ──
async def test_debate_opening_and_debate_ask_ask_one_face_each_with_their_state() -> None:
    from tests.unit.test_cast_plan import request as cast_request
    from tests.unit.test_cast_plan import run

    facts = DebateFacts(motion="This house would ban homework", phase="opening", side="prop")
    planner, jev, clock = make({f"emotion_debate_opening:{A}": choice("happy", 0.9)})
    plan = await run(planner, clock, cast_request(clock, "debate_opening", candidates=[], forced=[A],
                                                  forced_by="round_order", latest="", debate=facts))
    assert set(jev.sent[0]) == {f"emotion_debate_opening:{A}"}
    assert set(jev.states[0]) == {"mode", "side", "quoted_user", "quoted_cast", "quoted_motion"}
    assert "last_spoke" not in json.dumps(jev.states[0])
    tp = plan.for_speaker(A)
    assert tp.emotion is not None and tp.emotion.face == "happy"
    assert [(r["id"], r["result"]) for r in tp.rows if r["id"].startswith("emotion")] == [("emotion_debate_opening", "used")]

    planner, jev, clock = make({f"emotion_reply:{A}": choice("surprised", 0.9)})
    plan = await run(planner, clock, cast_request(clock, "debate_ask", candidates=[], forced=[A], forced_by="user_ask",
                                                  latest="Kai: Would you ban weekend homework too?",
                                                  debate=facts.model_copy(update={"phase": "rebuttal"})))
    assert set(jev.sent[0]) == {f"emotion_reply:{A}"}
    assert jev.states[0]["quoted_latest"] == "Kai: Would you ban weekend homework too?"
    tp = plan.for_speaker(A)
    assert tp.emotion is not None and tp.emotion.face == "surprised"
