"""The scripted PromptCompiler (doc 05 §5, NFR-35; design D11): the static persona and system prompt.

Prompt order: this system message (persona fields, the world, the You card, the content-rating clause and the emotion
tag rule), then the rolling session summary, then the history window. Everything here is stable for a speaker in a
session, so the provider's prompt cache keeps hitting between turns.
"""

from __future__ import annotations

from typing import Any

from horizon.ai.contexts import TurnContext
from horizon.ai.naive.tag_parser import EMOTIONS

PROMPT_VERSION = "naive-1"


def _list(xs: Any) -> str:
    return ", ".join(str(x) for x in xs) if isinstance(xs, list) and xs else ""


def system_prompt(ctx: TurnContext) -> str:
    p: dict[str, Any] = ctx.speaker.profile
    s = ctx.session
    style = p.get("speakingStyle") or {}
    persona = p.get("personality") or {}
    lines = [f"You are {p.get('title', '') + ' ' if p.get('title') else ''}{p.get('name', ctx.speaker.name)}, "
             f"{p.get('role', 'a character')}, in a story world called {s.world.name}."]
    for label, value in (
        ("Age", p.get("age")), ("Pronouns", p.get("pronouns")), ("Tagline", p.get("tagline")),
        ("Personality", persona.get("summary")), ("Traits", _list(persona.get("traits"))),
        ("Backstory", p.get("backstory")), ("Speaking style", style.get("summary")), ("Tone", style.get("tone")),
        ("Formality", style.get("formality")), ("Quirks", _list(style.get("quirks"))),
        ("Catchphrases", _list(style.get("catchphrases"))), ("Expertise", _list(p.get("expertise"))),
        ("Goals", p.get("goals")), ("Boundaries", _list(p.get("boundaries"))),
        ("Example lines", _list(p.get("exampleLines"))),
    ):
        if value:
            lines.append(f"{label}: {value}")
    you = s.world.you or {}
    if you.get("displayName"):
        lines.append(f"The user is {you['displayName']}." + (f" About them: {you['about']}" if you.get("about") else ""))
    others = [x.name for x in s.participants if x.character_id != ctx.speaker.id]
    if s.mode == "group" and others:
        lines.append(f"This is a group chat with {', '.join(others)} and the user. Speak only as yourself.")
    elif s.mode == "debate":
        cfg = s.config or {}
        lines.append(f"This is a moderated debate on the motion: \"{cfg.get('motion', '')}\". Opponents: {', '.join(others)}.")
    elif s.mode == "watch":
        cfg = s.config or {}
        lines.append(f"This is a scene the user watches. Premise: {cfg.get('premise', '')}. Others: {', '.join(others)}.")
    if s.content_rating == "adult":
        lines.append("Mature themes are allowed between consenting adults; stay within the platform's rules.")
    else:
        lines.append("Keep everything safe for work.")
    lines.append(f"Begin every reply with exactly one emotion tag <e:LABEL>, where LABEL is one of: {', '.join(EMOTIONS)}. "
                 "Never write tags anywhere else. Then reply in character, briefly, in plain text.")
    return "\n".join(lines)


def turn_cue(ctx: TurnContext) -> str | None:
    """A per-turn instruction after the history, only when the turn isn't a plain reply to the last message."""
    kind = ctx.line.kind
    if kind == "greeting":
        return "Open the conversation with a short, warm greeting in character."
    if kind == "debate" and ctx.debate is not None:
        d = ctx.debate
        side = {"prop": "the proposition", "opp": "the opposition"}.get(d.side or "", "your own view")
        return f"Give your {d.phase} statement for {side}, round {d.round}. Stay under a few sentences."
    if kind == "answer":
        return f"Answer the moderator's question directly: {ctx.prompt}"
    if kind == "scene":
        return f"Continue the scene in character.{f' Director: {ctx.direction_note}' if ctx.direction_note else ''}"
    if ctx.variant_id:
        return "Answer the last message again, differently."
    return None
