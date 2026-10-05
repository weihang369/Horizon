"""The inline emotion tag parser against the shared fixtures (ai-ports "Inline emotion tag"; task 10.1).
`frontend/src/engine/tagParser.fixtures.test.ts` runs a TS reference parser over the same files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from horizon.ai.naive.tag_parser import ParsedEmotion, ParsedText, TagParser, parse_all

DIR = Path(__file__).resolve().parents[1] / "fixtures" / "tag_parser"
CASES = sorted(DIR.glob("*.json"))


def test_found_the_cases() -> None:
    assert len(CASES) >= 6


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_fixture(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    emotion, text = parse_all(case["chunks"], case["previous"])
    assert (emotion.emotion, emotion.source, text) == (case["expected"]["emotion"], case["expected"]["source"],
                                                        case["expected"]["text"])


def test_emotion_comes_before_any_token() -> None:
    p = TagParser()
    out = p.feed("<e:ha") + p.feed("ppy>Hel") + p.feed("lo") + p.close()
    assert out == [ParsedEmotion("happy", "llm"), ParsedText("Hel"), ParsedText("lo")]
