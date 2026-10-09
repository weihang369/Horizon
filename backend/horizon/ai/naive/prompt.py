"""The scripted PromptCompiler (doc 05 §5, NFR-35; design D11): the static persona and system prompt.

Prompt order: this system message (persona fields, the world, the You card, the content-rating clause and the emotion
tag rule), then the rolling session summary, then the history window. Everything here is stable for a speaker in a
session, so the provider's prompt cache keeps hitting between turns.

v2 (knowledge-memory-storage design D15, D-93): when the runtime retrieved passages or memories for the turn, one
system message goes **after** the history (dynamic content last, NFR-35): the passages numbered `[n]` with their
section text (<= 1 200 chars, one per section), up to three memories, and the cite-only-when-used line. With nothing
retrieved the request is byte-identical to v1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from horizon.ai.contexts import KnowledgeHit, MemoryHit, TurnContext
from horizon.ai.naive.tag_parser import EMOTIONS

PROMPT_VERSION = "naive-2"
SECTION_MAX = 1200
QUOTE_MAX = 400
MEMORY_MAX = 3
CITE_LINE = "Cite a passage with its [n] only when you rely on it; otherwise don't mention the passages."
_MARKER = re.compile(r"\[(\d{1,2})\](?!\()")


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


@dataclass
class RetrievalBlock:
    """The v2 block for one turn: its system message, the numbered passages (n -> the hits of that section) and the
    memories it was given."""

    content: str
    passages: dict[int, list[KnowledgeHit]] = field(default_factory=dict)
    memories: list[MemoryHit] = field(default_factory=list)
    knowledge_text: str = ""
    memory_text: str = ""

    def citations(self) -> list[dict[str, Any]]:
        """A citation for every numbered passage (the runtime keeps only the markers the reply wrote)."""
        out: list[dict[str, Any]] = []
        for n, hits in self.passages.items():
            h = hits[0]
            out.append({"n": n, "sourceId": h.source_id, "title": h.title, "type": h.type, "chunkId": h.chunk_id,
                        **({"locator": h.locator} if h.locator else {}),
                        "quote": h.text if len(h.text) <= QUOTE_MAX else h.text[:QUOTE_MAX - 1] + "\u2026",
                        "score": round(h.score, 4)})
        return out

    def knowledge_trace(self, query: str | None, reply: str) -> dict[str, Any] | None:
        if not self.passages:
            return None
        used = {int(m) for m in _MARKER.findall(reply)}
        retrieved = [{"chunkId": h.chunk_id, "sourceId": h.source_id, "title": h.title,
                      **({"locator": h.locator} if h.locator else {}), "text": h.text, "score": round(h.score, 4),
                      "cited": n in used and i == 0, "n": n}
                     for n, hits in self.passages.items() for i, h in enumerate(hits)]
        return {**({"query": query[:120]} if query else {}), "trigger": "always", "retrieved": retrieved}

    def memory_trace(self) -> dict[str, Any] | None:
        if not self.memories:
            return None
        return {"recalled": [{"memoryItemId": m.id, "text": m.text,
                              **({"sourceSessionId": m.source_session_id} if m.source_session_id else {}),
                              **({"score": round(m.score, 4)} if m.score is not None else {})} for m in self.memories]}


def retrieval_block(ctx: TurnContext) -> RetrievalBlock | None:
    if not ctx.knowledge and not ctx.memory:
        return None
    block = RetrievalBlock(content="")
    sections: dict[str, int] = {}
    parts: list[str] = []
    for h in ctx.knowledge:
        n = sections.get(h.section_text)
        if n is None:
            n = sections[h.section_text] = len(sections) + 1
            block.passages[n] = []
            text = h.section_text if len(h.section_text) <= SECTION_MAX else h.section_text[:SECTION_MAX - 1] + "\u2026"
            where = f", {h.locator}" if h.locator else ""
            parts.append(f"[{n}] {h.title}{where}: {text}")
        block.passages[n].append(h)
    lines: list[str] = []
    if parts:
        block.knowledge_text = "\n".join(parts)
        lines += ["Passages you can use (from your own documents):", block.knowledge_text]
    block.memories = list(ctx.memory[:MEMORY_MAX])
    if block.memories:
        block.memory_text = "\n".join(f"- {m.text}" for m in block.memories)
        lines += ["Things you remember about this world:", block.memory_text]
    if parts:
        lines.append(CITE_LINE)
    block.content = "\n".join(lines)
    return block
