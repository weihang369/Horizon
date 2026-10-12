"""The face check's row, cut and verdict (doc 13 W2; turn-plan-emotion D23, D24; face-check spec)."""

from __future__ import annotations

from typing import Any

import pytest

from horizon.ai.agent.face_check import JevFaceCheck, row, tail, verdict
from horizon.ai.contexts import SessionContext, WorldView
from horizon.ai.decider import ChoiceAnswer, DecisionResult
from horizon.ai.questions import bank
from horizon.domain.pricing import count_tokens


@pytest.mark.parametrize(("face", "pick", "want"), [
    ("sad", "sad", "yes"),
    ("happy", "angry", "clash"),
    ("angry", "happy", "clash"),
    ("sad", "happy", "clash"),
    ("happy", "thinking", "no (words read: thinking)"),
    ("surprised", "neutral", "no (words read: neutral)"),
])
def test_verdict(face: str, pick: str, want: str) -> None:
    assert verdict(face, pick) == want


def test_the_row_is_display_only_with_p_for_the_face_shown() -> None:
    r = row(version=1, label="face and words agree?", face="sad", pick="sad", p=0.66)
    assert r == {"purpose": "face_check", "id": "face_check", "version": 1, "label": "face and words agree?",
                 "answer": "yes", "p": 0.66, "compared": [], "result": "shown_only"}


def test_a_long_reply_is_cut_to_its_last_600_tokens() -> None:
    text = " ".join(f"word{i:04d}" for i in range(300))   # ~900 tokens at bytes / 3
    assert count_tokens(text) > 850
    cut = tail(text)
    assert count_tokens(cut) <= 600 and text.endswith(cut) and cut.startswith("word")
    assert tail("Short.") == "Short."


def test_the_bank_entry_asks_the_seven_emotions_about_the_words_only() -> None:
    e = bank().get("face_check")
    assert set(e.state) == {"quoted_reply"} and e.floor is None and e.deadline == "face_check"
    q = bank().question("face_check", seed="s:msg_1:face")
    assert set(q.options) == {"neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed"}  # type: ignore[union-attr]
    assert q.meta is not None and q.meta.label == "face and words agree?"


class _Call:
    def __init__(self, res: DecisionResult) -> None:
        self.res = res

    async def by(self, _at: Any) -> DecisionResult:
        return self.res

    def cancel(self) -> None:
        pass


class _Decider:
    def __init__(self, res: DecisionResult) -> None:
        self.res = res
        self.state: Any = None

    def now(self) -> Any:
        from datetime import UTC, datetime
        return datetime(2026, 10, 12, tzinfo=UTC)

    def timeout_for(self, _k: str) -> float:
        return 1.5

    def start(self, state: Any, questions: Any, ctx: Any, *, purpose: str) -> _Call:
        self.state = state
        assert purpose == "face_check" and list(questions) == ["face_check"]
        return _Call(self.res)


class _Deps:
    def __init__(self, d: _Decider) -> None:
        self.d = d

    def decider(self) -> _Decider:
        return self.d


def _ctx() -> SessionContext:
    return SessionContext(session_id="ses_1", seed="s", world=WorldView(id="w", name="W"), mode="one_on_one", title="t",
                          participants=[], recent=[])


async def test_the_check_sends_only_the_quoted_reply_and_skips_a_fallback() -> None:
    d = _Decider(DecisionResult(answers={"face_check": ChoiceAnswer("happy", 0.7, {"happy": 0.7, "sad": 0.1})}))
    out = await JevFaceCheck(_Deps(d)).check(_ctx(), "msg_1", "chr_a", "sad", "Oh, that's wonderful news!")
    assert d.state == {"quoted_reply": "Oh, that's wonderful news!"}
    assert out is not None and out[0]["answer"] == "clash" and out[0]["p"] == 0.1 and out[1] is None
    late = _Decider(DecisionResult(answers={"face_check": ChoiceAnswer("sad", source="fallback")}))
    assert await JevFaceCheck(_Deps(late)).check(_ctx(), "msg_1", "chr_a", "sad", "Hi.") is None
