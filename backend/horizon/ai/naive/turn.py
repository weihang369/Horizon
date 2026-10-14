"""The naive DeepSeek TurnEngine (doc 05 §5; ai-ports "Naive reply engine"; design D11).

One streamed call to the pinned chat model with its `runtime.llm.calls` row (`reply.chat`, or `reply.debate`):
reasoning off, the row's temperature, `max_tokens` from the runtime (chosen after the plan). The prompt is the
compiled persona (system), the rolling summary, then the history window (and a short cue for turns that aren't a
plain reply). The SHA-256 of the system + summary prefix is kept per (session, speaker): when it matches the last
call, the estimate prices that prefix as cached (`warm=True`). The `<e:label>` tag is parsed off the stream; a
mid-stream provider error propagates, and the runner keeps the partial text (`interrupted`, `interruptedBy: "error"`).

Prompt v2 (D-93): retrieved passages and memories go in one system message after the history. The engine yields a
`CitationMap` for every numbered passage and, after the stream, reports in the trace which passages its reply cited
(`[n]` in its own output) and which memories it was given.

`naive-3` (docs/ai/03 C4–C6, §5; ai-foundation design D15–D17):
- **Stop sequences** from the names the history writes (`\\n<Name>:` for every other participant and the user,
  `\\n[<kind>]` for other line kinds), and the parser drops a leading `<own name>:` on the first line.
- **A history that ends on the speaker's own line gets a trailing cue** (group A A2: 2 of 4 such replies were empty).
- **An empty reply is retried once before anything shows**: the emotion is held until the first visible text, so an
  empty first stream emits nothing; the retry adds the trailing cue if it was missing. A second empty reply is a
  retryable `provider_error`. Both calls keep their ledger rows.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any

from horizon.ai.agent.budget import planned_input
from horizon.ai.contexts import TurnContext
from horizon.ai.language import language_cue
from horizon.ai.llm import llm_request
from horizon.ai.naive.prompt import (
    PROMPT_VERSION,
    PROMPT_VERSION_DEBATE,
    SUMMARY_HEADING,
    TRAILING_CUE,
    RetrievalBlock,
    retrieval_block,
    system_prompt,
    turn_cue,
)
from horizon.ai.naive.tag_parser import ParsedEmotion, TagParser
from horizon.ai.naive.window import render_history
from horizon.ai.ports import CitationMap, Emotion, Token, TracePatch, TurnEvent
from horizon.ai.scripted.ports import AiDeps
from horizon.domain.pricing import count_tokens
from horizon.domain.runtime_config import LlmCall
from horizon.gateway.chat import ChatRequest
from horizon.gateway.errors import ProviderError

EMPTY_REPLY = "The model sent an empty reply."
FALLBACK_ROW = LlmCall(thinking="off", temperature=1.0, output="stream")   # only when no table is wired (unit tests)


def stop_sequences(ctx: TurnContext, you: str, messages: list[dict[str, Any]]) -> list[str]:
    """docs/ai/03 C6: the prefixes the history writes for everyone but the speaker. Never a bare "\\n[" (a line may
    start with a citation marker), deduplicated, at most 16 (a cast of 5 needs about 8)."""
    out = [f"\n{p.name}:" for p in ctx.session.participants if p.character_id != ctx.speaker.id and p.name]
    out.append(f"\n{you}:")
    for m in messages:
        c = m.get("content")
        if m.get("role") == "user" and isinstance(c, str) and c.startswith("[") and "] " in c:
            out.append(f"\n{c[:c.index(']') + 1]}")
    return list(dict.fromkeys(s for s in out if s.strip() and s != "\n["))[:16]


def own_names(ctx: TurnContext) -> list[str]:
    """The names the speaker could prefix a line with: the history's name for them, the profile name, the first name."""
    names = [p.name for p in ctx.session.participants if p.character_id == ctx.speaker.id]
    names += [ctx.speaker.name, ctx.speaker.first_name]
    return list(dict.fromkeys(n for n in names if n))


