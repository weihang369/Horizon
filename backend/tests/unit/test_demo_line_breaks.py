"""Demo parity for bubbles (docs/requirements D-46; ai-foundation design D22; task 4.3): chat-mode character lines in
the shipped seed sessions and the scripted bank may hold line breaks (the UI shows them as up to 4 bubbles); debate
lines never do."""

from __future__ import annotations

import json

from horizon.ai.scripted.bank import chat_lines, debate_line
from tests.conftest import SEED_DIR


def seed_messages(sid: str) -> list[dict[str, object]]:
    doc = json.loads((SEED_DIR / "sessions" / sid / "messages.json").read_text(encoding="utf-8"))
    return [m for m in doc["data"] if m["author"]["type"] == "character"]  # type: ignore[index]


def test_no_debate_message_contains_a_line_break() -> None:
    for m in seed_messages("ses_seedDebate4Day"):
        assert "\n" not in str(m["content"]), m["id"]
    for phase in ("opening", "rebuttal", "closing"):
        for i in range(3):
            assert "\n" not in debate_line(phase, "This house would tax sugary drinks", "prop", i).text


def test_the_amara_seed_has_a_multi_line_reply() -> None:
    assert any(str(m["content"]).count("\n") >= 2 for m in seed_messages("ses_seedAmaraHeadache"))


def test_chat_modes_carry_breaks_but_never_blank_lines() -> None:
    for sid in ("ses_seedAmaraHeadache", "ses_seedHanaLongDay", "ses_seedDinner", "ses_seedRainySunday"):
        contents = [str(m["content"]) for m in seed_messages(sid)]
        assert any("\n" in c for c in contents), sid
        assert not any("\n\n" in c or c.startswith("\n") or c.endswith("\n") for c in contents), sid
    lines = chat_lines({"name": "Ana", "role": "Nurse", "tagline": "One step at a time."}, "my sleep is bad")
    assert sum("\n" in ln.text for ln in lines) >= 4
