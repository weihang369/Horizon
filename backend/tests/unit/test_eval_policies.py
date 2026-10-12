"""The emotion and reaction scoring policies (turn-plan-emotion D26; evaluation-harness "Emotion item with a kept face",
"Floor chosen on dev"). Pure: fixture answers, no requests."""

from __future__ import annotations

from horizon.ai.decider import ChoiceAnswer
from horizon.evals.policies import (
    FLOORS,
    choose_floor,
    emotion_answer,
    emotion_baseline,
    emotion_correct,
    reaction_answer,
    reaction_baseline,
    reaction_correct,
    report,
)


def a(choice: str, conf: float) -> ChoiceAnswer:
    return ChoiceAnswer(choice, confidence=conf, probabilities={choice: conf})


def test_emotion_item_with_a_kept_face() -> None:
    label = {"previous": "thinking", "acceptable": ["sad"], "keep_ok": True}
    face = emotion_answer(a("angry", 0.4), label, floor=0.6)
    assert face == "thinking" and emotion_correct(face, label)
    assert emotion_baseline(label)


def test_a_kept_short_face_fades_and_counts_as_keeping() -> None:
    label = {"previous": "surprised", "acceptable": ["happy"], "keep_ok": True}
    face = emotion_answer(None, label, floor=0.6)
    assert face == "neutral" and emotion_correct(face, label)
    assert not emotion_correct("neutral", {**label, "keep_ok": False})


def test_a_confident_pick_outside_the_set_is_wrong() -> None:
    label = {"previous": "neutral", "acceptable": ["sad"], "keep_ok": False}
    assert emotion_answer(a("happy", 0.9), label, floor=0.6) == "happy"
    assert not emotion_correct("happy", label) and not emotion_baseline(label)


def test_reaction_policy_shows_a_confident_different_face_or_none() -> None:
    label = {"previous": "neutral", "acceptable": ["surprised"]}
    assert reaction_answer(a("surprised", 0.8), label, floor=0.6) == "surprised"
    assert reaction_answer(a("surprised", 0.5), label, floor=0.6) == "none"
    assert reaction_answer(a("none", 0.9), label, floor=0.6) == "none"
    assert reaction_correct("surprised", label) and not reaction_baseline(label)
    assert reaction_baseline({"previous": "neutral", "acceptable": ["none"]})


def test_floor_chosen_on_dev_from_the_grid_beating_both_extremes() -> None:
    # Confident answers are right, unsure ones wrong: a floor between them wins.
    rows = [(a("sad", 0.9), {"previous": "neutral", "acceptable": ["sad"], "keep_ok": False})] * 6
    rows += [(a("angry", 0.55), {"previous": "thinking", "acceptable": ["happy"], "keep_ok": True})] * 4
    out = choose_floor(rows, "emotion")
    assert out["floor"] in FLOORS and out["floor"] == 0.6                     # ties go to the lower floor
    assert out["accuracy"] == 1.0 and out["no_floor"] == 0.6 and out["fallback_only"] == 0.4
    assert out["beats_both"] and set(out["grid"]) == {0.2, 0.3, 0.4, *FLOORS}   # D36: the emotion grid


def test_a_floor_that_cannot_beat_fallback_only_is_flagged() -> None:
    rows = [(a("happy", 0.95), {"previous": "thinking", "acceptable": ["thinking"], "keep_ok": True})] * 5
    out = choose_floor(rows, "emotion")
    assert not out["beats_both"]


# ── 8.2: the report ──
def _row(i: int, split: str, choice: str, conf: float, label: dict, lang: str = "en") -> dict:
    return {"id": f"e{i}", "question_id": "emotion_reply", "split": split, "lang": lang, "label": label,
            "answer": choice, "confidence": conf, "probabilities": {choice: conf}}


def test_the_emotion_report_reads_floor_accuracy_baseline_mcnemar_coverage_and_merge() -> None:
    sad = {"previous": "neutral", "acceptable": ["sad"], "keep_ok": False}
    keep = {"previous": "thinking", "acceptable": ["happy"], "keep_ok": True}
    rows = [_row(i, "dev", "sad", 0.9, sad) for i in range(6)] + [_row(10 + i, "dev", "angry", 0.55, keep) for i in range(4)]
    rows += [_row(20 + i, "test", "sad", 0.9, sad) for i in range(8)]
    rows += [_row(30, "test", "neutral", 0.7, {"previous": "neutral", "acceptable": ["neutral"], "keep_ok": True})]
    rows += [_row(31, "test", "happy", 0.95, keep, lang="ms")]
    out = report(rows, "emotion")
    assert out[0].startswith("## Emotion: floor 0.6")
    assert "English test accuracy 9/9 = 1.00" in out[1]                      # English is what's judged
    assert "baseline (always keep) 1/9" in out[2] and "8 only the policy right" in out[2]
    assert "coverage: Jev's answer used on 9/9" in out[3]
    assert "merge decided 1/9" in out[4]
    assert out[5].startswith("- other languages: 1/1 test items ran") and "isn't judged" in out[5]


def test_the_reaction_report_gives_the_share_shown() -> None:
    lab = {"previous": "neutral", "acceptable": ["surprised"]}
    none = {"previous": "neutral", "acceptable": ["none"]}
    rows = [{**_row(i, "dev", "surprised", 0.8, lab), "question_id": "reaction"} for i in range(3)]
    rows += [{**_row(10 + i, "test", "surprised", 0.8, lab), "question_id": "reaction"} for i in range(3)]
    rows += [{**_row(20, "test", "none", 0.9, none), "question_id": "reaction"}]
    out = report(rows, "reaction")
    assert "English test accuracy 4/4" in out[1] and "always none) 1/4" in out[2]
    assert "reaction share: 3/4" in out[-1]


def test_a_report_without_both_splits_says_so() -> None:
    assert "needs dev and test" in report([_row(1, "dev", "sad", 0.9, {"previous": "neutral", "acceptable": ["sad"]})],
                                          "emotion")[0]
