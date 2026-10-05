"""TurnRunner (session-runtime design D5; doc 01 §4.2 turn order).

One character turn:
1. the speaker is chosen by the mode or the router;
2. the energy gate (below `estReplyPoints` for the period: the caller's asleep/skip path, no model call);
3. the `messageId` (or `variantId`) is allocated before any model call;
4. the preamble: `turn.next`, then `turn.thinking` after `thinkingMs`;
5. the engine runs under an `llm_slots` slot; the budget is reserved inside the gateway preflight. `turn.start` is
   emitted lazily at the engine's first event, so a refusal (cap, key, credits) leaves no message;
6. TurnEvents map to session events: `Emotion` → `emotion`, `Token` → the coalescer → `token`, `CitationMap` kept for
   the end, `TracePatch` deep-merged (the owned sections `model`/`energy`/`routing`/`calls` are dropped);
7. the end: the guardrail check, then `turn.end` (usage from the ledger, citations filtered to the `[n]` markers in the
   content, `message_citations` rows), the `energy` event after the drain, and `insight` with the full trace;
8. listener reactions run in the background and never delay the next speaker.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import DebateMeta, LineHint, TurnContext
from horizon.ai.ports import OWNED_TRACE_KEYS, CitationMap, Emotion, Token, TracePatch
from horizon.api.errors import DEFAULT_RETRYABLE
from horizon.domain.energy import points_for_cost
from horizon.domain.ids import new_id
from horizon.domain.timeutil import to_ms
from horizon.gateway.errors import ProviderError
from horizon.sessions.actor import SessionActor, TurnInfo
from horizon.sessions.coalesce import Coalescer
from horizon.sessions.context import character_view, characters, energy_of, maintain_window, session_context
from horizon.sessions.prefetch import Prefetch
from horizon.sessions.writer import TraceMeta

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.sessions")

Wire = dict[str, Any]
STATUS_BY_CODE = {"content_refused": "error"}
_MARKER = re.compile(r"\[(\d+)\]")


@dataclass
class TurnSpec:
    speaker: str
    line: LineHint = field(default_factory=LineHint)
    prompt: str = ""
    message: dict[str, Any] | None = None          # extra Message fields on turn.start (kind, debate, forcedSpeaker…)
    variant_of: str | None = None                   # regenerate: stream a new variant into this message
    forced_by: str | None = None
    skipped: list[dict[str, Any]] | None = None
    routing: dict[str, Any] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)   # turn-level calls (the route decision, OQ-13)
    reactions: bool = True
    debate: DebateMeta | None = None
    direction_note: str | None = None


@dataclass
class TurnOutcome:
    message_id: str | None
    status: str          # complete | interrupted | error | refused | asleep | missing


def deep_merge(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, Mapping) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def merge_patch(trace: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """Apply an engine's TracePatch, dropping the sections the runtime owns (design D5)."""
    owned = sorted(k for k in patch if k in OWNED_TRACE_KEYS)
    if owned:
        log.warning("trace patch tried to set runtime-owned sections %s (dropped)", owned)
    return deep_merge(trace, {k: v for k, v in patch.items() if k not in OWNED_TRACE_KEYS})


