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

from horizon.ai.contexts import DebateMeta, LineHint, MessageView, PlannedFace, TurnContext, TurnPlan
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
    # M10 (group-watch task 7.1): a watch scene turn under a director's note, recorded before the cue sentence existed
    scene = ctx([mv(1, "character", "The power's out on the whole street.", "chr_h", "Hana Morisaki"),
                 mv(2, "user", "Rin is hiding something", name="user")], mode="watch",
                summary="**The inn**\n- A storm has closed the road.", line=LineHint(kind="scene"))
    scene = scene.model_copy(update={"direction_note": "Rin is hiding something"})
    return {"one_on_one": one, "group": group, "greeting": greet, "scene": scene, "debate": debate_case()}


def debate_case(phase: str = "rebuttal", round_: int = 2, iteration: int = 1,
                recent: list[MessageView] | None = None) -> TurnContext:
    """M11 (debate task 5.1): Amara's rebuttal for the Proposition against Hana, recorded from the `agent-1` engine
    before the debate cue existed (naive's cue then)."""
    c = ctx(recent if recent is not None else [
        mv(1, "system", "ROUND 1 · OPENING", kind="system_note"),
        mv(2, "character", "Homework steals the evening from children.", "chr_a", "Amara Okafor"),
        mv(3, "character", "Homework teaches discipline that school alone can't.", "chr_h", "Hana Morisaki"),
        mv(4, "system", "ROUND 2 · REBUTTAL", kind="system_note")], mode="debate")
    s = c.session
    parts = [p.model_copy(update={"side": "prop" if p.character_id == "chr_a" else "opp"}) for p in s.participants]
    s = s.model_copy(update={"participants": parts, "config": {
        "motion": "This house would ban homework", "format": "two_sided", "turnLength": "short",
        "sides": {"prop": ["chr_a"], "opp": ["chr_h"]}}})
    return c.model_copy(update={"session": s, "line": LineHint(kind="debate"), "debate": DebateMeta(
        phase=phase, round=round_, iteration=iteration, side="prop", motion="This house would ban homework")})


MOOD_ON = {"persona.moodLine": True}   # D40: the line is behind a switch, off by default


def dump(c: TurnContext, switches: dict[str, bool] | None = None) -> dict[str, Any]:
    req, prefix = engine(switches).request(c)
    return {"messages": req.messages, "stop": req.stop, "max_tokens": req.max_tokens, "prefix_len": len(prefix)}


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIX / f"request_agent1_{name}.json").read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("name", ["one_on_one", "group", "greeting", "scene"])   # debate: its cue differs (5.7)
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


# ── M10 (group-watch tasks 7.2, 7.3; design D10): G3's sentence and the labels that follow the bytes ──
TURN_CUE = json.loads((FIX.parent / "turn_cue" / "cases.json").read_text(encoding="utf-8"))["cases"]
SECOND = "Hana has just answered. Don't repeat them; add your own angle, or answer Hana directly."
STEER = ("This thread has run its course. Bring in something new that fits the premise: an event, a discovery or a "
         "change of plan. Don't wrap up, say goodbye or wait for Kai to decide.")   # M11 (debate D10)


def cued(base: TurnContext, cue: str | None, answered: str | None = None, face: str = "neutral") -> TurnContext:
    c = planned(base, face)
    assert c.plan is not None
    return c.model_copy(update={"plan": c.plan.model_copy(update={"cue": cue, "answered": answered})})


@pytest.mark.parametrize("case", TURN_CUE, ids=lambda c: f"{c['cue']}-{c.get('user')}")
def test_the_shared_turn_cue_table(case: dict[str, Any]) -> None:
    from horizon.ai.agent.persona import turn_cue_sentence

    assert turn_cue_sentence(case["cue"], case["answered"], case.get("user")) == case["sentence"]


def test_a_first_reply_is_agent1_and_a_second_differs_only_in_the_cue_line() -> None:
    from tests.sessions.test_agent_turn import engine as make

    old = fixture("group")
    first = cued(cases()["group"], None)
    assert dump(first) == old and make().prompt_version_for(first) == "agent-1"
    second = cued(cases()["group"], "second", "Hana")
    new = dump(second)
    assert make().prompt_version_for(second) == "agent-3"
    assert {k: v for k, v in new.items() if k != "messages"} == {k: v for k, v in old.items() if k != "messages"}
    n = len(old["messages"])
    had_tail = old["messages"][-1]["role"] == "system" and n > old["prefix_len"]
    keep = n - 1 if had_tail else n
    assert new["messages"][:keep] == old["messages"][:keep]
    assert new["messages"][keep:] == [{"role": "system", "content": SECOND}]


@pytest.mark.parametrize(("mood", "sentence", "label"), [
    (False, False, "agent-1"), (True, False, "agent-2"), (False, True, "agent-3"), (True, True, "agent-4")])
