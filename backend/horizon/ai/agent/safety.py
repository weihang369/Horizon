"""The safety questions in every plan (doc 11 S3, S4, S7; safety design D3–D8, D19, U4; content-safety spec).

A user-written line is asked "unsafe request?" (`unsafe_request`, or `unsafe_note` for a debate Interject or a watch
director's note) and, where care applies, "at risk?" (`at_risk`) in every plan request that sees it until Jev's answer
is stored (D4). They ride the plan's one request with no `about`; this module adds them, reads them and decides:
- **steer** at or above `safety.tSteer`; **care** at or above `safety.tCare`, or by the stay (one of the session's 2
  user lines before it had a stored care yes, D7);
- a stored answer is reused with no question (a regenerate, a later plan); a late, failed or refused answer gives no
  cue, is flagged, and stores nothing, so the next plan that sees the line asks again (D5);
- the frozen `SafetyCue` rides the reply's plan (A9), with its System 1 rows (D19) and its guardrail checks (S3, S4);
- while care is on, the face is kept calm on every path (D8).
"""

from __future__ import annotations

from typing import Any

from horizon.ai.contexts import PlannedFace, SafetyCue, SafetyLine, TurnPlan
from horizon.ai.decider import Answers, DecisionResult, NoulAnswer, Question
from horizon.ai.questions import bank
from horizon.services.ai_meta import StoredSafety

INPUT = "unsafe_request"
NOTE = "unsafe_note"
CARE = "at_risk"
KEYS = (INPUT, NOTE, CARE)
CALM = ("neutral", "sad", "thinking")   # D8: the faces a care reply may show
CALM_ACTION = "care: face kept calm"
ONE_VOICE = {"steer": "one voice: the message was steered", "care": "one voice: the message was answered with care"}


def thresholds() -> dict[str, float]:
    b = bank()
    return {"tSteer": float(b.get(INPUT).thresholds.get("tSteer", 0.7)),
            "tCare": float(b.get(CARE).thresholds.get("tCare", 0.3))}


def asks(line: SafetyLine | None) -> bool:
    """This plan asks about the line: no stored answer, and no other plan asking right now."""
    return line is not None and line.stored is None and line.ask


def input_question(line: SafetyLine) -> str:
    return NOTE if line.note else INPUT


def questions(line: SafetyLine | None) -> dict[str, Question]:
    """The safety questions to add to the plan's request (none when the answer is stored or in flight)."""
    if line is None or not asks(line):
        return {}
    b = bank()
    qid = input_question(line)
    qs: dict[str, Question] = {qid: b.question(qid)}
    if line.care:
        qs[CARE] = b.question(CARE)
    return qs


def state_extra(line: SafetyLine | None) -> dict[str, Any]:
    """A note is its own state field (`quoted_note`, U4): `quoted_latest` there is the last character line."""
    return {"quoted_note": line.text} if line is not None and line.note and asks(line) else {}


def fallbacks(qs: dict[str, Question]) -> Answers:
    """No cue (the fallback adds nothing): the Decider marks them `source="fallback"`, and nothing is stored."""
    return {k: NoulAnswer(0.0) for k in qs if k in KEYS}


def _p(res: DecisionResult | None, key: str) -> float | None:
    a = res.answers.get(key) if res is not None else None
    return a.p if isinstance(a, NoulAnswer) and a.source != "fallback" else None


def decide(line: SafetyLine | None, res: DecisionResult | None) -> SafetyCue | None:
    """The cue this line gives its replies, from the stored answers or from this plan's request (`res`)."""
    if line is None:
        return None
    th = thresholds()
    qid = input_question(line)
    base: dict[str, Any] = {"message_id": line.message_id, "wording": line.wording, "question": qid}
    stored = StoredSafety.from_json(line.stored) if line.stored is not None else None
    if stored is not None:
        own_care = bool(stored.care) if line.care else False
        care = line.care and (own_care or line.stay)
        return SafetyCue(**base, steer=stored.steer, care=care, stay=care and not own_care, p_input=stored.p_input,
                         p_care=stored.p_care if line.care else None, input_outcome="stored",
                         care_outcome="stored" if line.care else None, versions=dict(stored.versions))
    if not line.ask:   # another plan is asking now: no answer yet, so no cue (a late cue beats none)
        care = line.care and line.stay
        return SafetyCue(**base, care=care, stay=care, input_outcome="pending",
                         care_outcome="pending" if line.care else None)
    why = "late" if res is not None and res.failure == "timeout" else "fallback"
    p_in = _p(res, qid)
    p_care = _p(res, CARE) if line.care else None
    own_care = p_care is not None and p_care >= th["tCare"]
    care = line.care and (own_care or line.stay)
    b = bank()
    versions = {qid: b.get(qid).version, **({CARE: b.get(CARE).version} if line.care else {})}
    return SafetyCue(**base, steer=p_in is not None and p_in >= th["tSteer"], care=care, stay=care and not own_care,
                     p_input=p_in, p_care=p_care, input_outcome="jev" if p_in is not None else why,  # type: ignore[arg-type]
                     care_outcome=("jev" if p_care is not None else why) if line.care else None,  # type: ignore[arg-type]
                     asked=True, versions=versions)


