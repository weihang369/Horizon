"""The `agent` request, byte for byte (turn-plan-emotion tasks 4.1, 4.3; design D16; persona-prompt "The mood line never
touches the cached prefix").

`backend/tests/fixtures/agent_request/request_agent1_*.json` were recorded from the `agent-1` engine BEFORE the mood
line existed (task 4.1). `agent-2` must send exactly those requests on a neutral, a MANUAL and an unplanned turn, and
differ only in the tail on a planned non-neutral one.

Recording again (only if `agent-1`'s system message itself changes, which re-versions the prompt):
`HORIZON_RECORD_REQUESTS=1 uv run pytest tests/sessions/test_agent_request_fixtures.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.contexts import LineHint, PlannedFace, TurnContext, TurnPlan
from tests.sessions.test_agent_turn import ctx, engine, mv

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "agent_request"
RECORD = os.environ.get("HORIZON_RECORD_REQUESTS") == "1"


def planned(base: TurnContext, face: str, *, manual: bool = False) -> TurnContext:
    pf = PlannedFace(face=face, source="classifier" if face != "neutral" else "default", base="thinking",
                     outcome="jev", pick=face, p=0.8, confidence=0.8, manual=manual)
    return base.model_copy(update={"plan": TurnPlan(seed="s:1", branch="quick", emotion=pf)})


def cases() -> dict[str, TurnContext]:
    one = ctx([mv(1, "user", "Morning.", name="user"), mv(2, "character", "Morning, Kai.", "chr_a", "Amara Okafor"),
               mv(3, "user", "My dog died this morning.", name="user")], mode="one_on_one", others=False,
              summary="**Kai — facts**\n- Has a dog called Pepper.")
    group = ctx([mv(1, "user", "Morning all", name="user"),
                 mv(2, "character", "Hi!\nLong day ahead.", "chr_h", "Hana Morisaki")], mode="group")
    greet = ctx([], mode="one_on_one", others=False, line=LineHint(kind="greeting"))
    return {"one_on_one": one, "group": group, "greeting": greet}


MOOD_ON = {"persona.moodLine": True}   # D40: the line is behind a switch, off by default


def dump(c: TurnContext, switches: dict[str, bool] | None = None) -> dict[str, Any]:
    req, prefix = engine(switches).request(c)
    return {"messages": req.messages, "stop": req.stop, "max_tokens": req.max_tokens, "prefix_len": len(prefix)}


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIX / f"request_agent1_{name}.json").read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("name", ["one_on_one", "group", "greeting"])
def test_unplanned_requests_equal_the_agent1_fixture(name: str) -> None:
    got = dump(cases()[name])
    if RECORD:
        (FIX / f"request_agent1_{name}.json").write_text(json.dumps(got, indent=2, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
    assert got == fixture(name)


# ── 4.3: agent-2 ──
MOOD_HAPPY = "Your mood right now: in a good mood. Let it show in how you word this reply; don't name the feeling."


@pytest.mark.parametrize("name", ["one_on_one", "group", "greeting"])
@pytest.mark.parametrize("manual", [False, True])
def test_neutral_and_manual_planned_requests_equal_the_agent1_fixture(name: str, manual: bool) -> None:
    """"Prefix unchanged": a neutral or a MANUAL turn sends `agent-1`'s request byte for byte, so M8's stored answers
    still serve."""
    assert dump(planned(cases()[name], "neutral", manual=manual)) == fixture(name)
    assert dump(planned(cases()[name], "happy", manual=True)) == fixture(name)


@pytest.mark.parametrize("name", ["one_on_one", "group", "greeting"])
def test_with_the_line_off_a_planned_happy_turn_sends_agent1(name: str) -> None:
    """D40: the default sends `agent-1`'s bytes on every turn, whatever the planned face."""
    assert dump(planned(cases()[name], "happy")) == fixture(name)


@pytest.mark.parametrize("name", ["one_on_one", "group", "greeting"])
def test_happy_differs_only_in_the_tail(name: str) -> None:
    old, new = fixture(name), dump(planned(cases()[name], "happy"), MOOD_ON)
    assert {k: v for k, v in new.items() if k != "messages"} == {k: v for k, v in old.items() if k != "messages"}
    n = len(old["messages"])
    had_tail = old["messages"][-1]["role"] == "system" and n > old["prefix_len"]
    keep = n - 1 if had_tail else n
    assert new["messages"][:keep] == old["messages"][:keep]
    tail = new["messages"][-1]
    assert tail["role"] == "system" and len(new["messages"]) == keep + 1
    old_tail = old["messages"][-1]["content"] if had_tail else None
    assert tail["content"] == (f"{MOOD_HAPPY}\n{old_tail}" if old_tail else MOOD_HAPPY)


def test_mood_line_sits_before_the_repeat_hint_voice_reminder_and_cue() -> None:
    """"Mood line before the cue": D16's order, block → mood → repeat hint → voice reminder → cue → language cue."""
    from tests.sessions.test_agent_turn import mv as m
    recent = [m(1, "user", "Morning all", name="user"),
              m(2, "character", "Well, honestly that depends.", "chr_a", "Amara Okafor"),
              m(3, "character", "Hi!", "chr_h", "Hana Morisaki")]
    c = planned(ctx(recent, mode="group"), "happy")
    c = c.model_copy(update={"speaker": c.speaker.model_copy(update={
        "profile": {**c.speaker.profile, "speakingStyle": {"summary": "Clipped and dry. Never gushes."}}})})
    req, _ = engine({"persona.repeatHint": True, "context.voiceReminder": True, **MOOD_ON}).request(c)
    lines = str(req.messages[-1]["content"]).split("\n")
    assert lines[0] == MOOD_HAPPY
    assert lines[1].startswith("Your last replies began:") and lines[2].startswith("Stay Amara:")
    assert lines.index(MOOD_HAPPY) < len(lines) - 1   # the cue comes after it


def test_no_mood_line_without_a_plan_or_under_manual() -> None:
    base = cases()["group"]
    for c in (base, planned(base, "sad", manual=True), planned(base, "neutral")):
        assert "Your mood right now" not in json.dumps(dump(c, MOOD_ON), ensure_ascii=False)
    assert "Your mood right now: a bit low." in json.dumps(dump(planned(base, "sad"), MOOD_ON), ensure_ascii=False)
