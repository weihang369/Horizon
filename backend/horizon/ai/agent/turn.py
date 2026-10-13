"""The `agent` reply engine (docs/ai/04 P1–P9, docs/ai/05 X3–X8; persona-context design D1, D2, D4, D6, D7, D16;
ai-ports "Agent reply engine").

It is the naive engine's stream loop with three seams overridden (D2): the held face, the empty-reply retry, the
citation map and the warm-prefix estimate are shared. What differs:
- **the request (D6):** system message 1 from the `agent` compiler; the rolling summary under doc 11 S6's heading
  (leading `#`s stripped from its lines); the history with the speaker's own lines as `assistant` and every other
  line as `Name: line`, same-role messages merged (X4), each message clipped at 4,000 tokens (X8); then ONE tail message
  (the retrieval block, M9's mood line, the repeat hint and voice reminder when switched on, the cue);
- **the parser:** stray tags and a `<name>:` at every line start are stripped (P6), and a tag never sets the face (P7):
  until M9's turn plan, the previous face stays, source `default` (D4);
- **the trace:** doc 05 X7's context mapping, the per-mode planned input as the budget, and no `cacheHitPct` (X6).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from horizon.ai.agent.budget import planned_input
from horizon.ai.agent.persona import (
    PROMPT_VERSION,
    PROMPT_VERSION_CUE,
    PROMPT_VERSION_CUE_MOOD,
    PROMPT_VERSION_MOOD,
    compile_persona,
    first_name,
    mood_line,
    persona_input,
    turn_cue_sentence,
)
from horizon.ai.contexts import MessageView, TurnContext
from horizon.ai.language import language_cue
from horizon.ai.llm import llm_request
from horizon.ai.naive.prompt import SUMMARY_HEADING, TRAILING_CUE, RetrievalBlock, turn_cue
from horizon.ai.naive.tag_parser import ParsedEmotion, TagParser
from horizon.ai.naive.turn import NaiveTurnEngine
from horizon.domain.pricing import count_tokens
from horizon.gateway.chat import ChatRequest

MESSAGE_MAX = 4000          # X8
MESSAGE_HEAD = 3000
MESSAGE_TAIL = 1000
CLIP_MARK = "[…]"
_HEADING = re.compile(r"^[ \t]*#+[ \t]*")


class AgentTagParser(TagParser):
    """P7 on the agent path: a tag is stripped like any stray tag but never chooses the face. The face is the plan's
    (M9, turn-plan-emotion D14) or, on an unplanned turn, the previous one with source `default` (M8 D4)."""

    def __init__(self, previous: str = "neutral", speaker: str | Sequence[str] | None = None, *,
                 per_line: bool = False, planned: tuple[str, str] | None = None) -> None:
        super().__init__(previous, speaker, per_line=per_line)
        self.planned = planned

    def _decide(self, emotion: str | None) -> list[Any]:
        self.decided = True
        if self.planned is not None:
            return [ParsedEmotion(*self.planned)]
        return [ParsedEmotion(self.previous, "default")]


def clip(text: str, limit: int = MESSAGE_MAX) -> str:
    """X8: a message over `limit` tokens shows as its first 3,000 and last 1,000 with `[…]` between (by bytes / 3)."""
    if count_tokens(text) <= limit:
        return text
    data = text.encode("utf-8")
    head = data[:MESSAGE_HEAD * 3].decode("utf-8", errors="ignore")
    tail = data[-MESSAGE_TAIL * 3:].decode("utf-8", errors="ignore")
    return f"{head}\n{CLIP_MARK}\n{tail}"


def summary_text(summary: str) -> str:
    """S6 plus D6: the summary as a record. A line can't open a fake `#` heading."""
    return "\n".join(_HEADING.sub("", line) for line in summary.split("\n"))


def render_merged(window: Sequence[MessageView], speaker_id: str, you: str) -> list[dict[str, Any]]:
    """X4: own lines `assistant` (no name), everyone else's `user` with EVERY line prefixed by the speaker's name,
    system notes and narration as `[kind] line`; consecutive same-role messages merged with a newline."""
    out: list[dict[str, Any]] = []
    for m in window:
        if not m.content:
            continue
        text = clip(m.content)
        if m.author_type == "character" and m.character_id == speaker_id:
            role, body = "assistant", text
        else:
            prefix = (f"{you}: " if m.author_type == "user" else f"{m.name}: " if m.author_type == "character"
                      else f"[{m.kind.replace('_', ' ')}] ")
            role, body = "user", "\n".join(prefix + line for line in text.split("\n"))
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + body
        else:
            out.append({"role": role, "content": body})
    return out