def test_the_prefix_is_the_same_in_all_four_label_cases(mood: bool, sentence: bool, label: str) -> None:
    from tests.sessions.test_agent_turn import engine as make

    switches = MOOD_ON if mood else None
    base = ctx([mv(1, "user", "Morning all", name="user"), mv(2, "character", "Hi!", "chr_h", "Hana Morisaki")],
               mode="group", summary="**Kai**\n- Likes tea.")
    c = cued(base, "second" if sentence else None, "Hana", face="happy")
    req, prefix = make(switches).request(c)
    _, ref_prefix = make().request(cued(base, None))
    assert prefix == ref_prefix and len(prefix) == 2           # system message 1 and the summary message
    assert make(switches).prompt_version_for(c) == label
    assert (SECOND in str(req.messages[-1]["content"])) is sentence


def test_the_steer_sentence_follows_the_directors_note() -> None:
    old = fixture("scene")
    new = dump(cued(cases()["scene"], "steer"))
    assert new["messages"][:-1] == old["messages"][:-1]
    assert new["messages"][-1] == {"role": "system", "content": (
        "Continue the scene in character. Director: Rin is hiding something\n" + STEER)}


# ── M11 (debate tasks 5.1–5.7; design D10): the debate cue, the steer's labels, and the prefix proof ──
DEBATE_CUE = json.loads((FIX.parent / "debate_cue" / "cases.json").read_text(encoding="utf-8"))["cases"]
REBUTTAL = ("Give your rebuttal: name the strongest point the other side has made so far and answer it, then "
            "strengthen your own case.")


@pytest.mark.parametrize("case", DEBATE_CUE, ids=lambda c: f"{c['phase']}-{len(c['teammates'])}-{c['extended']}")
def test_the_shared_debate_cue_table(case: dict[str, Any]) -> None:
    from horizon.ai.agent.persona import debate_cue

    assert debate_cue(case["phase"], panel=case["panel"], extended=case["extended"], teammates=case["teammates"],
                      after_interject=case["afterInterject"]) == case["cue"]


def test_the_debate_fixture_loads_and_a_debate_argument_differs_only_in_the_cue_line() -> None:
    """5.1 / 5.7: the `agent-1` debate request (naive's cue) and the V4 request differ only in the tail's cue line."""
    from tests.sessions.test_agent_turn import engine as make

    old = fixture("debate")
    assert old["messages"][-1] == {"role": "system", "content": "Give your rebuttal statement for the proposition, round 2."}
    new = dump(debate_case())
    assert {k: v for k, v in new.items() if k != "messages"} == {k: v for k, v in old.items() if k != "messages"}
    assert new["messages"][:-1] == old["messages"][:-1]
    assert new["messages"][-1] == {"role": "system", "content": REBUTTAL}
    assert make().prompt_version_for(debate_case()) == "agent-7"
    assert make(MOOD_ON).prompt_version_for(debate_case()) == "agent-8"


def test_two_rounds_one_prefix() -> None:
    """V4 / P5: Amara's opening and rebuttal send a byte-identical system message 1."""
    opening = debate_case("opening", 1, recent=[mv(1, "system", "ROUND 1 · OPENING", kind="system_note")])
    a, _ = dump(opening), None
    b = dump(debate_case())
    assert a["messages"][0] == b["messages"][0]
    assert a["messages"][-1]["content"] == "Give your opening statement: your case in two or three reasons."


def test_a_rebuttal_after_a_teammate_and_an_extended_round_after_an_interject() -> None:
    from horizon.ai.contexts import ParticipantView

    c = debate_case()
    rin = ParticipantView(character_id="chr_r", name="Rin Takeda", role="speaker", side="prop",
                          energy={"current": 500, "max": 1000})
    c = c.model_copy(update={"session": c.session.model_copy(update={"participants": [*c.session.participants, rin]})})
    assert c.debate is not None
    after_mate = c.model_copy(update={"debate": c.debate.model_copy(update={"teammates_heard": ["chr_r"]})})
    assert dump(after_mate)["messages"][-1]["content"] == (
        REBUTTAL + "\nRin has already spoken for your side this round: add to it, don't repeat it.")
    extended = c.model_copy(update={"debate": c.debate.model_copy(update={"iteration": 2, "after_interject": True})})
    assert dump(extended)["messages"][-1]["content"] == (
        REBUTTAL + "\nThe round was extended: make a point not yet made.\nTake the moderator's last note into account.")


def test_an_ask_answer_keeps_naives_cue_and_agent1() -> None:
    from tests.sessions.test_agent_turn import engine as make

    ask = debate_case().model_copy(update={"line": LineHint(kind="answer"), "prompt": "Would you ban weekends too?"})
    assert dump(ask)["messages"][-1]["content"] == "Answer the moderator's question directly: Would you ban weekends too?"
    assert make().prompt_version_for(ask) == "agent-1"


@pytest.mark.parametrize(("mood", "label"), [(False, "agent-5"), (True, "agent-6")])
def test_the_reworded_steer_is_agent5_and_names_the_watcher(mood: bool, label: str) -> None:
    from tests.sessions.test_agent_turn import engine as make

    c = cued(cases()["scene"], "steer")
    assert make(MOOD_ON if mood else None).prompt_version_for(c) == label
    assert dump(c)["messages"][-1]["content"].endswith("Don't wrap up, say goodbye or wait for Kai to decide.")
    assert make().prompt_version_for(cued(cases()["group"], "next")) == "agent-3"