def kept_citations(content: str, citations: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """D-59: only the citations whose `[n]` marker appears in the final content."""
    if not citations:
        return []
    used = {int(m) for m in _MARKER.findall(content)}
    return [c for c in citations if int(c["n"]) in used]


class TurnRunner:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    # ── energy ──
    async def energy_now(self, character_id: str) -> Wire | None:
        rows = await characters(self.rt, [character_id])
        row = rows.get(character_id)
        if row is None or row["deleted_at"] is not None:
            return None
        return energy_of(self.rt, row)

    async def is_asleep(self, character_id: str) -> bool:
        e = await self.energy_now(character_id)
        return e is None or float(e["current"]) < self.rt.est_reply_points()

    def key_set(self) -> bool:
        return self.rt.keys.status() == "set"

    # ── one turn ──
    async def run(self, actor: SessionActor, spec: TurnSpec, *, prefetch: Prefetch | None = None) -> TurnOutcome:
        """One turn. A `prefetch` (design D5) was generated ahead of its slot: it is released here, its energy already
        spent, so it skips the gate."""
        rt = self.rt
        rows = await characters(rt, [spec.speaker])
        row = rows.get(spec.speaker)
        if row is None or row["deleted_at"] is not None:
            if prefetch is not None:
                await prefetch.discard()
            return TurnOutcome(None, "missing")
        if prefetch is None and float(energy_of(rt, row)["current"]) < rt.est_reply_points():
            return TurnOutcome(None, "asleep")
        existing = actor.state["messages"].get(spec.variant_of) if spec.variant_of else None
        mid = prefetch.message_id if prefetch is not None else spec.variant_of or new_id("msg")
        # The mock's rule: `${messageId}_v${(variants.length || 1) + 1}`.
        vid = f"{mid}_v{(len((existing or {}).get('variants') or []) or 1) + 1}" if spec.variant_of else None
        info = TurnInfo(mid, spec.speaker, vid, started_iso="" if prefetch is not None else rt.now_iso(),
                        t0_ms=float(to_ms(rt.clock.now())), spec=spec)
        actor.current = info
        started_iso = info.started_iso
        t0 = info.t0_ms
        nxt: Wire = {"nextSpeakerId": spec.speaker}
        if spec.forced_by:
            nxt["forcedBy"] = spec.forced_by
        if spec.skipped:
            nxt["skipped"] = spec.skipped
        try:
            await actor.emit({"type": "turn.next", "payload": nxt})
            await rt.clock.sleep(rt.runtime_cfg.timing.thinking_ms / 1000)
            await actor.emit({"type": "turn.thinking", "payload": {"characterId": spec.speaker}})
            if prefetch is not None:
                info.ctx = prefetch.ctx
                return await self._stream(actor, spec, info, prefetch.ctx, t0, started_iso, prefetch=prefetch)
            await maintain_window(rt, actor)
            sctx = await session_context(rt, actor)
            caps = rt.runtime_cfg.runtime.reply_max_tokens
            cfg = sctx.config or {}
            ctx = TurnContext(session=sctx, speaker=character_view(row), message_id=mid, variant_id=vid, prompt=spec.prompt,
                              line=spec.line, turn_index=actor.mode.turn,
                              max_tokens=caps.for_mode(sctx.mode, str(cfg.get("turnLength")) if sctx.mode == "debate" else None),
                              direction_note=spec.direction_note, debate=spec.debate)
            actor.mode.turn += 1
            info.ctx = ctx
            return await self._stream(actor, spec, info, ctx, t0, started_iso)
        finally:
            if actor.current is info and info.closed:
                actor.current = None

    async def _stream(self, actor: SessionActor, spec: TurnSpec, info: TurnInfo, ctx: TurnContext, t0: float,
                      started_iso: str, *, prefetch: Prefetch | None = None) -> TurnOutcome:
        rt = self.rt
        knobs = rt.runtime_cfg.runtime
        clock = rt.clock
        engine = info.engine = prefetch.engine if prefetch is not None else rt.ai.turn(self.key_set())
        co = Coalescer(knobs.coalesce_max_chars, knobs.coalesce_max_ms, lambda: float(to_ms(clock.now())))
        timer: asyncio.Task[None] | None = None
        trace: dict[str, Any] = {}
        citations: list[dict[str, Any]] | None = None
        first_token_ms: float | None = None
        fault = rt.take_stream_fault()
        tokens_seen = 0
        err: ProviderError | None = None

        async def flush() -> None:
            text = co.take()
            if text:
                info.content += text
                payload: Wire = {"messageId": info.message_id, "delta": text}
                if info.variant_id:
                    payload["variantId"] = info.variant_id
                await actor.emit({"type": "token", "payload": payload})

        async def trailing() -> None:
            await clock.sleep(co.due_in_ms() / 1000)
            await flush()

        def arm() -> None:
            nonlocal timer
            if co.pending and (timer is None or timer.done()):
                timer = rt.spawn(f"coalesce:{actor.sid}", trailing())

        async def settle_timer() -> None:
            nonlocal timer
            if timer is not None and not timer.done():
                timer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await timer
            timer = None

        slot: Any = rt.llm_slots.slot() if prefetch is None else contextlib.nullcontext()
        try:
            async with slot:
                agen: Any = prefetch.replay() if prefetch is not None else engine.run(ctx)
                try:
                    async for ev in agen:
                        if not info.started:
                            await self._start(actor, spec, info)
                        if isinstance(ev, Token):
                            if first_token_ms is None:
                                first_token_ms = to_ms(clock.now()) - t0
                                info.first_token_ms = first_token_ms
                            out = co.add(ev.delta)
                            if out is not None:
                                await settle_timer()
                                co.buf = out
                                await flush()
                            else:
                                arm()
                            if fault is not None:
                                tokens_seen += max(1, -(-len(ev.delta) // rt.runtime_cfg.timing.chars_per_token))
                                if tokens_seen >= fault:
                                    raise ProviderError("network", "Can't reach the Horizon server.")
                        elif isinstance(ev, Emotion):
                            await settle_timer()
                            await flush()
                            await actor.emit({"type": "emotion", "payload": {
                                "messageId": info.message_id, "characterId": info.character_id, "emotion": ev.emotion,
                                "source": ev.source}})
                        elif isinstance(ev, CitationMap):
                            citations = info.citations = list(ev.citations)
                        elif isinstance(ev, TracePatch):
                            trace = info.trace = merge_patch(trace, ev.patch)
                finally:
                    await agen.aclose()
        except ProviderError as e:
            if not info.started:
                await settle_timer()
                info.closed = True
                if e.code != "daily_budget_exceeded":  # the cap pause (D7) answers a cap refusal
                    await actor.emit({"type": "error", "payload": {"code": e.code, "message": e.message,
                                                                   "retryable": DEFAULT_RETRYABLE.get(e.code, True)}})
                return TurnOutcome(None, "refused")
            err = e
        except asyncio.CancelledError:
            if timer is not None:
                timer.cancel()
            raise
        await settle_timer()
        await flush()
        if prefetch is not None:
            await prefetch.link()
        status = "complete"
        if err is not None:
            status = STATUS_BY_CODE.get(err.code, "interrupted")
        elif not info.started:
            info.closed = True
            return TurnOutcome(None, "refused")
        await self.finish(actor, info, spec, ctx, status=status, err=err, trace=trace, citations=citations,
                          first_token_ms=first_token_ms, t0=t0, started_iso=started_iso, engine=engine)
        return TurnOutcome(info.message_id, status)

    async def _start(self, actor: SessionActor, spec: TurnSpec, info: TurnInfo) -> None:
        payload: Wire = {"messageId": info.message_id, "author": {"type": "character", "characterId": info.character_id}}
        if info.variant_id:
            payload["variantId"] = info.variant_id
        elif spec.message:
            payload["message"] = spec.message
        info.started = True
        await actor.emit({"type": "turn.start", "payload": payload})

    # ── the end of a turn ──
    async def finish(self, actor: SessionActor, info: TurnInfo, spec: TurnSpec, ctx: TurnContext | None, *, status: str,
                     err: ProviderError | None, trace: dict[str, Any], citations: list[dict[str, Any]] | None,
                     first_token_ms: float | None, t0: float, started_iso: str, engine: Any = None,
                     interrupted_by: str | None = None) -> None:
        rt = self.rt
        await rt.gateway.drain_background()   # a cut or stopped stream records its estimate in a shielded task
        mid = info.message_id
        total_ms = to_ms(rt.clock.now()) - t0
        scrub = False
        if status == "complete" and ctx is not None:
            check = await rt.ai.guardrail(self.key_set()).check(ctx, info.content)
            if check.checks:
                trace = deep_merge(trace, {"guardrail": {"checks": check.checks}})
            if check.verdict == "block":
                status, scrub = "error", True
                err = ProviderError("content_refused", "The reply was blocked by the safety check.")
        ledger = rt.ledger
        since = started_iso or None   # a released prefetch's row was recorded before its slot
        usage = await ledger.reply_usage(mid, since=since)
        row = await ledger.reply_row(mid, since=since)
        spent = points_for_cost(float(usage["costUsd"])) if usage else 0
        events: list[Wire] = []
        if err is not None:
            events.append({"type": "error", "payload": {"code": err.code, "message": err.message,
                                                        "retryable": DEFAULT_RETRYABLE.get(err.code, True), "messageId": mid}})
        end: Wire = {"messageId": mid, "status": status}
        by = interrupted_by or ("error" if status == "interrupted" else None)
        if by:
            end["interruptedBy"] = by
        wire_usage: Wire | None = None
        if usage is not None:
            wire_usage = {"tokensIn": int(usage["tokensIn"]), **({"tokensCached": int(usage["tokensCached"])}
                                                                  if usage.get("tokensCached") else {}),
                          "tokensOut": int(usage["tokensOut"]), "costUsd": float(usage["costUsd"]), "energySpent": spent,
                          "firstTokenMs": float(first_token_ms if first_token_ms is not None else total_ms),
                          "totalMs": float(total_ms)}
            end["usage"] = wire_usage
        if info.variant_id:
            end["variantId"] = info.variant_id
        kept = kept_citations(info.content, citations) if status in ("complete", "interrupted") and not scrub else []
        if kept:
            end["citations"] = kept
        events.append({"type": "turn.end", "payload": end})
        energy = await self.energy_now(info.character_id)
        if spent > 0 and energy is not None:
            ev: Wire = {"characterId": info.character_id, "current": energy["current"], "max": energy["max"],
                        "state": energy["state"], "spent": spent}
            if energy.get("fullAt"):
                ev["fullAt"] = energy["fullAt"]
            events.append({"type": "energy", "payload": ev})
        if status != "error":
            full = {"messageId": mid, **trace}
            prices = rt.prices
            full["model"] = {
                "id": (row or {}).get("model") or prices.chat.model, "provider": (row or {}).get("provider") or "",
                "pricePeriod": (row or {}).get("price_period") or rt.clock.pricing_period(),
                "latencyMs": {"firstToken": float(first_token_ms if first_token_ms is not None else total_ms),
                              "total": float(total_ms)},
                "tokensIn": int((usage or {}).get("tokensIn", 0)), "tokensOut": int((usage or {}).get("tokensOut", 0)),
                "costUsd": float((usage or {}).get("costUsd", 0.0))}
            if usage and usage.get("tokensCached"):
                full["model"]["tokensCached"] = int(usage["tokensCached"])
            if energy is not None:
                full["energy"] = {"characterId": info.character_id, "spent": spent, "remaining": energy["current"],
                                  "max": energy["max"]}
            routing: Wire = dict(spec.routing) if spec.routing else {"selected": info.character_id}
            if not spec.routing:
                if spec.forced_by:
                    routing["forcedBy"] = spec.forced_by
                if spec.skipped:
                    routing["skipped"] = spec.skipped
            full["routing"] = routing
            full["calls"] = [*spec.calls, *await ledger.calls_for_message(mid, since=since)]
            events.append({"type": "insight", "payload": {"messageId": mid, "trace": full}})
        meta = TraceMeta(engine=getattr(engine, "name", None), engine_version=getattr(engine, "version", None),
                         prompt_version=getattr(engine, "prompt_version", None))
        if scrub:
            await actor.emit_with(events, self._scrubber(actor, info))
        else:
            await actor.emit(*events, traces={mid: meta})
        info.closed = True
        if actor.current is info:
            actor.current = None
        if status == "complete" and spec.reactions and ctx is not None and actor.session["emotionMode"] != "user":
            self._reactions(actor, info, ctx)

    def _scrubber(self, actor: SessionActor, info: TurnInfo) -> Any:
        """D13: the blocked reply's text leaves the stored token events and the message (same transaction)."""
        from sqlalchemy import and_, select, update

        from horizon.db import tables as t

        msg = actor.state["messages"].get(info.message_id)
        if msg is not None:
            msg["content"] = ""
            if info.variant_id and msg.get("variants"):
                msg["variants"] = [{**v, "content": ""} if v["id"] == info.variant_id else v for v in msg["variants"]]

        async def scrub(tx: Any, _stamped: list[Wire]) -> None:
            E = t.session_events.c
            rows = (await tx.conn.execute(select(E.id, E.payload).where(and_(
                E.session_id == actor.sid, E.message_id == info.message_id, E.type == "token")))).all()
            for rid, payload in rows:
                if info.variant_id and payload.get("variantId") != info.variant_id:
                    continue
                await tx.conn.execute(update(t.session_events).where(E.id == rid).values(payload={**payload, "delta": ""}))
            from horizon.contract import mappers as mp

            if msg is not None:
                row = mp.message_row(msg)
                await tx.conn.execute(update(t.messages).where(t.messages.c.id == info.message_id).values(
                    content=row["content"], variants=row["variants"]))

        return scrub

    def _reactions(self, actor: SessionActor, info: TurnInfo, ctx: TurnContext) -> None:
        rt = self.rt
        est = rt.est_reply_points()
        listeners = [p.character_id for p in ctx.session.participants
                     if p.character_id != info.character_id and not p.muted
                     and float(p.energy.get("current", 0)) >= est]
        if not listeners:
            return
        reactions = rt.ai.reactions(self.key_set()).predict(ctx.session, info.message_id, info.character_id, listeners,
                                                            seed=f"{actor.seed}:{ctx.turn_index}")
        if not reactions:
            return

        async def play() -> None:
            start = to_ms(rt.clock.now())
            for r in sorted(reactions, key=lambda x: x.delay_ms):
                wait = start + r.delay_ms - to_ms(rt.clock.now())
                if wait > 0:
                    await rt.clock.sleep(wait / 1000)
                payload: Wire = {"messageId": info.message_id, "characterId": r.character_id, "emotion": r.emotion,
                                 "source": "classifier"}
                if r.p is not None:
                    payload["p"] = r.p
                await actor.emit({"type": "reaction", "payload": payload})

        actor.background("reactions", play())

    # ── Stop ──
    async def close_interrupted(self, actor: SessionActor, info: TurnInfo, *, by: str = "user") -> None:
        """Close a turn cut by Stop (design D3): the streamed text is kept, its spend (the estimate) stays."""
        if actor.current is info:
            actor.current = None
        if info.closed:
            return
        if not info.started:
            info.closed = True
            return
        spec = info.spec if isinstance(info.spec, TurnSpec) else TurnSpec(speaker=info.character_id)
        await self.finish(actor, info, spec, None, status="interrupted", err=None, trace=dict(info.trace),
                          citations=info.citations, first_token_ms=info.first_token_ms, t0=info.t0_ms,
                          started_iso=info.started_iso, engine=info.engine, interrupted_by=by)
