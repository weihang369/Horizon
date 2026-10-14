"""The speaker's face rule and its System 1 row (turn-plan-emotion task 2.7; design D12, D13; speaker-emotion "The face
rule", "Neutral and none are one answer on a neutral face", "The trace explains the face")."""

from __future__ import annotations

from typing import Any

import pytest

from horizon.ai.agent.emotion import candidates, decide_face, emotion_row, merges
from horizon.ai.decider import ChoiceAnswer

FADE = frozenset({"surprised", "embarrassed"})


def ans(choice: str, conf: float, **probs: float) -> ChoiceAnswer:
    return ChoiceAnswer(choice, confidence=conf, probabilities=probs or {choice: conf})


def row(f: Any) -> dict[str, Any]:
    return emotion_row(f, qid="emotion_reply", version=1, label="emotion", about="chr_a")


def test_confident_pick_is_shown() -> None:
    f = decide_face(ans("sad", 0.74, sad=0.6, thinking=0.2, none=0.1, happy=0.1), base="happy", floor=0.6, fade=FADE)
    assert (f.face, f.source, f.outcome) == ("sad", "classifier", "jev")
    r = row(f)
    assert (r["answer"], r["p"], r["confidence"], r["result"], r["action"]) == ("sad", 0.6, 0.74, "used", "shown")
    assert r["compared"] == [{"name": "confidence", "value": 0.74, "threshold": 0.6}]


def test_spec_candidates_leave_none_out() -> None:
    f = decide_face(ans("sad", 0.74, sad=0.6, thinking=0.2, none=0.1, happy=0.1), base="happy", floor=0.6, fade=FADE)
    assert [c["label"] for c in f.candidates] == ["sad", "thinking", "happy"]


def test_unsure_keeps_the_face() -> None:
    f = decide_face(ans("angry", 0.41), base="thinking", floor=0.6, fade=FADE)
    assert (f.face, f.source, f.outcome, f.faded) == ("thinking", "default", "below_floor", False)
    r = row(f)
    assert (r["answer"], r["result"], r["action"]) == ("angry", "below_threshold", "kept")


def test_none_keeps_and_a_short_face_fades() -> None:
    f = decide_face(ans("none", 0.8), base="surprised", floor=0.6, fade=FADE)
    assert (f.face, f.source, f.outcome, f.faded) == ("neutral", "default", "none", True)
    assert (row(f)["answer"], row(f)["result"], row(f)["action"]) == ("none", "used", "faded to neutral")


@pytest.mark.parametrize(("failure", "outcome"), [("timeout", "late"), ("network", "fallback"), (None, "fallback")])
def test_a_failed_call_keeps_or_fades_with_no_p(failure: str | None, outcome: str) -> None:
    f = decide_face(None, base="embarrassed", floor=0.6, fade=FADE, failure=failure)
    assert (f.face, f.source, f.outcome, f.p, f.candidates) == ("neutral", "default", outcome, None, [])
    r = row(f)
    assert (r["answer"], r["result"], r["action"]) == ("faded to neutral", "fallback", "faded to neutral") and "p" not in r
    kept = row(decide_face(ChoiceAnswer("none", source="fallback"), base="sad", floor=0.6, fade=FADE))
    assert kept["answer"] == "kept sad" and kept["result"] == "fallback"


def test_the_merge_on_a_neutral_face() -> None:   # the spec's example
    f = decide_face(ans("none", 0.38, none=0.38, neutral=0.35, happy=0.27), base="neutral", floor=0.6, fade=FADE)
    assert (f.face, f.source, f.outcome) == ("neutral", "classifier", "jev")
    assert f.compared == [{"name": "p_neutral+p_none", "value": 0.73, "threshold": 0.6}] and f.confidence == 0.38
    assert f.candidates[0] == {"label": "neutral", "p": 0.73}


def test_no_merge_when_the_base_is_not_neutral() -> None:
    f = decide_face(ans("none", 0.38, none=0.38, neutral=0.35, happy=0.27), base="sad", floor=0.6, fade=FADE)
    assert (f.face, f.outcome) == ("sad", "none")      # none = keep the current face


def test_a_merged_neutral_can_overtake_a_weak_pick() -> None:
    f = decide_face(ans("happy", 0.4, happy=0.4, neutral=0.3, none=0.3), base="neutral", floor=0.6, fade=FADE)
    assert (f.face, f.pick, f.compared[0]["name"]) == ("neutral", "neutral", "p_neutral+p_none")


def test_manual_records_the_pick() -> None:
    f = decide_face(ans("happy", 0.9), base="thinking", floor=0.6, fade=FADE, manual=True)
    assert f.face == "happy" and row(f)["action"] == "recorded (MANUAL)"


def test_not_used_row() -> None:
    f = decide_face(ans("happy", 0.9), base="thinking", floor=0.6, fade=FADE)
    r = emotion_row(f, qid="emotion_reply", version=1, label="emotion", about="chr_b", used=False)
    assert r["result"] == "not_used" and r["about"] == "chr_b"


def test_candidates_ignore_unknown_keys_and_rank_stably() -> None:
    assert candidates({"happy": 0.4, "sad": 0.4, "none": 0.2}, "happy") == [{"label": "happy", "p": 0.4},
                                                                            {"label": "sad", "p": 0.4}]


def test_emotion_line_does_not_merge_neutral_and_none() -> None:
    """M11 D33 (the user's choice after D20's measure): `emotion_line` (watch, group, debate lines) keeps `none` as
    "keep" and `neutral` as its own answer; the other face questions still merge."""
    assert not merges("emotion_line") and merges("emotion_reply") and merges("emotion_opening")
    a = ans("thinking", 0.41, thinking=0.41, neutral=0.24, none=0.21)   # 10.5's emw-023: merged, neutral wins
    merged = decide_face(a, base="neutral", floor=0.2, fade=FADE, merge=merges("emotion_reply"))
    line = decide_face(a, base="neutral", floor=0.2, fade=FADE, merge=merges("emotion_line"))
    assert (merged.face, line.face) == ("neutral", "thinking")
