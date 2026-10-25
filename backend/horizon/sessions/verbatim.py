"""A verbatim line, spoken without a model call (docs/ai/04 P9; persona-context design D19; session-runtime "A verbatim
line is spoken without a model call").

The first chat with a character opens with its approved greeting, word for word, in every profile. The runtime picks
this engine (it is not a profile port) when the turn's `LineHint.verbatim` is set: it shows the face `happy` (source
`default`) and streams the text paced by the shared timing table on the session clock, with no gateway, ledger row,
energy drain, guardrail, memory writer or `model` trace section. Stop works as for any stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import Emotion, Token, TracePatch, TurnEvent
from horizon.ai.scripted.ports import chunk_tokens, tokenize
from horizon.domain.clock import Clock
from horizon.domain.runtime_config import Timing

FACE = "happy"


class VerbatimEngine:
    name = "verbatim"
    version = "1"
    prompt_version: str | None = None

    def __init__(self, timing: Timing, clock: Callable[[], Clock]) -> None:
        self.timing = timing
        self.clock = clock

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        text = ctx.line.text or ""
        t = self.timing
        chunks = chunk_tokens(tokenize(text, t.chars_per_token), t.tokens_per_event) or [text]
        clock = self.clock()
        await clock.sleep(t.first_token_ms / 1000)
        yield Emotion(FACE, "default")
        for i, chunk in enumerate(chunks):
            if i:
                await clock.sleep(t.tokens_per_event / t.tokens_per_sec)
            yield Token(chunk)
        yield TracePatch({"emotion": {"chosen": FACE, "source": "default"}})
