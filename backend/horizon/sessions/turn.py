"""TurnRunner (session-runtime design D5; doc 01 §4.2 turn order).

One character turn:
1. the speaker is chosen by the mode or the router;
2. the energy gate (below `estReplyPoints` for the period: the caller's asleep/skip path, no model call);
3. the `messageId` (or `variantId`) is allocated before any model call;
4. the preamble: `turn.next`, then `turn.thinking` after `thinkingMs`;
4b. (M5) retrieval in the speaker's scope (`sessions/retrieve.py`): it waits at most `retrieval.queryEmbedWaitMs` for
   the user message's query embedding (started at `send`), then freezes the hits into the `TurnContext`;
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
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from horizon.ai.contexts import DebateMeta, LineHint, PlanRequest, SessionContext, TurnContext, TurnPlan
from horizon.ai.ports import OWNED_TRACE_KEYS, CitationMap, Emotion, Token, TracePatch
from horizon.ai.scripted.ports import PLANNED_FACE
from horizon.api.errors import DEFAULT_RETRYABLE
from horizon.domain import vclock
from horizon.domain.energy import points_for_cost
from horizon.domain.ids import new_id
from horizon.domain.timeutil import to_ms
from horizon.gateway.errors import ProviderError
from horizon.sessions.actor import SessionActor, TurnInfo
from horizon.sessions.after_turn import start_face_check, start_reactions
from horizon.sessions.coalesce import Coalescer
from horizon.sessions.context import (
    characters,
    document_titles,
    energy_of,
    reply_cap,
    session_context,
    speaker_view,
)
from horizon.sessions.prefetch import Prefetch
from horizon.sessions.retrieve import retrieve
from horizon.sessions.summary import check_summary
from horizon.sessions.system1 import section as system1_section
from horizon.sessions.verbatim import VerbatimEngine
from horizon.sessions.writer import TraceMeta

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.sessions")

Wire = dict[str, Any]
STATUS_BY_CODE = {"content_refused": "error"}
REGENERATE_SUFFIX = " (again)"   # regenerate's prompt marker (one_on_one.regenerate); the plan reads the plain line
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
    system1: dict[str, Any] | None = None           # rev 1.4: the turn's System 1 section (the route row, D25)
    reactions: bool = True
    debate: DebateMeta | None = None
    direction_note: str | None = None
    plan: TurnPlan | None = None                    # M10 (group-watch D3): a plan the mode already made for this turn
    deep: Any = None                                # M12 (rag D15): the speaker's deep work, started ahead of the turn
    # M10 (doc 07 G2, doc 11 S5; group-watch D8): called at the stream's end of a reply that streamed without an error;
    # it starts the follow plan and returns its handle (or None), which the outcome carries back to the mode
    follow: Callable[[TurnInfo], Awaitable[Any]] | None = None
    # M10 (doc 07 G5; group-watch D12): the reply epoch the job captured when queued; `turn.next` is written only while
    # it is current (None: never superseded, e.g. a watch scene turn)
    epoch: int | None = None


@dataclass
class TurnOutcome:
    message_id: str | None
    status: str          # complete | interrupted | error | refused | asleep | missing | superseded
    follow: Any = None   # M10: the follow plan's handle, started at the stream's end (D8)
    ended_at: datetime | None = None   # when turn.end was appended: the follow plan's deadline counts from here


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
        # M9 (turn-plan-emotion D6): an `agent` 1:1 turn is planned from here, so Jev overlaps the thinking delay
        # M10 (group-watch D3): a group or watch turn arrives with its plan already made by the mode
        planning = (rt.spawn(f"plan:{actor.sid}", self._plan(actor, spec, row, mid))
                    if prefetch is None and not spec.line.verbatim and actor.mode_name == "one_on_one"
                    and spec.plan is None else None)
        if spec.plan is not None and spec.plan.branch == "deep" and spec.deep is None and prefetch is None:
            from horizon.sessions.deep import attach  # M12 (rag D15): anything a mode didn't start earlier

            await attach(actor, spec)
        try:
            if spec.epoch is None:
                await actor.emit({"type": "turn.next", "payload": nxt})
            elif not await actor.emit_checked({"type": "turn.next", "payload": nxt},
                                              lambda _s: spec.epoch == actor.reply_epoch):
                info.closed = True   # G5: superseded before it announced; nothing was written
                if prefetch is not None:
                    await prefetch.discard()
                if spec.deep is not None:
                    spec.deep.cancel()   # M12: its Jev calls are recorded `cancelled`
                return TurnOutcome(None, "superseded")
            await rt.clock.sleep(rt.runtime_cfg.timing.thinking_ms / 1000)
            await actor.emit({"type": "turn.thinking", "payload": {"characterId": spec.speaker}})
            if prefetch is not None:
                await prefetch.planned()   # M11: a prefetched opening's own plan (debate D8), at most its deadline
                info.ctx = prefetch.ctx
                pplan = prefetch.ctx.plan
                if pplan is not None:   # M10 (D11): a prefetched Everyone reply carries its plan's rows and call
                    spec.calls.extend(pplan.calls)
                    spec.system1 = system1_section(spec.system1, pplan.rows, seed=pplan.seed)
                return await self._stream(actor, spec, info, prefetch.ctx, t0, started_iso, prefetch=prefetch)
            plan: TurnPlan | None = spec.plan
            if planning is not None:
                sctx, plan = await vclock.join(planning)   # the worker's token is given up while Jev thinks
            else:
                sctx = await session_context(rt, actor)   # M8: no summary work here (docs/ai/05 X2: after turn.end)
            if plan is not None and spec.deep is not None:   # M12 (rag D15): deep work started ahead of the turn
                merged = await self._deep(actor, spec, plan, mid, started_iso)
                if merged is None:   # a newer user message arrived during the deep work (G5): no reply
                    info.closed = True
                    return TurnOutcome(None, "superseded")
                plan = merged
            if plan is not None and plan.rewrite and plan.rewrite_for:   # M12 (D19): its own small write
                await self._store_rewrite(plan.rewrite_for, spec.speaker, plan.rewrite)
            if spec.line.verbatim:   # M8 (docs/ai/04 P9, persona-context D19): no retrieval, no model call
                ctx = TurnContext(session=sctx, speaker=await speaker_view(rt, actor, row), message_id=mid, variant_id=vid,
                                  prompt=spec.prompt, line=spec.line, turn_index=actor.mode.turn, max_tokens=1)
            elif plan is not None and plan.branch is not None:   # D9: the plan decided retrieval (M9: always quick)
                spec.calls.extend(plan.calls)
                spec.system1 = system1_section(spec.system1, plan.rows, seed=plan.seed)
                ctx = TurnContext(session=sctx, speaker=await speaker_view(rt, actor, row), message_id=mid, variant_id=vid,
                                  prompt=spec.prompt, line=spec.line, turn_index=actor.mode.turn,
                                  max_tokens=reply_cap(rt, sctx, plan), direction_note=spec.direction_note,
                                  debate=spec.debate, plan=plan,
                                  # M12 (ai-ports): an agent reply's passages come only from its frozen plan
                                  knowledge=list(plan.knowledge) if plan.branch == "deep" else [],
                                  query=plan.query if plan.branch == "deep" else None)
            else:
                if plan is not None:   # a planner that leaves retrieval alone (the scripted one): its rows only
                    spec.calls.extend(plan.calls)
                    spec.system1 = system1_section(spec.system1, plan.rows, seed=plan.seed)
                got = await retrieve(rt, actor, sctx, spec.speaker, spec.prompt)   # M5 design D10: the speaker's scope
                spec.calls.extend(got.calls)
                ctx = TurnContext(session=sctx, speaker=await speaker_view(rt, actor, row), message_id=mid, variant_id=vid,
                                  prompt=spec.prompt, line=spec.line, turn_index=actor.mode.turn,
                                  max_tokens=reply_cap(rt, sctx),   # after retrieval and the (M9) plan: design D14
                                  direction_note=spec.direction_note, debate=spec.debate, knowledge=got.knowledge,
                                  memory=got.memory, query=got.query)
            actor.mode.turn += 1
            info.ctx = ctx
            return await self._stream(actor, spec, info, ctx, t0, started_iso)
        except asyncio.CancelledError:
            if not info.started:   # cut before turn.start (clear() during the plan or the preamble): nothing to close
                info.closed = True
            raise
        finally:
            if planning is not None and not planning.done():   # D8: Stop during the plan leaves nothing running
                planning.cancel()
            if actor.current is info and info.closed:
                actor.current = None

    async def _deep(self, actor: SessionActor, spec: TurnSpec, plan: TurnPlan, mid: str,
                    started_iso: str = "") -> TurnPlan | None:
        """M12 (rag D15): wait for the deep work started ahead, link its ledger rows to this reply, and merge it into
        the plan; a bug inside gave no result, so the turn is quick with a `fallback` row. Cancelling the turn cancels
        the work (its Jev calls are recorded `cancelled`), and so does a newer user message (G5): None, no reply."""
        from horizon.ai.agent.deep import PASSAGE, PURPOSE

        call = spec.deep
        try:
            if spec.epoch is not None and not await vclock.wait_unless(call.task, actor.superseded(spec.epoch)):
                call.cancel()
                return None
            res = await call.result()
        except asyncio.CancelledError:
            call.cancel()
            raise
        for row_id in list(call.rows):
            await self.rt.ledger.link_message(row_id, mid)
        # the rows recorded before this turn started (watch's plan made ahead) aren't found by the turn-end listing
        spec.calls.extend(await self.rt.ledger.calls_for_rows(list(call.rows), before=started_iso or None))
        if res is None:
            row = {"purpose": PURPOSE, "id": PASSAGE, "answer": "error", "compared": [], "result": "fallback",
                   "action": "quick reply"}
            return plan.model_copy(update={"branch": "quick", "rows": [*plan.rows, row], "calls": [*plan.calls, {
                "purpose": PURPOSE, "model": self.rt.prices.decision.model, "costUsd": 0.0, "latencyMs": 0.0,
                "fallback": True}]})
        merged: TurnPlan = plan.with_deep(res).model_copy(update={"branch": "deep"})
        return merged

    async def _store_rewrite(self, message_id: str, speaker: str, text: str) -> None:
        from horizon.services.ai_meta import store_rewrite

        try:
            await store_rewrite(self.rt, message_id, speaker, text)
        except asyncio.CancelledError:
            raise
        except Exception:   # a derived row: losing it costs one more rewrite on regenerate, never the reply
            log.exception("storing the rewrite for %s failed", message_id)

    async def _plan(self, actor: SessionActor, spec: TurnSpec, row: Any, mid: str) -> tuple[SessionContext, TurnPlan | None]:
        """The turn's context and its plan (D6): started before `turn.next`, so the deadline counts from here. The
        base face is the current face in AUTO, and the speaker's last AI-chosen face under MANUAL (docs/ai/06 E2)."""
        rt = self.rt
        started = rt.clock.now()
        sctx = await session_context(rt, actor)
        planner = rt.ai.planner(self.key_set())
        manual = actor.session.get("emotionMode") == "user"
        if manual:
            mine = [m for m in actor.state["messages"].values()
                    if m["author"].get("characterId") == spec.speaker and m.get("emotion")]
            base = str(max(mine, key=lambda m: m["seq"])["emotion"]) if mine else "neutral"
        else:
            base = next((p.emotion for p in sctx.participants if p.character_id == spec.speaker), "neutral")
        kind: Literal["reply", "greeting"] = "greeting" if spec.line.kind == "greeting" else "reply"
        # M12 (rag D6): the gate's titles, read only for a planner that decides retrieval (agent) and a reply
        docs = await document_titles(rt, sctx.world.id, [spec.speaker]) \
            if kind == "reply" and getattr(planner, "decides_retrieval", False) else {}
        stored = None
        if docs:   # M12 (rag D19): a rewrite stored for this message and speaker is reused (regenerate)
            from horizon.ai.agent.planner import answered_message
            from horizon.services.ai_meta import stored_rewrite

            stored = await stored_rewrite(rt, answered_message(sctx)[0], spec.speaker)
        # M13 (memory D22): the speaker's view carries its memory list, so the 1:1 rewrite (and the deep request built
        # from this cast) share the reply's system message 1 byte for byte
        # M13 (memory D26, D34): whether there is something earlier to search, and what recall would search
        recall: dict[str, Any] = {}
        if kind == "reply" and getattr(planner, "decides_retrieval", False):
            from horizon.sessions.context import recall_scope, recallable

            recall = {"recallable": await recallable(rt, actor, [spec.speaker]),
                      **await recall_scope(rt, actor, spec.speaker)}
        req = PlanRequest(session=sctx, speaker_id=spec.speaker, cast=[await speaker_view(rt, actor, row)], message_id=mid,
                          kind=kind, latest=spec.prompt.removesuffix(REGENERATE_SUFFIX), turn_index=actor.mode.turn,
                          base_face=base, manual=manual, started_at=started, documents=docs, stored_rewrite=stored,
                          **recall)
        return sctx, await planner.plan(req)

    async def _stream(self, actor: SessionActor, spec: TurnSpec, info: TurnInfo, ctx: TurnContext, t0: float,
                      started_iso: str, *, prefetch: Prefetch | None = None) -> TurnOutcome:
        rt = self.rt
        knobs = rt.runtime_cfg.runtime
        clock = rt.clock
        verbatim = prefetch is None and ctx.line.verbatim
        engine = info.engine = (prefetch.engine if prefetch is not None
                                else VerbatimEngine(rt.runtime_cfg.timing, lambda: rt.clock) if verbatim
                                else rt.ai.turn(self.key_set()))
        co = Coalescer(knobs.coalesce_max_chars, knobs.coalesce_max_ms, lambda: float(to_ms(clock.now())))
        timer: asyncio.Task[None] | None = None
        writing = False   # the timer is past its sleep: its delta is taken and its token write must land
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
            nonlocal writing
            await clock.sleep(co.due_in_ms() / 1000)
            writing = True
            await flush()

        def arm() -> None:
            nonlocal timer, writing
            if co.pending and (timer is None or timer.done()):
                writing = False
                timer = rt.spawn(f"coalesce:{actor.sid}", trailing())

        async def settle_timer() -> None:
            nonlocal timer
            if timer is not None and not timer.done():
                # a sleeping timer is cancelled; a writing one is waited for. Cancelling it while its write waited for
                # the write lock lost its delta from the stored reply (docs/ai/checks/m11.md 10.1: debates, where
                # reactions, the plan and host lines all write, lost a first word or a last phrase)
                if not writing:
                    timer.cancel()
                # not `await timer`: a Stop cancelling this turn would pass its cancel on to the timer, a second one
                # landing in the timer's token write (docs/ai/checks/m9.md 9.6)
                await asyncio.wait((timer,))
                if not timer.cancelled() and (failed := timer.exception()) is not None:
                    raise failed   # as `await timer` did: a failed token write fails the turn
            timer = None

        slot: Any = rt.llm_slots.slot() if prefetch is None and not verbatim else contextlib.nullcontext()
        try:
            async with slot:
                agen: Any = prefetch.replay() if prefetch is not None else engine.run(ctx)
                try:
                    async for ev in agen:
                        if not info.started:
                            if isinstance(ev, Emotion):   # D14: turn.start and the face in one write
                                await self._start(actor, spec, info, emotion=self._emotion_event(info, ev))
                                continue
                            if not isinstance(ev, CitationMap | TracePatch):   # no wire event of their own
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
                            await actor.emit(self._emotion_event(info, ev))
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
            if timer is not None and not timer.cancelling():   # settle_timer may have cancelled it already
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
        follow: Any = None
        if spec.follow is not None and err is None:   # S5: the follow plan starts at the stream's end
            try:
                follow = await spec.follow(info)
            except Exception:
                log.exception("the follow plan could not start after %s (no second reply)", info.message_id)
        try:
            status = await self.finish(actor, info, spec, ctx, status=status, err=err, trace=trace,
                                       citations=citations, first_token_ms=first_token_ms, t0=t0,
                                       started_iso=started_iso, engine=engine)
        except BaseException:
            if follow is not None:
                follow.cancel()
            raise
        if follow is not None and status != "complete":   # a blocked reply (M14's check) has no follow plan
            follow.cancel()
            follow = None
        return TurnOutcome(info.message_id, status, follow=follow, ended_at=rt.clock.now())

    @staticmethod
    def _emotion_event(info: TurnInfo, ev: Emotion) -> Wire:
        info.face = ev.emotion
        return {"type": "emotion", "payload": {"messageId": info.message_id, "characterId": info.character_id,
                                               "emotion": ev.emotion, "source": ev.source}}

    async def _start(self, actor: SessionActor, spec: TurnSpec, info: TurnInfo, *, emotion: Wire | None = None) -> None:
        """`turn.start`, and with it the first face when the engine's first event is one (docs/ai/06 E2; D14): one
        `actor.emit`, so nothing (a pending reaction) lands between them."""
        payload: Wire = {"messageId": info.message_id, "author": {"type": "character", "characterId": info.character_id}}
        if info.variant_id:
            payload["variantId"] = info.variant_id
        elif spec.message:
            payload["message"] = spec.message
        info.started = True
        info.auto = actor.session.get("emotionMode") != "user"   # the face check reads the mode at turn.start (W2)
        await actor.emit({"type": "turn.start", "payload": payload}, *([emotion] if emotion is not None else []))

    # ── the end of a turn ──
    async def finish(self, actor: SessionActor, info: TurnInfo, spec: TurnSpec, ctx: TurnContext | None, *, status: str,
                     err: ProviderError | None, trace: dict[str, Any], citations: list[dict[str, Any]] | None,
                     first_token_ms: float | None, t0: float, started_iso: str, engine: Any = None,
                     interrupted_by: str | None = None) -> str:
        """Close the turn; returns its final status (a blocked reply ends `error`)."""
        rt = self.rt
        await rt.gateway.drain_background()   # a cut or stopped stream records its estimate in a shielded task
        mid = info.message_id
        total_ms = to_ms(rt.clock.now()) - t0
        scrub = False
        verbatim = getattr(engine, "name", None) == VerbatimEngine.name   # P9: the approved line, no model call
        if status == "complete" and ctx is not None and not verbatim:
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
                                                                  if usage.get("tokensCached") is not None else {}),
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
            if not verbatim:   # P9: a verbatim line made no model call, so Insight claims none
                full["model"] = {
                    "id": (row or {}).get("model") or prices.chat.model, "provider": (row or {}).get("provider") or "",
                    "pricePeriod": (row or {}).get("price_period") or rt.clock.pricing_period(),
                    "latencyMs": {"firstToken": float(first_token_ms if first_token_ms is not None else total_ms),
                                  "total": float(total_ms)},
                    "tokensIn": int((usage or {}).get("tokensIn", 0)),
                    "tokensOut": int((usage or {}).get("tokensOut", 0)),
                    "costUsd": float((usage or {}).get("costUsd", 0.0))}
                if usage and usage.get("tokensCached") is not None:
                    full["model"]["tokensCached"] = int(usage["tokensCached"])
            if energy is not None and not verbatim:
                full["energy"] = {"characterId": info.character_id, "spent": spent, "remaining": energy["current"],
                                  "max": energy["max"]}
            routing: Wire = dict(spec.routing) if spec.routing else {"selected": info.character_id}
            if not spec.routing:
                if spec.forced_by:
                    routing["forcedBy"] = spec.forced_by
                if spec.skipped:
                    routing["skipped"] = spec.skipped
            full["routing"] = routing
            full["calls"] = [*spec.calls, *await ledger.calls_for_message(mid, since=since), *info.system1_calls]
            plan = ctx.plan if ctx is not None else None
            if plan is not None and plan.graph_path:   # A12: the plan graph's node path, written once (D3)
                full["graph"] = {"path": list(plan.graph_path)}
            if spec.system1 or info.system1:   # D24: rows appended mid-stream merge by key, never replace
                base = dict(spec.system1 or {})
                if base.get("questions"):   # M9 D25: the scripted emotion row's answer is the face the reply showed
                    base["questions"] = [{**q, "answer": info.face or "neutral"}
                                         if q.get("purpose") == "turn_plan" and q.get("answer") == PLANNED_FACE else q
                                         for q in base["questions"]]
                full["system1"] = system1_section(base, info.system1, seed=base.get("seed"))
            events.append({"type": "insight", "payload": {"messageId": mid, "trace": full}})
        label = getattr(engine, "prompt_version_for", None)   # M10 D10: the label follows this turn's bytes
        meta = TraceMeta(engine=getattr(engine, "name", None), engine_version=getattr(engine, "version", None),
                         prompt_version=label(info.ctx) if label is not None else getattr(engine, "prompt_version", None))
        if scrub:
            await actor.emit_with(events, self._scrubber(actor, info))
        else:
            await actor.emit(*events, traces={mid: meta})
        info.closed = True
        if actor.current is info:
            actor.current = None
        if rt.capture.enabled and ctx is not None and not verbatim:   # ai-foundation D27: the turn row (queued)
            rt.capture.on_turn(world_id=actor.session.get("worldId"), session_id=actor.sid,
                               character_id=info.character_id, message_id=mid, request=ctx.model_dump(mode="json"),
                               response={"plan": ctx.plan.model_dump(mode="json") if ctx.plan is not None else None,
                                         "status": status,
                                         "routingFallback": (spec.routing or {}).get("reason") == "fallback",
                                         "deciderFallback": any(bool(c.get("fallback")) for c in spec.calls)})
        if status == "complete" and spec.reactions and ctx is not None and actor.session["emotionMode"] != "user":
            start_reactions(rt, actor, info, ctx, key_set=self.key_set())   # M9 D18-D20: predicted inside the task
        if status == "complete" and not scrub and ctx is not None and not verbatim:   # M9 D24 (doc 13 W2)
            start_face_check(rt, actor, info, ctx, key_set=self.key_set())
        if status != "error":   # M8 (docs/ai/05 X2, X3): fold the window after the reply, never before it
            check_summary(actor)
        return status

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
            await self._forget_derived(tx.conn, actor, info.message_id)
            from horizon.services.memory.index import follow_blocked

            await follow_blocked(tx.conn, info.message_id)   # M13 (memory D29): its indexed line goes too

        return scrub

    async def _forget_derived(self, conn: Any, actor: SessionActor, message_id: str) -> None:
        """A blocked reply leaves no memory (session-runtime "A blocked reply is scrubbed", closes M3 OQ-8). M13 (memory
        D20): the still-current memories sourced from it are undone, in the scrub's transaction, and what they
        superseded is current again, so a blocked new variant can't destroy older memories that were only superseded."""
        from horizon.services.memory.undo import undo_derived

        await undo_derived(self.rt, conn, message_id)

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
