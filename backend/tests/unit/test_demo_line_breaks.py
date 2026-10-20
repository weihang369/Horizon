"""Demo parity for bubbles (docs/requirements D-46; ai-foundation design D22; task 4.3): chat-mode character lines in
the shipped seed sessions and the scripted bank may hold line breaks (the UI shows them as up to 4 bubbles); debate
lines never do. Since v1 the seed sessions are real recordings: the model writes paragraphs (blank lines, which the
UI's bubble split collapses), and broke the debate prompt's "one paragraph" once in 10 turns."""

from __future__ import annotations

import json

from horizon.ai.scripted.bank import chat_lines, debate_line
from tests.conftest import SEED_DIR


def seed_messages(sid: str) -> list[dict[str, object]]:
    doc = json.loads((SEED_DIR / "sessions" / sid / "messages.json").read_text(encoding="utf-8"))
    return [m for m in doc["data"] if m["author"]["type"] == "character"]  # type: ignore[index]


def test_no_debate_message_contains_a_line_break() -> None:
    for m in seed_messages("ses_seedDebate4Day"):   # at most a paragraph break, never a single line break
        assert "\n" not in str(m["content"]).replace("\n\n", ""), m["id"]
    for phase in ("opening", "rebuttal", "closing"):
        for i in range(3):
            assert "\n" not in debate_line(phase, "This house would tax sugary drinks", "prop", i).text


def test_the_amara_seed_has_a_multi_line_reply() -> None:
    assert any(str(m["content"]).count("\n") >= 2 for m in seed_messages("ses_seedAmaraHeadache"))


def test_chat_modes_carry_breaks_but_never_blank_lines() -> None:
    sids = ("ses_seedAmaraHeadache", "ses_seedHanaLongDay", "ses_seedDinner", "ses_seedRainySunday")
    broken = [sid for sid in sids if any("\n" in str(m["content"]) for m in seed_messages(sid))]
    assert len(broken) >= len(sids) - 1, broken   # the model chooses the breaks: most sessions show several bubbles
    for sid in sids:
        for c in (str(m["content"]) for m in seed_messages(sid)):
            assert c == c.strip(), sid   # blank lines inside collapse in the UI; none at either end
    lines = chat_lines({"name": "Ana", "role": "Nurse", "tagline": "One step at a time."}, "my sleep is bad")
    assert sum("\n" in ln.text for ln in lines) >= 4
