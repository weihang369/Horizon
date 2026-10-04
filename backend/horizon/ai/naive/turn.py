"""The naive DeepSeek TurnEngine (doc 05 §5, design D11). Filled in by task group 10."""

from __future__ import annotations

from collections.abc import AsyncIterator

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import TurnEvent
from horizon.ai.scripted.ports import AiDeps


class NaiveTurnEngine:
    name = "naive"
    version = "1"
    prompt_version: str | None = "naive-1"

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        raise NotImplementedError("naive turn engine: task group 10")
        yield  # pragma: no cover
