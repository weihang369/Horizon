"""Unlisted `[n]` markers leave the reply stream (v1 test stage; horizon/ai/naive/markers.py).

Found by recording the seed debate on 2026-10-21: 5 of 12 turns wrote `[n]` for passages they were never given.
"""

from __future__ import annotations

import pytest

from horizon.ai.naive.markers import MarkerFilter


def run(listed: set[int], pieces: list[str]) -> str:
    f = MarkerFilter(listed)
    return "".join(f.feed(p) for p in pieces) + f.close()


@pytest.mark.parametrize(("listed", "text", "want"), [
    (set(), "the feared collapse never arrived [2]. Second, structure [3].",
     "the feared collapse never arrived. Second, structure."),
    ({1}, "a policy too [1]. History [2], then method [4].", "a policy too [1]. History, then method."),
    ({1, 2}, "caffeine [2][1]. Dull [3].", "caffeine [2][1]. Dull."),
    (set(), "see [1](https://example.org) here", "see [1](https://example.org) here"),
    (set(), "[laughs] and [123] stay", "[laughs] and [123] stay"),
    (set(), "ends on a marker [2]", "ends on a marker"),
    (set(), "line one\n[2] line two", "line one\n line two"),
])
def test_only_listed_markers_survive(listed: set[int], text: str, want: str) -> None:
    assert run(listed, [text]) == want
    assert run(listed, list(text)) == want   # the same text streamed one character at a time


def test_held_text_waits_only_while_it_could_still_be_a_marker() -> None:
    f = MarkerFilter(set())
    assert f.feed("arrived ") == "arrived"
    assert f.feed("[") == ""
    assert f.feed("2") == ""
    assert f.feed("]") == ""
    assert f.feed(". Next") == ". Next"
    assert f.feed(" [x") == " [x"
    assert f.close() == ""
