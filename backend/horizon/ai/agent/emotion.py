"""The speaker's face from Jev's emotion answer: pure code, shared by the planner and the evaluation (docs/ai/06 E1–E3;
turn-plan-emotion design D12, D13; speaker-emotion spec).

- **The merge (D12).** On a `neutral` base face, `neutral` and `none` are one answer: their probabilities are added as
  `neutral` before the pick and the floor. When that makes `neutral` the pick, the merged sum is what meets the floor
  (named `p_neutral+p_none`); otherwise Jev's own confidence does.
- **The rule (E3).** Jev's pick at or above the floor is shown (`classifier`). `none`, an unsure pick, a failed or late
  call all keep the base face (`default`), and a kept face in `emotion.fade` (surprised, embarrassed) becomes neutral.
- **The row (D13).** One System 1 row per candidate asked, worded as W1 says: the answer, `p` for that answer, the
  confidence and the comparison, the result, and what code did.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from horizon.ai.contexts import FaceOutcome, PlannedFace
from horizon.ai.decider import ChoiceAnswer

EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")
NONE = "none"
CONFIDENCE = "confidence"
MERGED = "p_neutral+p_none"


def _r(x: float) -> float:
    return round(float(x), 4)


def kept(base: str, fade: frozenset[str]) -> tuple[str, bool]:
    """The face kept on `none`, unsure or a fallback: the base, or neutral when the base is a short face (E3)."""
    return ("neutral", True) if base in fade else (base, False)


def merged(probs: Mapping[str, float], base: str) -> dict[str, float]:
    """The probabilities after D12's merge (only on a neutral base)."""
    out = {k: float(v) for k, v in probs.items()}
    if base == "neutral":
        out["neutral"] = out.get("neutral", 0.0) + out.pop(NONE, 0.0)
    return out


def candidates(probs: Mapping[str, float], base: str, n: int = 3) -> list[dict[str, Any]]:
    """`TurnTrace.emotion.candidates`: the top n emotions by probability, merged as above, `none` left out (E2)."""
    m = {k: v for k, v in merged(probs, base).items() if k in EMOTIONS}
    ranked = sorted(m.items(), key=lambda kv: (-kv[1], EMOTIONS.index(kv[0])))
    return [{"label": k, "p": _r(v)} for k, v in ranked[:n]]


def decide_face(answer: ChoiceAnswer | None, *, base: str, floor: float, fade: frozenset[str], manual: bool = False,
                failure: str | None = None) -> PlannedFace:
    """The face for one candidate. `answer` None or a fallback answer means Jev failed; `failure` "timeout" marks it
    late."""
    if answer is None or answer.source == "fallback":
        face, faded = kept(base, fade)
        outcome: FaceOutcome = "late" if failure == "timeout" else "fallback"
        return PlannedFace(face=face, source="default", base=base, outcome=outcome, faded=faded, manual=manual)
    probs = dict(answer.probabilities or {answer.choice: float(answer.confidence or 0.0)})
    m = merged(probs, base)
    pick = answer.choice
    value = float(answer.confidence if answer.confidence is not None else probs.get(pick, 0.0))
    name = CONFIDENCE
    if base == "neutral":
        top = max(m, key=lambda k: (m[k], k == "neutral"))   # a tie goes to keeping the neutral face
        if top == "neutral" or pick in ("neutral", NONE):
            pick, value, name = "neutral", m.get("neutral", 0.0), MERGED
    compared = [{"name": name, "value": _r(value), "threshold": floor}]
    p = _r(m.get(pick, probs.get(pick, 0.0)))
    common: dict[str, Any] = {   # `confidence` stays Jev's own (W1); the merged sum shows only in `compared`
        "base": base, "pick": pick, "p": p,
        "confidence": _r(answer.confidence) if answer.confidence is not None else None, "compared": compared,
        "candidates": candidates(probs, base), "manual": manual}
    if pick == NONE:
        face, faded = kept(base, fade)
        return PlannedFace(face=face, source="default", outcome="none", faded=faded, **common)
    if value >= floor:
        return PlannedFace(face=pick, source="classifier", outcome="jev", **common)
    face, faded = kept(base, fade)
    return PlannedFace(face=face, source="default", outcome="below_floor", faded=faded, **common)


def _action(f: PlannedFace) -> str:
    if f.manual:
        return "recorded (MANUAL)"
    if f.outcome == "jev":
        return "shown"
    return "faded to neutral" if f.faded else "kept"


def emotion_row(f: PlannedFace, *, qid: str, version: int, label: str, about: str, used: bool = True) -> dict[str, Any]:
    """The System 1 row for one candidate (W1, D13). `used` False: asked but didn't speak (`not_used`, M10's case)."""
    row: dict[str, Any] = {"purpose": "turn_plan", "id": qid, "version": version, "label": label, "about": about}
    if f.outcome in ("fallback", "late"):
        row.update(answer="faded to neutral" if f.faded else f"kept {f.face}", result="fallback", action=_action(f))
        return row if used else {**row, "result": "not_used"}
    row.update(answer=f.pick or NONE, p=f.p, compared=list(f.compared))
    if f.confidence is not None:
        row["confidence"] = f.confidence
    row["result"] = ("used" if f.outcome in ("jev", "none") else "below_threshold") if used else "not_used"
    row["action"] = _action(f)
    return row
