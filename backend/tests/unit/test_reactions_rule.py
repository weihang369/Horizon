"""E5's keep rule and E3's fades for listener reactions, in code (docs/ai/06 E3, E5; turn-plan-emotion D18;
listener-reactions "Which reactions show", "Listener faces fade")."""

from __future__ import annotations

import json

from horizon.ai.agent.reactions import delay_ms, keep, state
from horizon.ai.contexts import ListenerView, ReactionRequest, SessionContext, WorldView
from horizon.ai.decider import ChoiceAnswer

FADE = frozenset({"surprised", "embarrassed"})
WINDOW = (300.0, 800.0)


def lv(cid: str, face: str = "neutral", *, eligible: bool = True, side: str | None = None) -> ListenerView:
    return ListenerView(id=cid, name=cid.title(), about_source="A retired ferry captain. Loves maps.", face=face,
                        side_label=side, eligible=eligible)


def ans(choice: str, conf: float, **probs: float) -> ChoiceAnswer:
    return ChoiceAnswer(choice, confidence=conf, probabilities=probs or {choice: conf})


def run(answers: dict[str, ChoiceAnswer | None], listeners: list[ListenerView], floor: float = 0.6) -> list[tuple]:
    out = keep(answers, listeners, floor=floor, fade=FADE, seed="s:3", window=WINDOW)
    return [(r.character_id, r.emotion, r.p, r.source) for r in out]


def test_cap_of_two_keeps_the_most_confident() -> None:
    got = run({"a": ans("happy", 0.9), "b": ans("sad", 0.8), "c": ans("angry", 0.7)}, [lv("a"), lv("b"), lv("c")])
    assert got == [("a", "happy", 0.9, "classifier"), ("b", "sad", 0.8, "classifier")]


def test_same_face_none_and_unsure_show_nothing() -> None:
    got = run({"a": ans("happy", 0.9), "b": ans("none", 0.9), "c": ans("sad", 0.5)},
              [lv("a", "happy"), lv("b", "angry"), lv("c", "thinking")])
    assert got == []


def test_on_a_neutral_face_neutral_and_none_merge() -> None:
    """D12 per listener: neutral .35 + none .3 beats happy .35 (and happy is under the floor anyway at 0 floor)."""
    got = run({"a": ans("happy", 0.35, happy=0.35, neutral=0.35, none=0.3)}, [lv("a")], floor=0.0)
    assert got == []


def test_short_faces_fade_outside_the_cap_jev_or_not() -> None:
    listeners = [lv("a"), lv("b"), lv("m", "surprised", eligible=False), lv("e", "embarrassed"), lv("t", "thinking")]
    got = run({"a": ans("happy", 0.9), "b": ans("sad", 0.8), "e": ans("none", 0.9), "t": None}, listeners)
    assert got == [("a", "happy", 0.9, "classifier"), ("b", "sad", 0.8, "classifier"),
                   ("m", "neutral", None, "default"), ("e", "neutral", None, "default")]


def test_a_failed_call_still_fades_and_a_confirmed_short_face_stays() -> None:
    assert run({}, [lv("s", "surprised"), lv("h", "happy")]) == [("s", "neutral", None, "default")]
    assert run({"s": ans("surprised", 0.9)}, [lv("s", "surprised")]) == []
    assert run({"s": ChoiceAnswer("none", source="fallback")}, [lv("s", "surprised")]) == [("s", "neutral", None,
                                                                                               "default")]


def test_delays_are_seeded_per_listener_and_in_the_window() -> None:
    a, b = delay_ms("s:3", "a", WINDOW), delay_ms("s:3", "b", WINDOW)
    assert a == delay_ms("s:3", "a", WINDOW) and a != b and all(300 <= x <= 800 for x in (a, b))


def test_the_state_quotes_the_line_names_the_listeners_and_skips_the_ineligible() -> None:
    s = SessionContext(session_id="ses_1", world=WorldView(id="w", name="W"), mode="debate", title="t", participants=[],
                       recent=[])
    req = ReactionRequest(session=s, message_id="m1", speaker_id="chr_h", speaker_name="Hana", line="Maps lie.",
                          before="Kai: Do maps lie?", seed="s:3",
                          listeners=[lv("a", side="the other side"), lv("m", eligible=False)])
    st = state(req)
    assert st["mode"] == "debate" and st["quoted_line"] == "Hana: Maps lie." and st["quoted_before"] == "Kai: Do maps lie?"
    assert st["quoted_listeners"] == [{"name": "A", "about": "A retired ferry captain.", "side": "the other side"}]
    assert "face" not in json.dumps(st)   # D37: Jev anchored on the face it was shown
