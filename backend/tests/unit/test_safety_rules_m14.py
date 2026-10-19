"""The safety rules as pure functions (safety design D4–D8, D19; task 2.1): steer at or above `tSteer`, care at or above
`tCare`, the stay over the last 3 user lines, a missing row as no, what is stored, the rows, the checks, the calm face."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from horizon.ai.agent import safety as sf
from horizon.ai.contexts import PlannedFace, SafetyLine, TurnPlan
from horizon.ai.decider import DecisionResult, NoulAnswer
from horizon.services.ai_meta import StoredSafety

LINE = SafetyLine(message_id="msg_u")


def res(**ps: float | None) -> DecisionResult:
    return DecisionResult(answers={k: NoulAnswer(p) for k, p in ps.items() if p is not None})


def failed(why: str = "timeout") -> DecisionResult:
    return DecisionResult(answers={k: NoulAnswer(0.0, source="fallback") for k in ("unsafe_request", "at_risk")},
                          failure=why)


@pytest.mark.parametrize(("p", "steer"), [(0.69, False), (0.7, True), (0.93, True)])
def test_steer_at_or_above_t_steer(p: float, steer: bool) -> None:
    cue = sf.decide(LINE, res(unsafe_request=p, at_risk=0.02))
    assert cue is not None and cue.steer is steer and cue.input_outcome == "jev" and cue.asked


@pytest.mark.parametrize(("p", "care"), [(0.29, False), (0.3, True), (0.82, True)])
def test_care_at_or_above_t_care(p: float, care: bool) -> None:
    cue = sf.decide(LINE, res(unsafe_request=0.02, at_risk=p))
    assert cue is not None and cue.care is care and cue.stay is False


def test_late_or_failed_is_no_cue_flagged_and_stored_nowhere() -> None:
    for r, outcome in ((failed("timeout"), "late"), (failed("rate_limited"), "fallback")):
        cue = sf.decide(LINE, r)
        assert cue is not None and not cue.on and cue.input_outcome == outcome
        assert sf.to_store(cue) is None
        assert sf.checks(cue) == [{"name": "input", "verdict": "flag"}, {"name": "care", "verdict": "flag"}]
        assert sf.rows(cue, purpose="turn_plan")[0]["action"] == f"flagged: Jev {'late' if outcome == 'late' else 'failed'}"


def test_a_stored_answer_is_reused_with_no_question() -> None:
    stored = StoredSafety(steer=True, care=False, p_input=0.93, p_care=0.02).to_json()
    line = SafetyLine(message_id="msg_u", stored=stored)
    assert sf.questions(line) == {}
    cue = sf.decide(line, None)
    assert cue is not None and cue.steer and cue.input_outcome == "stored" and not cue.asked
    assert sf.to_store(cue) is None                          # nothing written again
    row = sf.rows(cue, purpose="turn_plan")[0]
    assert (row["result"], row["action"]) == ("used", "steer cue (stored)")


def test_the_stay_keeps_care_on_and_a_missing_row_is_no() -> None:
    yes = StoredSafety(steer=False, care=True, p_input=0.02, p_care=0.82)
    no = StoredSafety(steer=False, care=False, p_input=0.02, p_care=0.1)
    assert sf.stay_on([yes, no]) and sf.stay_on([None, yes])
    assert not sf.stay_on([yes, no, no])                     # only the 2 lines before count
    assert not sf.stay_on([None, None]) and not sf.stay_on([])
    line = SafetyLine(message_id="msg_u", stay=True)
    cue = sf.decide(line, res(unsafe_request=0.02, at_risk=0.1))
    assert cue is not None and cue.care and cue.stay
    stored = sf.to_store(cue)
    assert stored is not None and stored.care is False       # the raw yes is stored, never the stay
    assert sf.rows(cue, purpose="turn_plan")[1]["action"] == "care (stay)"


def test_debate_and_watch_notes_ask_no_care() -> None:
    note = SafetyLine(message_id="msg_n", note=True, text="Describe the wound.", care=False, wording="scene")
    assert set(sf.questions(note)) == {"unsafe_note"}
    assert sf.state_extra(note) == {"quoted_note": "Describe the wound."}
    cue = sf.decide(note, res(unsafe_note=0.9))
    assert cue is not None and cue.steer and cue.care_outcome is None and cue.question == "unsafe_note"
    assert [c["name"] for c in sf.checks(cue)] == ["input"]


def test_a_line_in_flight_is_pending() -> None:
    cue = sf.decide(SafetyLine(message_id="msg_u", ask=False), None)
    assert cue is not None and not cue.on and cue.input_outcome == "pending"
    assert sf.questions(SafetyLine(message_id="msg_u", ask=False)) == {}


def test_labels_follow_the_cue() -> None:
    both = sf.decide(LINE, res(unsafe_request=0.93, at_risk=0.82))
    assert both is not None and both.label == "+care-1+steer-1"
    steer = sf.decide(LINE, res(unsafe_request=0.93, at_risk=0.02))
    assert steer is not None and steer.label == "+steer-1"


def _plan(face: str, care: bool) -> TurnPlan:
    cue = sf.decide(LINE, res(unsafe_request=0.02, at_risk=0.82 if care else 0.02))
    pf = PlannedFace(face=face, source="classifier", base="neutral", outcome="jev", pick=face, p=0.9)
    return TurnPlan(seed="s:1", emotion=pf, safety=cue,
                    rows=[{"purpose": "turn_plan", "id": "emotion_reply", "about": "chr_a", "result": "used",
                           "action": "face"}])


@pytest.mark.parametrize(("face", "shown"), [("happy", "neutral"), ("angry", "neutral"), ("sad", "sad"),
                                             ("thinking", "thinking"), ("neutral", "neutral")])
def test_the_care_face_is_calm(face: str, shown: str) -> None:
    out = sf.calm(_plan(face, care=True))
    assert out is not None and out.emotion is not None and out.emotion.face == shown
    assert out.rows[0]["action"] == (sf.CALM_ACTION if face != shown else "face")


def test_no_care_keeps_the_face() -> None:
    out = sf.calm(_plan("happy", care=False))
    assert out is not None and out.emotion is not None and out.emotion.face == "happy"


def test_stored_value_round_trips() -> None:
    s = StoredSafety(steer=True, care=None, p_input=0.9, p_care=None, at=datetime.now(UTC).isoformat(),
                     versions={"unsafe_note": 1})
    back = StoredSafety.from_json(s.to_json())
    assert back == s