def to_store(cue: SafetyCue | None) -> StoredSafety | None:
    """What the runtime writes for the line (D5): only answers that came from Jev in this plan's request."""
    if cue is None or not cue.asked or cue.input_outcome != "jev" or cue.p_input is None:
        return None
    if cue.care_outcome is not None and (cue.care_outcome != "jev" or cue.p_care is None):
        return None
    th = thresholds()
    return StoredSafety(steer=cue.steer, care=(cue.p_care >= th["tCare"]) if cue.p_care is not None else None,
                        p_input=cue.p_input, p_care=cue.p_care, versions=dict(cue.versions))


def stay_on(previous: list[StoredSafety | None]) -> bool:
    """D7: care stays on when one of the session's 2 user lines before this one had a stored care yes (no row: no)."""
    return any(s is not None and s.care for s in previous[-2:])


# ── what a reply shows (D19; S3, S4) ──
def _flag_action(outcome: str) -> str:
    return {"late": "flagged: Jev late", "pending": "flagged: still being checked"}.get(outcome, "flagged: Jev failed")


def rows(cue: SafetyCue | None, *, purpose: str) -> list[dict[str, Any]]:
    """The shared System 1 rows: one for the input question and one for "at risk?" when it applies. A stored answer is
    `used` with no call."""
    if cue is None:
        return []
    th = thresholds()
    b = bank()
    out: list[dict[str, Any]] = []
    e = b.get(cue.question)
    row: dict[str, Any] = {"purpose": purpose, "id": cue.question, "version": e.version, "label": e.label}
    stored = " (stored)" if cue.input_outcome == "stored" else ""
    if cue.p_input is None:
        row.update(answer="no", compared=[], result="fallback", action=_flag_action(cue.input_outcome))
    else:
        p = round(cue.p_input, 4)
        row.update(answer="yes" if cue.steer else "no", p=p,
                   compared=[{"name": "tSteer", "value": p, "threshold": th["tSteer"]}],
                   result="used" if cue.steer or stored else "below_threshold",
                   action=("steer cue" if cue.steer else "no cue") + stored)
    out.append(row)
    if cue.care_outcome is not None:
        e = b.get(CARE)
        crow: dict[str, Any] = {"purpose": purpose, "id": CARE, "version": e.version, "label": e.label}
        stored = " (stored)" if cue.care_outcome == "stored" else ""
        own = cue.care and not cue.stay
        if cue.p_care is None:
            crow.update(answer="no", compared=[], result="fallback",
                        action="care (stay)" if cue.stay else _flag_action(cue.care_outcome))
        else:
            p = round(cue.p_care, 4)
            crow.update(answer="yes" if own else "no", p=p,
                        compared=[{"name": "tCare", "value": p, "threshold": th["tCare"]}],
                        result="used" if cue.care or stored else "below_threshold",
                        action=("care cue" if own else "care (stay)" if cue.stay else "no cue") + stored)
        out.append(crow)
    return out


def checks(cue: SafetyCue | None) -> list[dict[str, Any]]:
    """`TurnTrace.guardrail.checks` for the line (S3, S4): `input`, and `care` when it applies. Jev failed or late: a
    flag with no `p`."""
    if cue is None:
        return []
    out: list[dict[str, Any]] = [{"name": "input", "verdict": "flag" if cue.steer or cue.p_input is None else "pass",
                                  **({"p": round(cue.p_input, 4)} if cue.p_input is not None else {})}]
    if cue.care_outcome is not None:
        out.append({"name": "care", "verdict": "flag" if cue.care or cue.p_care is None else "pass",
                    **({"p": round(cue.p_care, 4)} if cue.p_care is not None else {})})
    return out


def calm_face(face: PlannedFace) -> PlannedFace:
    """D8: a face outside {neutral, sad, thinking} becomes neutral (code chose it)."""
    if face.face in CALM:
        return face
    return face.model_copy(update={"face": "neutral", "source": "default"})


def calm(plan: TurnPlan | None) -> TurnPlan | None:
    """D8: while the reply's care cue is on, the planned face is calm on every path (Jev's pick, the kept face, the
    Jev-failed path), and the speaker's emotion row says so."""
    if plan is None or plan.safety is None or not plan.safety.care or plan.emotion is None:
        return plan
    face = calm_face(plan.emotion)
    if face is plan.emotion:
        return plan
    rows = [{**r, "action": CALM_ACTION} if str(r.get("id", "")).startswith("emotion_")
            and r.get("result") != "not_used" else r for r in plan.rows]
    out: TurnPlan = plan.model_copy(update={"emotion": face, "rows": rows})
    return out


def one_voice_reason(cue: SafetyCue) -> str:
    return ONE_VOICE["care" if cue.care else "steer"]
