"""AI port protocols (doc 05 §2.2) and the values that cross them (`TurnEvent`, `TracePatch`, `RoutingDecision`).

The session runtime calls these and never inspects which implementation runs (scripted or naive, `ai/profile.py`).

TracePatch rules (doc 05 §2.3): a port may set `emotion`, `context`, `guardrail`, `memory`, `knowledge`,
`contextInSession` and `graph`. The runtime owns `model`, `energy`, `routing` and `calls` (from the ledger and the
router) and drops a patch's attempt to set them, applying the rest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.contexts import RouteContext, SessionContext, TurnContext
from horizon.gateway.context import CallContext

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


# ── Creation ports (M4, generation-jobs design D9) ──
@dataclass(frozen=True)
class PaidHooks:
    """The job worker's never-pay-twice steps, passed through to the gateway's paid call (design D3)."""

    before_send: Callable[[], Awaitable[None]] | None = None
    after_response: Callable[[Any], Awaitable[None]] | None = None
    commit_with: Callable[[AsyncConnection, str], Awaitable[None]] | None = None


@dataclass(frozen=True)
class ImageJob:
    """One image to make. `mode`: `base` (text-to-image), `edit` (an edit of `reference`, the locked base original) or
    `sheet` (a 2×4 expression sheet). `duration_ms` paces the scripted generator; `label` and `palette` (stage,
    primary, secondary) draw its placeholder."""

    task_id: str
    mode: str
    prompt: str
    model: str
    price_kind: str
    duration_ms: float
    label: str
    palette: tuple[str, str, str]
    reference: bytes | None = None
    aspect_ratio: str = "3:4"


class ProfileDrafter(Protocol):
    shared_call: bool   # True: one call (the `profile` task) feeds the other draft parts at $0

    def expected_ms(self, duration_ms: float) -> float: ...
    async def draft(self, ctx: CallContext, *, seed_prompt: str, intent: str, cost_usd: float, duration_ms: float,
                    model: str, hooks: PaidHooks) -> dict[str, Any]: ...
    async def regenerate_field(self, ctx: CallContext, *, profile: Mapping[str, Any], field: str, attempt: int,
                               cost_usd: float, duration_ms: float, model: str, hooks: PaidHooks) -> dict[str, Any]: ...


class ImageGenerator(Protocol):
    name: str

    def expected_ms(self, job: ImageJob) -> float: ...
    async def generate(self, ctx: CallContext, job: ImageJob, hooks: PaidHooks) -> bytes: ...


@dataclass(frozen=True)
class SongJob:
    """One theme song to make (creation-followups design D3): the brief and title the prompt is compiled from, and
    the configured music model."""

    task_id: str
    model: str
    brief: Mapping[str, Any]
    title: str


class SongGenerator(Protocol):
    """`paid` False: the procedural theme only ($0, no ledger row, D-83); `paid` True: one music call per attempt
    through `generate` (D-87), with `theme` still building the procedural fallback (design D7)."""

    model: str
    paid: bool

    def expected_ms(self, duration_ms: float) -> float: ...
    def theme(self, seed: str, brief: Mapping[str, Any], title: str | None) -> dict[str, Any]: ...
    async def generate(self, ctx: CallContext, job: SongJob, hooks: PaidHooks) -> bytes: ...
