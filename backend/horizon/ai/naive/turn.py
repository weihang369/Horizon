"""The naive DeepSeek TurnEngine (doc 05 §5; ai-ports "Naive reply engine"; design D11).

One streamed call to the pinned chat model, reasoning off, `max_tokens` from the per-mode reply caps. The prompt is
the compiled persona (system), the rolling summary, then the history window (and a short cue for turns that aren't a
plain reply). The SHA-256 of the system + summary prefix is kept per (session, speaker): when it matches the last
call, the estimate prices that prefix as cached (`warm=True`). The `<e:label>` tag is parsed off the stream; a
mid-stream provider error propagates, and the runner keeps the partial text (`interrupted`, `interruptedBy: "error"`).

Prompt v2 (D-93): retrieved passages and memories go in one system message after the history. The engine yields a
`CitationMap` for every numbered passage and, after the stream, reports in the trace which passages its reply cited
(`[n]` in its own output) and which memories it was given.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any

from horizon.ai.contexts import TurnContext
from horizon.ai.naive.prompt import PROMPT_VERSION, RetrievalBlock, retrieval_block, system_prompt, turn_cue
from horizon.ai.naive.tag_parser import ParsedEmotion, TagParser
from horizon.ai.naive.window import render_history
from horizon.ai.ports import CitationMap, Emotion, Token, TracePatch, TurnEvent
from horizon.ai.scripted.ports import AiDeps
from horizon.domain.pricing import count_tokens
from horizon.gateway.chat import ChatRequest


class NaiveTurnEngine:
    name = "naive"
    version = "2"
    prompt_version: str | None = PROMPT_VERSION

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps
        self._prefix: dict[tuple[str, str], str] = {}

    def request(self, ctx: TurnContext,
                block: RetrievalBlock | None = None) -> tuple[ChatRequest, list[dict[str, Any]]]:
        s = ctx.session
        prefix: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(ctx)}]
        if s.summary:
            prefix.append({"role": "system", "content": f"Earlier in this conversation (summary):\n{s.summary}"})
        you = str((s.world.you or {}).get("displayName") or "User")
        messages = [*prefix, *render_history(s.recent, ctx.speaker.id, you)]
        if block is not None:
            messages.append({"role": "system", "content": block.content})
        cue = turn_cue(ctx)
        if cue:
            messages.append({"role": "system", "content": cue})
        req = ChatRequest(model=self.deps.prices.chat.model, messages=messages, max_tokens=ctx.max_tokens,
                          reasoning={"enabled": False})
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
        estimate = gw.chat_estimate(req, warm=warm, prefix_tokens=count_tokens(prefix_text))
        previous = next((p.emotion for p in ctx.session.participants if p.character_id == ctx.speaker.id), "neutral")
        parser = TagParser(previous)
        chosen: ParsedEmotion | None = None
        # Every numbered passage, sent just before the first visible event (any engine event starts the message,
        # and a refusal must leave none); the runtime keeps only the markers the reply writes.
        pending_map = CitationMap(block.citations()) if block is not None and block.passages else None
        said: list[str] = []
        stream: Any = gw.chat_stream(req, ctx.call_ctx("reply"), estimate=estimate)
        try:
            async for chunk in stream:
                if not chunk.content:
                    continue
                for p in parser.feed(chunk.content):
                    if pending_map is not None:
                        yield pending_map
                        pending_map = None
                    if isinstance(p, ParsedEmotion):
                        chosen = p
                        yield Emotion(p.emotion, p.source)
                    elif p.text:
                        said.append(p.text)
                        yield Token(p.text)
        finally:
            await stream.aclose()
        for p in parser.close():
            if pending_map is not None:
                yield pending_map
                pending_map = None
            if isinstance(p, ParsedEmotion):
                chosen = p
                yield Emotion(p.emotion, p.source)
            elif p.text:
                said.append(p.text)
                yield Token(p.text)
        block_tokens = count_tokens(block.content) if block is not None else 0
        history = sum(count_tokens(m["content"]) for m in req.messages[len(prefix):]) - block_tokens
        memory_tokens = count_tokens(block.memory_text) if block is not None and block.memory_text else 0
        patch: dict[str, Any] = {
            "context": {"budget": self.deps.window_tokens, "cacheHitPct": 100 if warm else 0,
                        "used": {"system": count_tokens(prefix[0]["content"]), "persona": 0, "memory": memory_tokens,
                                 "knowledge": block_tokens - memory_tokens, "history": history, "user": 0,
                                 "mode": count_tokens(prefix[1]["content"]) if len(prefix) > 1 else 0}},
        }
        if chosen is not None:
            patch["emotion"] = {"chosen": chosen.emotion, "source": chosen.source}
        if block is not None:
            knowledge = block.knowledge_trace(ctx.query, "".join(said))
            if knowledge is not None:
                patch["knowledge"] = knowledge
            memory = block.memory_trace()
            if memory is not None:
                patch["memory"] = memory
        yield TracePatch(patch)
