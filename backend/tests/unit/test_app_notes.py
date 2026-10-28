"""Notes about the app (its controls, a failed step) stay out of every prompt and summary; story notes stay in (the
v1.1 runtime hunt and the user's choice, 28 Oct)."""

from __future__ import annotations

from horizon.ai.naive.verdict import NOTE_PROSE, NOTE_SCORES
from horizon.sessions.context import app_note
from horizon.sessions.modes.debate import SIDE_NAME
from horizon.sessions.modes.watch import RECAP_FAILED


def sys_note(text: str) -> dict[str, object]:
    return {"author": {"type": "system"}, "content": text}


def test_every_app_note_the_backend_writes_is_kept_out() -> None:
    texts = [RECAP_FAILED, NOTE_PROSE, NOTE_SCORES, "Takeshi is muted.",
             "Everyone's asleep. Top someone up to continue the scene.",
             "Everyone on the panel is asleep. Top someone up to continue the debate.",
             "Everyone on the panel has left. End the debate to finish.",
             *(f"The {SIDE_NAME[s]} is asleep. Top someone up to continue the debate." for s in ("prop", "opp")),
             *(f"The {SIDE_NAME[s]} has no one left. End the debate to finish." for s in ("prop", "opp"))]
    assert all(app_note(sys_note(t)) for t in texts)


def test_story_notes_and_people_stay_in() -> None:
    for t in ("Hana is asleep (⚡ 0).", "Hana is asleep, skipping.", "Victor has left.", "ROUND 1 · VERDICT",
              "Rainy afternoon.", "STRONGER CASE: PROPOSITION"):
        assert not app_note(sys_note(t)), t
    assert not app_note({"author": {"type": "user"}, "content": "Try Summarise again."})
