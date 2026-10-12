"""The frozen turn plan in `TurnContext` (turn-plan-emotion task 2.1; design D4; turn-plan "The plan is frozen into the
turn context"): it survives JSON both ways, and an unplanned context is unchanged."""

from __future__ import annotations

from datetime import UTC, datetime

from horizon.ai.contexts import (
    CharacterView,
    ParticipantView,
    PlannedFace,
    PlanRequest,
    SessionContext,
    TurnContext,
    TurnPlan,
    WorldView,
)


def session() -> SessionContext:
    return SessionContext(session_id="ses_1", seed="s1", world=WorldView(id="w", name="Meridian"), mode="one_on_one",
                          title="t", participants=[ParticipantView(character_id="chr_a", name="Amara", role="speaker",
                                                                   emotion="thinking", energy={"current": 500})],
                          recent=[])


def plan() -> TurnPlan:
    face = PlannedFace(face="sad", source="classifier", base="thinking", outcome="jev", pick="sad", p=0.6,
                       confidence=0.74, compared=[{"name": "confidence", "value": 0.74, "threshold": 0.6}],
                       candidates=[{"label": "sad", "p": 0.6}, {"label": "thinking", "p": 0.2}])
    return TurnPlan(seed="s1:3", emotion=face, graph_path=["state", "ask", "decide", "route"], state_tokens=412,
                    rows=[{"purpose": "turn_plan", "id": "emotion_reply", "version": 1, "label": "emotion",
                           "about": "chr_a", "answer": "sad", "p": 0.6, "confidence": 0.74, "result": "used",
                           "action": "shown", "compared": [{"name": "confidence", "value": 0.74, "threshold": 0.6}]}],
                    calls=[{"purpose": "turn_plan", "costUsd": 0.00004, "latencyMs": 412.0}])


def test_a_planned_context_round_trips_through_json() -> None:
    ctx = TurnContext(session=session(), speaker=CharacterView(id="chr_a", name="Amara", profile={}), message_id="msg_1",
                      max_tokens=150, plan=plan())
    again = TurnContext.model_validate_json(ctx.model_dump_json())
    assert again == ctx and again.plan is not None and again.plan.emotion is not None
    assert again.plan.emotion.face == "sad" and again.plan.rows[0]["result"] == "used"


def test_an_unplanned_context_has_no_plan_and_dumps_it_as_null() -> None:
    ctx = TurnContext(session=session(), speaker=CharacterView(id="chr_a", name="Amara", profile={}), message_id=None,
                      max_tokens=150)
    assert ctx.plan is None and ctx.model_dump()["plan"] is None


def test_the_plan_request_carries_its_start_instant() -> None:
    at = datetime(2026, 10, 12, 2, 0, tzinfo=UTC)
    req = PlanRequest(session=session(), speaker_id="chr_a", latest="hello", turn_index=3, base_face="thinking",
                      started_at=at)
    assert PlanRequest.model_validate_json(req.model_dump_json()) == req and req.kind == "reply" and not req.manual
