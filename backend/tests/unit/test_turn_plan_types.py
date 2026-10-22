"""The frozen turn plan in `TurnContext` (turn-plan-emotion task 2.1; design D4; turn-plan "The plan is frozen into the
turn context"): it survives JSON both ways, and an unplanned context is unchanged."""

from __future__ import annotations

from datetime import UTC, datetime

from horizon.ai.contexts import (
    CastPlan,
    CastRequest,
    CharacterView,
    FollowPlan,
    FollowRequest,
    ParticipantView,
    PlannedFace,
    PlanRequest,
    SessionContext,
    TalkFinished,
    TurnContext,
    TurnPlan,
    WhoPick,
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


# ── M10 (group-watch task 2.1; design D3, D22): the cast plan and the follow plan ──
def _face(face: str, outcome: str = "jev") -> PlannedFace:
    return PlannedFace(face=face, source="classifier" if outcome == "jev" else "default", base="neutral",
                       outcome=outcome, pick=face, p=0.7, confidence=0.7)  # type: ignore[arg-type]


def _row(cid: str, answer: str) -> dict:
    return {"purpose": "turn_plan", "id": "emotion_reply", "version": 2, "label": "emotion", "about": cid,
            "answer": answer, "result": "used", "action": "shown"}


def _cast_plan(kind: str = "group_first", talk: TalkFinished | None = None) -> CastPlan:
    who = WhoPick(pick="chr_a", source="jev", question="who_first", label="who answers first?", p=0.6, confidence=0.6,
                  candidates=[{"characterId": "chr_a", "p": 0.6}, {"characterId": "chr_b", "p": 0.4}])
    return CastPlan(seed="s1:4", kind=kind, order=["chr_a"], who=who,  # type: ignore[arg-type]
                    faces={"chr_a": _face("happy"), "chr_b": _face("sad")},
                    face_rows={"chr_a": _row("chr_a", "happy"), "chr_b": _row("chr_b", "sad")},
                    shared_rows=[{"purpose": "turn_plan", "id": "who_first", "answer": "chr_a", "result": "used"}],
                    talk=talk, calls=[{"purpose": "turn_plan", "costUsd": 0.00005, "latencyMs": 450.0}],
                    graph_path=["state", "ask", "decide", "route"])


def test_cast_request_and_plan_round_trip() -> None:
    at = datetime(2026, 10, 13, 2, 0, tzinfo=UTC)
    req = CastRequest(session=session(), kind="scene", candidates=["chr_a", "chr_b"], forced=["chr_b"],
                      forced_by="round_order", reason="Bo hadn't spoken for 6 turns.", latest="Amara: Well then.",
                      turn_index=4, base_faces={"chr_a": "neutral"}, turns_since={"chr_a": 0, "chr_b": None},
                      steer_block="note", started_at=at, deadline_at=at)
    assert CastRequest.model_validate_json(req.model_dump_json()) == req
    p = _cast_plan()
    assert CastPlan.model_validate_json(p.model_dump_json()) == p


def test_for_speaker_marks_the_other_candidates_not_used() -> None:
    tp = _cast_plan().for_speaker("chr_a")
    assert tp.emotion is not None and tp.emotion.face == "happy" and tp.branch == "quick" and tp.cue is None
    results = {(r["id"], r.get("about")): r["result"] for r in tp.rows}
    assert results == {("who_first", None): "used", ("emotion_reply", "chr_a"): "used",
                       ("emotion_reply", "chr_b"): "not_used",
                       ("docs", "chr_a"): "skipped", ("earlier", "chr_a"): "skipped"}   # U-49: greyed, with why
    assert TurnContext.model_validate_json(TurnContext(
        session=session(), speaker=CharacterView(id="chr_a", name="Amara", profile={}), message_id="m",
        max_tokens=150, plan=tp).model_dump_json()).plan == tp


def test_an_everyone_reply_carries_only_its_own_row() -> None:
    tp = _cast_plan("everyone").for_speaker("chr_b")
    assert [r.get("about") for r in tp.rows if r["id"] == "emotion_reply"] == ["chr_b"]


def test_a_steered_plan_sets_the_cue() -> None:
    tp = _cast_plan("scene", TalkFinished(p=0.9, steer=True, action="steer")).for_speaker("chr_a")
    assert tp.cue == "steer" and _cast_plan("scene").for_speaker("chr_a", cue="next").cue == "next"


def test_follow_request_and_plan_round_trip() -> None:
    at = datetime(2026, 10, 13, 2, 0, tzinfo=UTC)
    req = FollowRequest(session=session(), first_id="chr_a", first_name="Amara", first_message_id="msg_1",
                        first_text="It depends.", message="Should I go?", candidates=["chr_b"], started_at=at)
    assert FollowRequest.model_validate_json(req.model_dump_json()) == req
    fp = FollowPlan(seed="s1:4:follow", second="chr_b", outcome="jev", faces={"chr_b": _face("surprised")},
                    face_rows={"chr_b": _row("chr_b", "surprised")},
                    shared_rows=[{"purpose": "follow_plan", "id": "who_second", "answer": "chr_b", "result": "used"}])
    assert FollowPlan.model_validate_json(fp.model_dump_json()) == fp
    tp = fp.for_speaker("chr_b", answered="Amara")
    assert tp.cue == "second" and tp.answered == "Amara" and tp.emotion is not None
    nobody = fp.model_copy(update={"second": None, "outcome": "none"})
    assert {r["result"] for r in nobody.rows_for_first() if r["id"] == "emotion_reply"} == {"not_used"}