class NaiveTurnEngine:
    name = "naive"
    version = "3"
    prompt_version: str | None = PROMPT_VERSION

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps
        self._prefix: dict[tuple[str, str], str] = {}

    def prompt_version_for(self, ctx: TurnContext | None) -> str | None:
        """The label of the bytes this turn sent (M9 D40's principle): a debate request is `naive-6` since M11 named
        teammates apart from opponents (debate design D10); every other request keeps `naive-5`."""
        if ctx is not None and ctx.session.mode == "debate":
            return PROMPT_VERSION_DEBATE
        return self.prompt_version

    def _row(self, ctx: TurnContext) -> LlmCall:
        row = self.deps.llm("reply.debate" if ctx.session.mode == "debate" else "reply.chat")
        return row if isinstance(row, LlmCall) else FALLBACK_ROW

    def request(self, ctx: TurnContext, block: RetrievalBlock | None = None, *,
                force_cue: bool = False) -> tuple[ChatRequest, list[dict[str, Any]]]:
        s = ctx.session
        prefix: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(ctx)}]
        if s.summary:
            prefix.append({"role": "system", "content": f"{SUMMARY_HEADING}\n{s.summary}"})   # naive-4: S6
        you = str((s.world.you or {}).get("displayName") or "User")
        history = render_history(s.recent, ctx.speaker.id, you)
        messages = [*prefix, *history]
        if block is not None:
            messages.append({"role": "system", "content": block.content})
        cue = turn_cue(ctx)
        if cue:
            messages.append({"role": "system", "content": cue})
        elif force_cue or (history and history[-1]["role"] == "assistant"):
            # group A A2: a history that ends on the speaker's own line came back empty 2 times in 4 without a cue
            messages.append({"role": "system", "content": TRAILING_CUE})
        lang = language_cue(ctx)   # naive-5 (persona-context D35): a clearly non-English user line, last of all
        if lang:
            messages.append({"role": "system", "content": lang})
        req = llm_request(self._row(ctx), self.deps.prices.chat.model, messages, max_tokens=ctx.max_tokens,
                          stop=stop_sequences(ctx, you, history))
        return req, prefix

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        block = retrieval_block(ctx)
        req, prefix = self.request(ctx, block)
        prefix_text = json.dumps(prefix, ensure_ascii=False)
        digest = hashlib.sha256(prefix_text.encode("utf-8")).hexdigest()
        key = (ctx.session.session_id, ctx.speaker.id)
        warm = self._prefix.get(key) == digest
        self._prefix[key] = digest
        gw = self.deps.gateway()
        previous = next((p.emotion for p in ctx.session.participants if p.character_id == ctx.speaker.id), "neutral")
        names = own_names(ctx)
        # Every numbered passage, sent just before the first visible event (any engine event starts the message,
        # and a refusal must leave none); the runtime keeps only the markers the reply writes.
        pending_map = CitationMap(block.citations()) if block is not None and block.passages else None
        said: list[str] = []
        chosen: ParsedEmotion | None = None
        for attempt in (1, 2):
            if attempt == 2:
                req, _ = self.request(ctx, block, force_cue=True)
            estimate = gw.chat_estimate(req, warm=warm, prefix_tokens=count_tokens(prefix_text))
            parser = self.parser(ctx, previous, names)
            held: ParsedEmotion | None = None
            stream: Any = gw.chat_stream(req, ctx.call_ctx("reply"), estimate=estimate)
            try:
                async for chunk in stream:
                    if not chunk.content:
                        continue
                    for p in parser.feed(chunk.content):
                        if isinstance(p, ParsedEmotion):
                            held = p   # D17: the face waits for the first word, so an empty reply shows nothing
                            continue
                        if not p.text:
                            continue
                        if pending_map is not None:
                            yield pending_map
                            pending_map = None
                        if held is not None:
                            chosen, held = held, None
                            yield Emotion(chosen.emotion, chosen.source)
                        said.append(p.text)
                        yield Token(p.text)
            finally:
                await stream.aclose()
            for p in parser.close():
                if isinstance(p, ParsedEmotion):
                    held = p
                elif p.text:
                    if pending_map is not None:
                        yield pending_map
                        pending_map = None
                    if held is not None:
                        chosen, held = held, None
                        yield Emotion(chosen.emotion, chosen.source)
                    said.append(p.text)
                    yield Token(p.text)
            if said:
                break
            if attempt == 2:
                raise ProviderError("provider_error", EMPTY_REPLY)
        yield TracePatch(self.trace_patch(ctx, req, prefix, block, "".join(said), chosen, warm=warm))

    # ── seams (persona-context design D2): the agent engine overrides these three, the stream loop is shared ──
    def parser(self, ctx: TurnContext, previous: str, names: list[str]) -> TagParser:
        """The tag parser: naive reads the face from the tag and strips the speaker's name on the first line."""
        return TagParser(previous, speaker=names)

    def trace_patch(self, ctx: TurnContext, req: ChatRequest, prefix: list[dict[str, Any]], block: RetrievalBlock | None,
                    said: str, chosen: ParsedEmotion | None, *, warm: bool) -> dict[str, Any]:
        """The engine's TracePatch: the context X-ray, the face it showed, and the passages and memories it was given."""
        # docs/ai/05 X6, X7 (persona-context D15, D16): no cacheHitPct (Insight derives it from the provider's cached
        # tokens); the summary counts as history, `user` is the latest user message, the budget is the mode's planned
        # input. The one naive system prompt stays under `system` (persona 0); `mode` is the turn's cue.
        tail = req.messages[len(prefix):]
        block_msg = next((m for m in tail if block is not None and m["role"] == "system" and m["content"] == block.content),
                         None)
        cue_msg = tail[-1] if tail and tail[-1]["role"] == "system" and tail[-1] is not block_msg else None
        history_msgs = [m for m in tail if m is not block_msg and m is not cue_msg]
        latest = next((m.content for m in reversed(ctx.session.recent) if m.author_type == "user"), "")
        user = count_tokens(latest) if latest else 0
        summary = count_tokens(prefix[1]["content"]) if len(prefix) > 1 else 0
        history = summary + max(0, sum(count_tokens(m["content"]) for m in history_msgs) - user)
        block_tokens = count_tokens(block.content) if block is not None else 0
        memory_tokens = count_tokens(block.memory_text) if block is not None and block.memory_text else 0
        patch: dict[str, Any] = {
            "context": {"budget": planned_input(ctx.session.mode, self.deps.windows()),
                        "used": {"system": count_tokens(prefix[0]["content"]), "persona": 0, "memory": memory_tokens,
                                 "knowledge": block_tokens - memory_tokens, "history": history, "user": user,
                                 "mode": count_tokens(cue_msg["content"]) if cue_msg is not None else 0}},
        }
        if chosen is not None:
            patch["emotion"] = {"chosen": chosen.emotion, "source": chosen.source}
        if block is not None:
            knowledge = block.knowledge_trace(ctx.query, said)
            if knowledge is not None:
                patch["knowledge"] = knowledge
            memory = block.memory_trace()
            if memory is not None:
                patch["memory"] = memory
        return patch
