"""`naive`'s debate line names teammates apart from opponents (doc 08 finding 2; debate design D10; task 2.9; ai-ports
"The naive debate prompt names teammates"), and only debate requests change their label."""

from __future__ import annotations

from horizon.ai.contexts import CharacterView, LineHint, ParticipantView, SessionContext, TurnContext, WorldView
from horizon.ai.naive.prompt import PROMPT_VERSION, PROMPT_VERSION_DEBATE, debate_line, system_prompt
from horizon.ai.naive.turn import NaiveTurnEngine

AMARA, RIN, VICTOR = "chr_a", "chr_r", "chr_v"


def ctx(mode: str = "debate", sides: dict[str, str | None] | None = None, speaker: str = AMARA) -> TurnContext:
    sides = sides if sides is not None else {AMARA: "prop", RIN: "prop", VICTOR: "opp"}
    names = {AMARA: "Amara Okafor", RIN: "Rin Sato", VICTOR: "Victor Hale"}
    s = SessionContext(session_id="ses_d", world=WorldView(id="w", name="Meridian"), mode=mode, title="t",
                       config={"motion": "This house would tax sugary drinks"}, recent=[],
                       participants=[ParticipantView(character_id=c, name=names[c], role="debater", side=side,
                                                     energy={"current": 500}) for c, side in sides.items()])
    return TurnContext(session=s, speaker=CharacterView(id=speaker, name=names[speaker], profile={"name": names[speaker]}),
                       message_id="m", prompt="", line=LineHint(kind="debate"), turn_index=1, max_tokens=320)


def test_a_teammate_is_not_an_opponent() -> None:
    line = debate_line(ctx())
    assert line == ('This is a moderated debate on the motion: "This house would tax sugary drinks". You argue for it, '
                    "with Rin Sato. Opponents: Victor Hale.")
    assert debate_line(ctx(speaker=VICTOR)).endswith("You argue against it. Opponents: Amara Okafor, Rin Sato.")
    assert line in system_prompt(ctx())


def test_a_panel_lists_fellow_panellists() -> None:
    line = debate_line(ctx(sides={AMARA: None, RIN: None, VICTOR: None}))
    assert line == 'This is a moderated panel debate on: "This house would tax sugary drinks". Also on the panel: Rin Sato, Victor Hale.'


def test_only_debate_requests_change_their_label() -> None:
    eng = NaiveTurnEngine.__new__(NaiveTurnEngine)
    assert eng.prompt_version_for(ctx()) == PROMPT_VERSION_DEBATE == "naive-6"
    assert eng.prompt_version_for(ctx(mode="group")) == PROMPT_VERSION == "naive-5"
    assert eng.prompt_version_for(None) == "naive-5"
