"""AI port protocols (doc 05 §2.2) and the values that cross them (`TurnEvent`, `TracePatch`, `RoutingDecision`).

The session runtime calls these and never inspects which implementation runs (scripted or naive, `ai/profile.py`).

TracePatch rules (doc 05 §2.3): a port may set `emotion`, `context`, `guardrail`, `memory`, `knowledge`,
`contextInSession` and `graph`. The runtime owns `model`, `energy`, `routing` and `calls` (from the ledger and the
router) and drops a patch's attempt to set them, applying the rest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NamedTuple, Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.contexts import (
    Assessment,
    CastPlan,
    CastRequest,
    DebatePlan,
    DebateRequest,
    FollowPlan,
    FollowRequest,
    HostKey,
    PlanRequest,
    ReactionRequest,
    RouteContext,
    SessionContext,
    TurnContext,
    TurnPlan,
    VerdictRequest,
)
from horizon.gateway.context import CallContext

OWNED_TRACE_KEYS = frozenset({"model", "energy", "routing", "calls", "messageId", "system1"})   # system1: rev 1.4, D24


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
    system1: dict[str, Any] | None = None                # rev 1.4: `{seed, questions: [route row]}`, on every reply (D25)


@dataclass(frozen=True)
class Reaction:
    character_id: str
    emotion: str
    p: float | None
    delay_ms: float
    source: str = "classifier"                           # "default" for an E3 fade (M9 D18)


@dataclass(frozen=True)
class GuardrailResult:
    verdict: str                                         # pass | flag | block
    checks: list[dict[str, Any]] = field(default_factory=list)
    # M14 (safety D9, D19): the System 1 row (agent only), Jev's p, and whether the check fell back (late or failed)
    rows: list[dict[str, Any]] = field(default_factory=list)
    p: float | None = None
    fallback: bool = False


class TurnEngine(Protocol):
    name: str
    version: str
    prompt_version: str | None

    def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]: ...


class Router(Protocol):
    async def route(self, ctx: RouteContext) -> RoutingDecision: ...


class FollowCall(Protocol):
    """M10 (doc 07 G2; group-watch D3, D8): a follow plan already started at the first reply's stream end. `by` waits
    until the deadline the runtime knows only at `turn.end`, and never raises except CancelledError."""

    async def by(self, deadline: datetime) -> FollowPlan: ...
    def cancel(self) -> None: ...


class DebateCall(Protocol):
    """M11 (doc 08 V2; doc 13 W11; debate design D5, D8): a debate plan already started at `turn.end`. One request
    serves two waits: `member` fixes who speaks by the deadline (`turn.next` names them), and `faces` reads the same
    answer when the turn starts (fallback faces if it hasn't landed). Neither raises except CancelledError."""

    async def member(self, deadline: datetime) -> DebatePlan: ...
    async def faces(self, until: datetime) -> DebatePlan: ...
    async def late_rows(self) -> DebatePlan | None: ...
    def cancel(self) -> None: ...
    @property
    def landed(self) -> bool: ...


class TurnPlanner(Protocol):
    """M9 (docs/ai/01 A4; turn-plan-emotion design D4): plans a turn before its reply. Returns None when the profile
    has no planner (`naive`). It never raises, except CancelledError: a failed or late Jev call is a fallback plan.

    M10 (group-watch D3): `plan_cast` plans group and watch turns (who speaks, and every candidate's face) and
    `start_follow` starts the follow plan. Both return None when the profile has no planner for them, and the mode
    then keeps its own routing. `decides_retrieval` says whether a planned turn's retrieval follows the plan (D18)."""

    decides_retrieval: bool

    async def plan(self, req: PlanRequest) -> TurnPlan | None: ...
    async def plan_cast(self, req: CastRequest) -> CastPlan | None: ...
    def start_follow(self, req: FollowRequest) -> FollowCall | None: ...
    def start_debate(self, req: DebateRequest) -> DebateCall | None: ...   # M11 (debate D5)


class FaceCheckOut(NamedTuple):
    """A face check's result: its System 1 row, its call entry, and the emotion the words show (D-112: on a clash the
    runtime switches the face to it)."""

    row: dict[str, Any]
    call: dict[str, Any] | None
    words: str | None = None


class FaceChecker(Protocol):
    """M9 (doc 13 W2; design D23, D24): after `turn.end`, which emotion the reply's words show. Returns the System 1
    row, its call entry and the words' emotion, or None (no check for this profile, or the call was late or failed)."""

    async def check(self, ctx: SessionContext, message_id: str, speaker_id: str, face: str,
                    text: str) -> FaceCheckOut | None: ...


class ReactionPredictor(Protocol):
    """Async, called inside the reactions task after `turn.end`, never in `finish` (M9 D18)."""

    async def predict(self, req: ReactionRequest) -> list[Reaction]: ...


class DebateHost(Protocol):
    """M11 (doc 08 V6; debate D11): the fixed lines, and `narration`, the async written line (None on any failure; the
    runtime owns the timing and shows `fixed_line` when it isn't ready by its deadline)."""

    def round_note(self, phase: str, round_: int, iteration: int) -> str: ...
    def fixed_line(self, key: HostKey, by: str, motion: str = "") -> str: ...
    async def narration(self, ctx: SessionContext, key: HostKey, *,
                        finish: Callable[[], str | None] | None = None) -> str | None: ...
    # M11 (doc 08 V9; debate D14): the verdict splits into the work, started early and cancellable, and the delivery
    async def assess(self, req: VerdictRequest) -> Assessment: ...
    def deliver(self, a: Assessment, picked: str | None) -> dict[str, Any]: ...


class WatchDirector(Protocol):
    def order(self, cast: list[str], opening: str | None) -> list[str]: ...


class Summariser(Protocol):
    async def episode(self, ctx: SessionContext) -> str: ...
    # M8 (docs/ai/05 X3): async, after `turn.end`; `lines` are the dropped messages as `Name: line` lines
    async def rolling(self, ctx: SessionContext, previous: str | None, lines: Sequence[str]) -> str: ...


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


@dataclass(frozen=True)
class DraftWorld:
    """What the drafter knows of the world (docs/ai/04 P11; persona-context design D17): its name, the names its
    characters already use (tombstones included) and the You card, so a companion's relationship fits the user."""

    name: str
    names_in_use: tuple[str, ...] = ()
    you: Mapping[str, Any] | None = None


class ProfileDrafter(Protocol):
    shared_call: bool   # True: one call (the `profile` task) feeds the other draft parts at $0

    def expected_ms(self, duration_ms: float) -> float: ...
    async def draft(self, ctx: CallContext, *, seed_prompt: str, intent: str, cost_usd: float, duration_ms: float,
                    model: str, hooks: PaidHooks, world: DraftWorld | None = None) -> dict[str, Any]: ...
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


# ── Memory (M5, knowledge-memory-storage design D17; doc 05 §2.2) ──
@dataclass(frozen=True)
class MemoryDraft:
    """A memory to write: what the AI layer decided to remember, from the perspective character's point of view."""

    kind: str                                            # fact | event | preference | about_user
    text: str
    importance: float                                    # 0..1
    source_session_id: str | None = None
    source_message_id: str | None = None
    source_variant_id: str | None = None
    source_mode: str | None = None                       # D-71: one_on_one | group | debate | watch
    about_character_id: str | None = None


@dataclass(frozen=True)
class Insert:
    draft: MemoryDraft


@dataclass(frozen=True)
class Supersede:
    old_ids: list[str]
    draft: MemoryDraft


@dataclass(frozen=True)
class Reinforce:
    id: str
    importance: float


@dataclass(frozen=True)
class Touch:
    ids: list[str]


MemoryOp = Insert | Supersede | Reinforce | Touch


class SessionRecall(Protocol):
    """M13 (memory D36): an `agent` speaker's recall over this session's indexed lines and its overflow memories (D31),
    Jev call 2 (D33) and the keep rule; called from the deep graph only (`horizon.ai.agent.deep.DeepSteps.recall`).
    `docs_bundle` is the documents' query when that branch ran, else None (a recall-only turn: no rewrite). Returns the
    kept hits, the outcome, the System 1 rows and the evaluation's checks. `naive` and `scripted` keep `MemoryRetriever`'s
    tail recall."""

    async def recall(self, req: Any, docs_bundle: Any) -> dict[str, Any]: ...


class MemoryWriter(Protocol):
    """M13 (memory D12; doc 09 M1–M5): a pause run's writer. It reads one stretch (`horizon.services.memory.stretch`:
    the numbered new lines, every present character's current list, the context) and returns each character's memory
    operations, the duplicate check's vectors and a log of what it dropped; the run commits them with the checkpoint
    (`MemoryStore.apply_run`). `ctx` is the run's `RunContext`: call contexts that never pause sessions, the knobs and
    the run's reads. `scripted` writes nothing, `naive` makes the one rewrite call, `agent` adds Jev (D18)."""

    async def on_stretch(self, stretch: Any, ctx: Any) -> Any: ...
