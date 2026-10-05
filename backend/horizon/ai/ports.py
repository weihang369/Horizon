"""AI port protocols (doc 05 §2.2) and the values that cross them (`TurnEvent`, `TracePatch`, `RoutingDecision`).

The session runtime calls these and never inspects which implementation runs (scripted or naive, `ai/profile.py`).

TracePatch rules (doc 05 §2.3): a port may set `emotion`, `context`, `guardrail`, `memory`, `knowledge`,
`contextInSession` and `graph`. The runtime owns `model`, `energy`, `routing` and `calls` (from the ledger and the
router) and drops a patch's attempt to set them, applying the rest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from horizon.ai.contexts import RouteContext, SessionContext, TurnContext

OWNED_TRACE_KEYS = frozenset({"model", "energy", "routing", "calls", "messageId"})


# ── TurnEvent ──
@dataclass(frozen=True)
class Emotion:
    emotion: str
    source: str = "llm"


@dataclass(frozen=True)
class Token:
    delta: str


@dataclass(frozen=True)
class CitationMap:
    citations: list[dict[str, Any]]


@dataclass(frozen=True)
class TracePatch:
    patch: dict[str, Any]


TurnEvent = Emotion | Token | CitationMap | TracePatch


@dataclass(frozen=True)
class RoutingDecision:
    speakers: list[str]                                  # who answers, in order (forced first)
    candidates: list[dict[str, Any]] = field(default_factory=list)   # [{characterId, p}] sorted by p
    question: str = "Who should answer?"
    fallback: bool = False
    call: dict[str, Any] | None = None                   # the paid route call as a TurnTrace.calls entry


@dataclass(frozen=True)
class Reaction:
    character_id: str
    emotion: str
    p: float | None
    delay_ms: float


@dataclass(frozen=True)
class GuardrailResult:
    verdict: str                                         # pass | flag | block
    checks: list[dict[str, Any]] = field(default_factory=list)


class TurnEngine(Protocol):
    name: str
    version: str
    prompt_version: str | None

    def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]: ...


class Router(Protocol):
    async def route(self, ctx: RouteContext) -> RoutingDecision: ...


class ReactionPredictor(Protocol):
    def predict(self, ctx: SessionContext, message_id: str, speaker_id: str, listeners: list[str],
                seed: str) -> list[Reaction]: ...


class DebateHost(Protocol):
    def round_note(self, phase: str, round_: int, iteration: int) -> str: ...
    def narration(self, phase: str, motion: str) -> str: ...
    async def verdict(self, ctx: SessionContext, by: str, picked: str | None) -> dict[str, Any]: ...


class WatchDirector(Protocol):
    def order(self, cast: list[str], opening: str | None) -> list[str]: ...


class Summariser(Protocol):
    async def episode(self, ctx: SessionContext) -> str: ...
    def rolling(self, previous: str | None, dropped: list[str]) -> str: ...


class Guardrail(Protocol):
    async def check(self, ctx: TurnContext, text: str) -> GuardrailResult: ...
