"""E4's mood line (docs/ai/06 E4; turn-plan-emotion D16; persona-prompt "Phrase per face"): every case in
`tests/fixtures/mood_line/cases.json`, which `personaPrompt.ts`'s `moodLine()` runs too."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from horizon.ai.agent.emotion import EMOTIONS
from horizon.ai.agent.persona import MOOD_PHRASES, PROMPT_VERSION, PROMPT_VERSION_MOOD, mood_line

CASES = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "mood_line" / "cases.json")
                   .read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['face']}-{'manual' if c['manual'] else 'auto'}")
def test_phrase_per_face(case: dict[str, object]) -> None:
    assert mood_line(str(case["face"]), bool(case["manual"])) == case["line"]


def test_every_face_but_neutral_has_a_phrase_and_the_versions() -> None:
    assert set(MOOD_PHRASES) == set(EMOTIONS) - {"neutral"}
    assert (PROMPT_VERSION, PROMPT_VERSION_MOOD) == ("agent-9", "agent-10")   # D40: the line is off by default