def stop_sequences(ctx: TurnContext, you: str, history: list[dict[str, Any]]) -> list[str]:
    """docs/ai/03 C6 for the merged history: `\\n<Name>:` for everyone but the speaker, and `\\n[<kind>]` for every
    line kind that appears (never a bare `\\n[`), deduplicated, at most 16."""
    out = [f"\n{p.name}:" for p in ctx.session.participants if p.character_id != ctx.speaker.id and p.name]
    out.append(f"\n{you}:")
    for m in history:
        if m["role"] != "user":
            continue
        for line in str(m["content"]).split("\n"):
            if line.startswith("[") and "] " in line:
                out.append(f"\n{line[:line.index(']') + 1]}")
    return list(dict.fromkeys(s for s in out if s.strip() and s != "\n["))[:16]


class AgentTurnEngine(NaiveTurnEngine):
    name = "agent"
    version = "2"   # M9: the face comes from the plan (turn-plan-emotion D14)

    @property
    def prompt_version(self) -> str:  # type: ignore[override]   # dynamic: it follows the live switch (D40)
        """`agent-1`, or `agent-2` while the mood line is switched on (D16, D40): the label follows the bytes sent."""
        return PROMPT_VERSION_MOOD if self.deps.switch("persona.moodLine") else PROMPT_VERSION

    def prompt_version_for(self, ctx: TurnContext | None) -> str:
        """M10 (group-watch D10): the label of the bytes this turn sent. A G3 sentence in the cue makes it `agent-3`
        (`agent-4` with the mood line on); every other request keeps M9's `agent-1` / `agent-2`."""
        mood = self.deps.switch("persona.moodLine")
        if ctx is not None and self.sentence(ctx) is not None:
            return PROMPT_VERSION_CUE_MOOD if mood else PROMPT_VERSION_CUE
        return PROMPT_VERSION_MOOD if mood else PROMPT_VERSION

    # ── seam 1: the request ──
    @staticmethod
    def sentence(ctx: TurnContext) -> str | None:
        """G3's sentence for this turn (a follow-plan second reply, a group Next speaker, a steered scene), if any."""
        plan = ctx.plan
        return turn_cue_sentence(plan.cue, plan.answered) if plan is not None else None

    def cue(self, ctx: TurnContext) -> str | None:
        """D7: naive's cues, except a generated greeting, which avoids the stored one (P9). M10 (D10): then G3's
        sentence on its own line, after the scene cue and any director's note; still the tail, never the prefix."""
        if ctx.line.kind == "greeting":
            stored = str(ctx.speaker.profile.get("greeting") or "").strip()
            base = "Open the conversation with a short, warm greeting in character."
            return f"{base} Don't reuse your usual greeting: '{stored}'." if stored else base
        lines = [x for x in (turn_cue(ctx), self.sentence(ctx)) if x]
        return "\n".join(lines) if lines else None

    def mood(self, ctx: TurnContext) -> str | None:
        """E4's mood line for the planned face; none without a plan, for neutral or in MANUAL (D16). Off unless the
        `persona.moodLine` switch is on: M9's on/off run found no gain and more replies naming the feeling (D40)."""
        if not self.deps.switch("persona.moodLine"):
            return None
        face = ctx.plan.emotion if ctx.plan is not None else None
        return mood_line(face.face, face.manual) if face is not None else None

    def tail_extras(self, ctx: TurnContext) -> list[str]:
        """P8's repeat hint and X5's voice reminder, each only when its runtime switch is on (both off by default)."""
        out: list[str] = []
        if self.deps.switch("persona.repeatHint"):
            mine = [m.content for m in ctx.session.recent
                    if m.author_type == "character" and m.character_id == ctx.speaker.id and m.content][-3:]
            if mine:
                openers = ", ".join(f"'{' '.join(x.split()[:3])}…'" for x in mine)
                out.append(f"Your last replies began: {openers}. Start differently.")
        if self.deps.switch("context.voiceReminder"):
            style = str((ctx.speaker.profile.get("speakingStyle") or {}).get("summary") or "").strip()
            first = re.split(r"(?<=[.!?])\s", style, maxsplit=1)[0] if style else ""
            if first:
                out.append(f"Stay {first_name(ctx.speaker.name)}: {first}")
        return out

    def request(self, ctx: TurnContext, block: RetrievalBlock | None = None, *,
                force_cue: bool = False) -> tuple[ChatRequest, list[dict[str, Any]]]:
        s = ctx.session
        persona = compile_persona(persona_input(ctx))
        prefix: list[dict[str, Any]] = [{"role": "system", "content": persona.text}]
        if s.summary:
            prefix.append({"role": "system", "content": f"{SUMMARY_HEADING}\n{summary_text(s.summary)}"})
        you = str((s.world.you or {}).get("displayName") or "User")
        history = render_merged(s.recent, ctx.speaker.id, you)
        tail: list[str] = []
        if block is not None and block.content:
            tail.append(block.content)
        mood = self.mood(ctx)   # M9 D16: after the retrieval block, before the repeat hint (doc 04 P2, doc 06 E4)
        if mood:
            tail.append(mood)
        tail += self.tail_extras(ctx)
        cue = self.cue(ctx)
        if cue:
            tail.append(cue)
        elif force_cue or (history and history[-1]["role"] == "assistant"):
            tail.append(TRAILING_CUE)   # group A A2: a history that ends on the speaker's own line needs a cue
        lang = language_cue(ctx)   # D35: a clearly non-English user line; the tail's last line
        if lang:
            tail.append(lang)
        messages = [*prefix, *history]
        if tail:
            messages.append({"role": "system", "content": "\n".join(tail)})
        req = llm_request(self._row(ctx), self.deps.prices.chat.model, messages, max_tokens=ctx.max_tokens,
                          stop=stop_sequences(ctx, you, history))
        return req, prefix

    # ── seam 2: the parser ──
    def parser(self, ctx: TurnContext, previous: str, names: list[str]) -> TagParser:
        face = ctx.plan.emotion if ctx.plan is not None else None
        return AgentTagParser(previous, planned=(face.face, face.source) if face is not None else None, speaker=names,
                              per_line=True)

    # ── seam 3: the trace (X7) ──
    def trace_patch(self, ctx: TurnContext, req: ChatRequest, prefix: list[dict[str, Any]], block: RetrievalBlock | None,
                    said: str, chosen: ParsedEmotion | None, *, warm: bool) -> dict[str, Any]:
        persona = compile_persona(persona_input(ctx))
        t = persona.tokens
        summary = count_tokens(prefix[1]["content"]) if len(prefix) > 1 else 0
        has_tail = req.messages[-1]["role"] == "system" and len(req.messages) > len(prefix)
        tail = str(req.messages[-1]["content"]) if has_tail else ""
        history_msgs = req.messages[len(prefix):len(req.messages) - (1 if has_tail else 0)]
        history = sum(count_tokens(str(m["content"])) for m in history_msgs)
        latest = next((clip(m.content) for m in reversed(ctx.session.recent) if m.author_type == "user"), "")
        user = count_tokens(latest) if latest else 0
        block_tokens = count_tokens(block.content) if block is not None and block.content else 0
        memory = count_tokens(block.memory_text) if block is not None and block.memory_text else 0
        mode_tail = max(0, count_tokens(tail) - block_tokens) if tail else 0
        patch: dict[str, Any] = {"context": {
            "budget": planned_input(ctx.session.mode, self.deps.windows()),
            "used": {"persona": t["card"], "system": t["world"] + t["rules"], "mode": t["session"] + mode_tail,
                     "history": summary + max(0, history - user), "user": user, "memory": memory,
                     "knowledge": max(0, block_tokens - memory)}}}
        if chosen is not None:
            patch["emotion"] = {"chosen": chosen.emotion, "source": chosen.source}
            face = ctx.plan.emotion if ctx.plan is not None else None
            if face is not None and face.candidates:   # E2: the top 3 by Jev's p (none when Jev failed)
                patch["emotion"]["candidates"] = [dict(c) for c in face.candidates]
        if block is not None:
            knowledge = block.knowledge_trace(ctx.query, said)
            if knowledge is not None:
                patch["knowledge"] = knowledge
            mem = block.memory_trace()
            if mem is not None:
                patch["memory"] = mem
        return patch
