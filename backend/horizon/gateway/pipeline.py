"""The paid-call pipeline (doc backend/04 §1, design D5): every paid call, whatever the client.

    1. preflight  key guard → caps incl. in-flight reservations → reserve(estimate)   (refuse before any spend)
    2. request    the client call (HttpCore: pinned routing, timeouts, the no-double-charge retry)
    3. record     one ledger row: the provider's cost, or the estimate + generation_id (corrected later)
    4. settle     release the reservation AFTER the row commits; drain energy iff ctx.purpose == "reply"
    5. emit       budget.warning on crossing (budget.reached on refusal); the `on_call` hook (a no-op by default)

The gateway reaches the ledger through `LedgerPort`, so it never imports services (doc 01 §2 layering). A call that
is cancelled or breaks after it was sent is recorded at its estimate inside `asyncio.shield`, so a Stop can't lose
spend (NFR-30).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from horizon.domain import budget
from horizon.domain.pricing import (
    PricePeriod,
    PriceTable,
    count_tokens,
    estimate_chat,
    estimate_decision,
    estimate_embedding,
    estimate_image,
    expected_out,
)
from horizon.gateway.chat import ChatChunk, ChatClient, ChatRequest, ChatResult
from horizon.gateway.client import HttpCore
from horizon.gateway.context import CallContext
from horizon.gateway.decisions import DecisionsClient, DecisionsResponse
from horizon.gateway.embeddings import EmbeddingsClient, batches
from horizon.gateway.errors import ProviderError
from horizon.gateway.images import ImageResult, ImagesClient
from horizon.gateway.meta import MetaClient
from horizon.gateway.redact import redact_obj
from horizon.gateway.reservations import Hold, ReservationBook
from horizon.gateway.types import GatewayConfig, Usage

log = logging.getLogger("horizon.gateway")
T = TypeVar("T")


# ── the ledger, as the gateway sees it ──
@dataclass(frozen=True)
class LedgerRow:
    category: str
    purpose: str
    cost_usd: float
    cost_source: str                    # "provider" | "estimate"
    estimated_cost_usd: float
    price_period: str
    counts_to_creation_cap: bool
    model: str | None = None
    provider: str | None = None
    generation_id: str | None = None
    session_id: str | None = None
    character_id: str | None = None
    job_id: str | None = None
    message_id: str | None = None
    tokens_in: int | None = None
    tokens_cached: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None


@dataclass(frozen=True)
class RecordResult:
    row_id: str
    spent_before: float
    spent_after: float
    creation_before: float | None = None
    creation_after: float | None = None


class LedgerPort(Protocol):
    async def spent_today(self) -> float: ...
    async def creation_spent(self, character_id: str) -> float: ...
    async def record(self, row: LedgerRow, *, drain: bool) -> RecordResult: ...


@dataclass(frozen=True)
class Caps:
    daily_cap_usd: float
    creation_cap_usd: float
    warn_at_pct: float


@dataclass(frozen=True)
class Billing:
    """What the provider told us about a finished call."""

    generation_id: str | None
    usage: Usage | None
    provider: str | None
    model: str | None


OnCall = Callable[[CallContext, Mapping[str, Any], Mapping[str, Any]], Awaitable[None] | None]


def no_op_hook(_ctx: CallContext, _summary: Mapping[str, Any], _outcome: Mapping[str, Any]) -> None:
    return None


@dataclass
class Gateway:
    core: HttpCore
    cfg: GatewayConfig
    prices: PriceTable
    book: ReservationBook
    ledger: LedgerPort
    caps: Callable[[], Caps]
    period: Callable[[], PricePeriod]
    publish: Callable[[dict[str, Any]], None]
    decision_model: str
    on_estimate_row: Callable[[str], None] = lambda _row_id: None   # the cost corrector's queue
    on_call: OnCall = no_op_hook
    chat: ChatClient = field(init=False)
    decisions: DecisionsClient = field(init=False)
    images: ImagesClient = field(init=False)
    embeddings: EmbeddingsClient = field(init=False)
    meta: MetaClient = field(init=False)
    _background: set[asyncio.Task[Any]] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        t = self.cfg.timeouts
        self.chat = ChatClient(self.core, self.cfg)
        self.decisions = DecisionsClient(self.core, self.decision_model)
        self.images = ImagesClient(self.core, t.image)
        self.embeddings = EmbeddingsClient(self.core, provider=self.cfg.embedding_provider, batch_size=self.cfg.embed_batch,
                                           timeout_s=t.embedding)
        self.meta = MetaClient(self.core, t.meta)

    # ── estimates ──
    def chat_estimate(self, req: ChatRequest, *, recent_outs: Sequence[int] = (), warm: bool = False,
                      prefix_tokens: int = 0) -> float:
        other = max(0, count_tokens(json.dumps(req.messages, ensure_ascii=False)) - prefix_tokens)
        return estimate_chat(self.prices, prefix_tokens=prefix_tokens, warm=warm, other_in=other,
                             expected_out_tokens=expected_out(req.max_tokens, recent_outs), period=self.period())

    def decision_estimate(self, state: Any, questions: Mapping[str, Any]) -> float:
        tokens = count_tokens(json.dumps(state, ensure_ascii=False)) + sum(
            count_tokens(json.dumps(q, ensure_ascii=False)) for q in questions.values())
        return estimate_decision(self.prices, tokens)

    # ── 1. preflight ──
    async def _preflight(self, ctx: CallContext, estimate: float) -> Hold:
        self.core.require_key()
        caps = self.caps()
        async with self.book.lock:
            spent = await self.ledger.spent_today()
            moved = self.book.take_from_job(ctx.job_id, estimate) if ctx.job_id else 0.0
            if budget.exceeds_daily(spent, self.book.total(), estimate, caps.daily_cap_usd):
                self._give_back(ctx, moved)
                self._reached(ctx, "daily", spent, caps.daily_cap_usd)
                raise ProviderError("daily_budget_exceeded", "Today's spending cap is reached.")
            if ctx.creation and ctx.character_id:
                creation = await self.ledger.creation_spent(ctx.character_id)
                if budget.exceeds_creation(creation, self.book.reserved_for(ctx.character_id), estimate, caps.creation_cap_usd):
                    self._give_back(ctx, moved)
                    self._reached(ctx, "creation", creation, caps.creation_cap_usd)
                    raise ProviderError("creation_budget_exceeded", "This character's creation budget is used up.")
            return self.book.reserve(estimate, character_id=ctx.character_id, creation=ctx.creation)

    def _give_back(self, ctx: CallContext, moved: float) -> None:
        if moved and ctx.job_id:
            j = self.book.job_remaining(ctx.job_id)
            self.book.reserve_job(ctx.job_id, j + moved, character_id=ctx.character_id, creation=ctx.creation)

    def _reached(self, ctx: CallContext, scope: str, spent: float, cap: float) -> None:
        ev: dict[str, Any] = {"type": "budget.reached", "scope": scope, "spentUsd": round(spent, 6), "capUsd": cap}
        if ctx.session_id:
            ev["sessionId"] = ctx.session_id
        if ctx.job_id:
            ev["jobId"] = ctx.job_id
        self.publish(ev)

    # ── 3–5. record, settle, emit ──
    def _row(self, ctx: CallContext, estimate: float, *, cost: float | None, bill: Billing | None, model: str | None,
             generation_id: str | None, latency_ms: int) -> LedgerRow:
        u = bill.usage if bill else None
        actual = cost if cost is not None else (u.cost_usd if u else None)
        return LedgerRow(
            category=ctx.category, purpose=ctx.purpose,
            cost_usd=round(actual if actual is not None else estimate, 9),
            cost_source="provider" if actual is not None else "estimate",
            estimated_cost_usd=round(estimate, 9), price_period=self.period(), counts_to_creation_cap=ctx.creation,
            model=(bill.model if bill and bill.model else model), provider=bill.provider if bill else None,
            generation_id=(bill.generation_id if bill and bill.generation_id else generation_id),
            session_id=ctx.session_id, character_id=ctx.character_id, job_id=ctx.job_id, message_id=ctx.message_id,
            tokens_in=u.tokens_in if u else None, tokens_cached=u.tokens_cached if u else None,
            tokens_out=u.tokens_out if u else None, latency_ms=latency_ms)

    async def _record(self, ctx: CallContext, row: LedgerRow, summary: Mapping[str, Any]) -> RecordResult:
        res = await self.ledger.record(row, drain=ctx.drains)
        caps = self.caps()
        line = budget.warn_at(caps.daily_cap_usd, caps.warn_at_pct)
        if budget.crossed(res.spent_before, res.spent_after, line):
            self.publish({"type": "budget.warning", "scope": "daily", "spentUsd": round(res.spent_after, 6),
                          "capUsd": caps.daily_cap_usd})
        if ctx.creation and res.creation_before is not None and res.creation_after is not None:
            cline = budget.warn_at(caps.creation_cap_usd, caps.warn_at_pct)
            if budget.crossed(res.creation_before, res.creation_after, cline):
                self.publish({"type": "budget.warning", "scope": "creation", "spentUsd": round(res.creation_after, 6),
                              "capUsd": caps.creation_cap_usd})
        if row.cost_source == "estimate" and row.generation_id:
            self.on_estimate_row(res.row_id)
        await self._hook(ctx, summary, {"ledgerRowId": res.row_id, "costUsd": row.cost_usd, "costSource": row.cost_source,
                                        "provider": row.provider, "generationId": row.generation_id})
        return res

    async def _hook(self, ctx: CallContext, summary: Mapping[str, Any], outcome: Mapping[str, Any]) -> None:
        try:
            r = self.on_call(ctx, redact_obj(dict(summary)), redact_obj(dict(outcome)))
            if r is not None:
                await r
        except Exception:
            log.exception("on_call hook failed (ignored)")

    async def _record_shielded(self, ctx: CallContext, row: LedgerRow, summary: Mapping[str, Any]) -> None:
        """Record even while being cancelled: the write runs as its own task, and a second cancel can't abort it."""
        task = asyncio.get_running_loop().create_task(self._record(ctx, row, summary))
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass  # the task keeps running; the caller re-raises its own cancellation

    async def drain_background(self) -> None:
        """Wait for shielded ledger writes still in flight (shutdown, tests)."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    # ── the generic paid call ──
    async def paid(self, ctx: CallContext, estimate: float, send: Callable[[], Awaitable[tuple[T, Billing]]], *,
                   model: str | None, summary: Mapping[str, Any] | None = None) -> T:
        hold = await self._preflight(ctx, estimate)
        started = time.monotonic()
        summ = dict(summary or {}, model=model, purpose=ctx.purpose)

        def ms() -> int:
            return round((time.monotonic() - started) * 1000)

        try:
            try:
                value, bill = await send()
            except ProviderError as e:
                if e.cost_usd is not None or e.maybe_charged:
                    await self._record_shielded(ctx, self._row(ctx, estimate, cost=e.cost_usd, bill=None, model=model,
                                                               generation_id=e.generation_id, latency_ms=ms()), summ)
                raise
            except asyncio.CancelledError:
                await self._record_shielded(ctx, self._row(ctx, estimate, cost=None, bill=None, model=model,
                                                           generation_id=None, latency_ms=ms()), summ)
                raise
            await self._record(ctx, self._row(ctx, estimate, cost=None, bill=bill, model=model, generation_id=None,
                                              latency_ms=ms()), summ)
            return value
        finally:
            self.book.release(hold)

    # ── clients behind the pipeline ──
    async def chat_complete(self, req: ChatRequest, ctx: CallContext, *, estimate: float | None = None) -> ChatResult:
        est = self.chat_estimate(req) if estimate is None else estimate

        async def send() -> tuple[ChatResult, Billing]:
            r = await self.chat.complete(req)
            return r, Billing(r.generation_id, r.usage, r.provider, r.model)

        return await self.paid(ctx, est, send, model=req.model, summary={"kind": "chat", "maxTokens": req.max_tokens})

    async def chat_stream(self, req: ChatRequest, ctx: CallContext, *, estimate: float | None = None) -> AsyncIterator[ChatChunk]:
        """Streamed chat through the pipeline. Stopping early (aclose / cancel) records the estimate + generation_id."""
        est = self.chat_estimate(req) if estimate is None else estimate
        hold = await self._preflight(ctx, est)
        started = time.monotonic()
        summ = {"kind": "chat_stream", "maxTokens": req.max_tokens, "model": req.model, "purpose": ctx.purpose}
        gid: str | None = None
        usage: Usage | None = None
        provider: str | None = None
        done = False

        def row(cost: float | None, bill: Billing | None) -> LedgerRow:
            return self._row(ctx, est, cost=cost, bill=bill, model=req.model, generation_id=gid,
                             latency_ms=round((time.monotonic() - started) * 1000))

        try:
            try:
                async for chunk in self.chat.stream(req):
                    gid = chunk.generation_id
                    usage = chunk.usage or usage
                    provider = chunk.provider or provider
                    yield chunk
                done = True
            except ProviderError as e:
                gid = e.generation_id or gid
                if e.cost_usd is not None or e.maybe_charged:
                    await self._record_shielded(ctx, row(e.cost_usd, None), summ)
                raise
            except (asyncio.CancelledError, GeneratorExit):
                await self._record_shielded(ctx, row(None, None), summ)
                raise
            if done:
                await self._record(ctx, row(None, Billing(gid, usage, provider, req.model)), summ)
        finally:
            self.book.release(hold)

    async def decide(self, state: Any, questions: Mapping[str, Mapping[str, Any]], ctx: CallContext, *,
                     estimate: float | None = None, model: str | None = None) -> DecisionsResponse:
        est = self.decision_estimate(state, questions) if estimate is None else estimate
        m = model or self.decision_model

        async def send() -> tuple[DecisionsResponse, Billing]:
            r = await self.decisions.decide(state, questions, model=m)
            return r, Billing(r.generation_id, r.usage, None, r.model or m)

        return await self.paid(ctx, est, send, model=m,
                               summary={"kind": "decision", "questions": sorted(questions)})

    async def generate_image(self, ctx: CallContext, *, model: str, prompt: str, kind: str = "portrait",
                             refs: list[str] | None = None, resolution: str | None = None, aspect_ratio: str | None = None,
                             seed: int | None = None) -> ImageResult:
        async def send() -> tuple[ImageResult, Billing]:
            r = await self.images.generate(model=model, prompt=prompt, refs=refs, resolution=resolution,
                                           aspect_ratio=aspect_ratio, seed=seed)
            return r, Billing(r.generation_id, r.usage, r.provider, model)

        return await self.paid(ctx, estimate_image(self.prices, kind), send, model=model, summary={"kind": "image"})

    async def embed(self, texts: Sequence[str], ctx: CallContext, *, model: str, dimensions: int | None = None) -> list[list[float]]:
        """Batches of `embed_batch` texts; each batch is one paid call and one ledger row. Vectors keep input order."""
        out: list[list[float]] = []
        for chunk in batches(texts, self.cfg.embed_batch):
            est = estimate_embedding(self.prices, sum(count_tokens(x) for x in chunk))

            async def send(c: list[str] = chunk) -> tuple[list[list[float]], Billing]:
                r = await self.embeddings.embed_batch(c, model=model, dimensions=dimensions)
                return r.vectors, Billing(r.generation_id, r.usage, r.provider, model)

            out.extend(await self.paid(ctx, est, send, model=model, summary={"kind": "embedding", "texts": len(chunk)}))
        return out
