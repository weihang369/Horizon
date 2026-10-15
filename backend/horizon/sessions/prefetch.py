"""Prefetched openings (session-runtime design D5, "Discarded prefetches still drain energy"; D-77).

For the debate opening round and a group's everyone-answer, at most 2 turns run ahead of their speaking slot. A
prefetch allocates its message ID but announces nothing: its TurnEvents are buffered in memory with their clock times,
unsequenced. It holds an LLM slot and its reservation while it runs, and its paid call carries no message ID, so its
ledger row starts with `message_id` NULL (the drain still happens: the purpose is `reply`).

- **Release.** At its slot, the runner plays the buffer through the normal mapping (preamble, lazy `turn.start`,
  coalescing, trace): events before the first token at once, then at the original speaking pace. Its ledger rows are
  then linked to the message (`LedgerWriter.link_message`), so usage and `TurnTrace.calls` work unchanged.
- **Discard.** Stop, leave, a cap pause or the end of the run cancels a prefetch. Its rows keep `message_id` NULL and
  their drain stands; nothing from it reaches the session's events.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import TurnContext, TurnPlan
from horizon.ai.ports import Token, TurnEvent
from horizon.domain import vclock
from horizon.domain.ids import new_id
from horizon.domain.timeutil import to_ms
from horizon.domain.vclock import Inbox
from horizon.gateway.errors import ProviderError
from horizon.gateway.pipeline import RECORDED_SINK
from horizon.sessions.context import character_view, characters, reply_cap, session_context

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor
    from horizon.sessions.turn import TurnSpec

_END = object()


class Prefetch:
    def __init__(self, actor: SessionActor, spec: TurnSpec, ctx: TurnContext, message_id: str, engine: Any) -> None:
        self.actor = actor
        self.spec = spec
        self.ctx = ctx
        self.message_id = message_id
        self.engine = engine
        self.rows: list[str] = []
        self.error: ProviderError | None = None
        self.channel: Inbox[Any] = Inbox()
        self.task: asyncio.Task[None] | None = None
        self.planning: asyncio.Task[TurnPlan | None] | None = None   # M11: its own face plan (debate D8)
        self._planned: asyncio.Task[TurnPlan | None] | None = None   # M12: the plan with its deep work merged
        self.released = False

    @classmethod
    async def start(cls, actor: SessionActor, spec: TurnSpec,
                    plan_with: Callable[[], Coroutine[Any, Any, TurnPlan | None]] | None = None) -> Prefetch | None:
        """`plan_with` (M11, debate D8): a prefetched debate opening plans its own face when its prefetch starts, in
        the background; the prefetch waits for that plan (its `turn_plan` deadline) before it streams, so nothing on
        screen waits. Its plan decides retrieval, as an Everyone reply's does."""
        rt = actor.rt
        row = (await characters(rt, [spec.speaker])).get(spec.speaker)
        if row is None or row["deleted_at"] is not None:
            return None
        sctx = await session_context(rt, actor)
        plan = spec.plan
        if plan_with is not None:
            ctx = TurnContext(session=sctx, speaker=character_view(row), message_id=None, prompt=spec.prompt,
                              line=spec.line, turn_index=actor.mode.turn, max_tokens=reply_cap(rt, sctx),
                              direction_note=spec.direction_note, debate=spec.debate)
        elif plan is not None and plan.branch is not None:
            # M10 (group-watch D11, D18): an Everyone reply's plan came from the run's one cast plan; it decided
            # retrieval, so none runs here (the runner adds the plan's rows and call when the prefetch is released).
            # M12 (rag D15): a deep plan's work starts now; the prefetch waits for it before it streams
            from horizon.sessions.deep import attach

            await attach(actor, spec, sctx)
            ctx = TurnContext(session=sctx, speaker=character_view(row), message_id=None, prompt=spec.prompt,
                              line=spec.line, turn_index=actor.mode.turn, max_tokens=reply_cap(rt, sctx, plan),
                              direction_note=spec.direction_note, debate=spec.debate, plan=plan)
        else:
            from horizon.sessions.retrieve import retrieve

            got = await retrieve(rt, actor, sctx, spec.speaker, spec.prompt)   # M5: retrieved at prefetch time (D10)
            spec.calls.extend(got.calls)
            ctx = TurnContext(session=sctx, speaker=character_view(row), message_id=None, prompt=spec.prompt,
                              line=spec.line, turn_index=actor.mode.turn,
                              max_tokens=reply_cap(rt, sctx),   # after retrieval, as for a live turn (design D14)
                              direction_note=spec.direction_note, debate=spec.debate, knowledge=got.knowledge,
                              memory=got.memory, query=got.query)
        actor.mode.turn += 1
        engine = rt.ai.turn(rt.keys.status() == "set")
        pf = cls(actor, spec, ctx, new_id("msg"), engine)
        if plan_with is not None:
            pf.planning = rt.spawn(f"prefetch-plan:{actor.sid}", plan_with())
        pf.task = rt.spawn(f"prefetch:{actor.sid}", pf._produce())
        actor.prefetches.add(pf)
        return pf

    async def _produce(self) -> None:
        rt = self.actor.rt
        token = RECORDED_SINK.set(self.rows.append)
        try:
            await self.planned()
            async with rt.llm_slots.slot():
                agen: Any = self.engine.run(self.ctx)
                try:
                    async for ev in agen:
                        self.channel.put((float(to_ms(rt.clock.now())), ev))
                finally:
                    await agen.aclose()
        except ProviderError as e:
            self.error = e
        finally:
            RECORDED_SINK.reset(token)
            self.channel.put(_END)

    async def planned(self) -> TurnPlan | None:
        """The prefetch's own plan once made (at most its `turn_plan` deadline), put into its context. M12 (rag D15): a
        deep plan's work (started with the prefetch, or now for an opening whose own plan went deep) is merged in, so
        the prefetch streams with its passages. The producer and the runner both ask; one task does the work."""
        if self._planned is None:
            self._planned = self.actor.rt.spawn(f"prefetch-planned:{self.actor.sid}", self._plan_and_merge())
        done: TurnPlan | None = await vclock.join(self._planned)
        return done

    async def _plan_and_merge(self) -> TurnPlan | None:
        plan = self.ctx.plan
        if self.planning is not None:
            plan = await vclock.join(self.planning)
            self.planning = None
            if plan is not None and self.ctx.plan is None:
                self.ctx = self.ctx.model_copy(update={
                    "plan": plan, "max_tokens": reply_cap(self.actor.rt, self.ctx.session, plan)})
        if plan is not None and plan.branch == "deep" and plan.knowledge_outcome is None:
            from horizon.sessions.deep import attach

            if self.spec.deep is None:
                self.spec.plan = plan
                await attach(self.actor, self.spec, self.ctx.session)
            if self.spec.deep is not None:
                plan = await self._merge(plan)
        return plan

    async def _merge(self, plan: TurnPlan) -> TurnPlan:
        call = self.spec.deep
        try:
            res = await call.result()
        except asyncio.CancelledError:
            call.cancel()
            raise
        self.rows.extend(call.rows)   # linked to the message when the prefetch is released
        merged = plan.with_deep(res).model_copy(update={"branch": "deep"}) if res is not None \
            else plan.model_copy(update={"branch": "quick"})
        self.ctx = self.ctx.model_copy(update={
            "plan": merged, "max_tokens": reply_cap(self.actor.rt, self.ctx.session, merged),
            "knowledge": list(merged.knowledge) if merged.branch == "deep" else [],
            "query": merged.query if merged.branch == "deep" else None})
        return merged

    async def replay(self) -> AsyncIterator[TurnEvent]:
        """The buffered events at speaking pace: everything before the first token at once, then the original gaps."""
        self.released = True
        clock = self.actor.rt.clock
        first: float | None = None
        start = 0.0
        while True:
            item = await self.channel.get()
            if item is _END:
                if self.error is not None:
                    raise self.error
                return
            at, ev = item
            if isinstance(ev, Token) and first is None:
                first, start = at, float(to_ms(clock.now()))
            if first is not None:
                wait = (at - first) - (to_ms(clock.now()) - start)
                if wait > 0:
                    await clock.sleep(wait / 1000)
            yield ev

    async def link(self) -> None:
        """The prefetch was released as its message: link its ledger rows (one-row updates)."""
        if self.task is not None and not self.task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task
        for row_id in self.rows:
            await self.actor.rt.ledger.link_message(row_id, self.message_id)
        self.actor.prefetches.discard(self)

    async def discard(self) -> None:
        """Cancel it (D-77): its rows keep no message ID, and their drain stands."""
        self.actor.prefetches.discard(self)
        if self.spec.deep is not None:
            self.spec.deep.cancel()   # M12: its Jev calls are recorded `cancelled`
        if self._planned is not None and not self._planned.done():
            self._planned.cancel()
        if self.planning is not None and not self.planning.done():
            self.planning.cancel()   # its Jev call is recorded `cancelled` (M9 D8)
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.planning
        if self.task is not None and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task
        await self.actor.rt.gateway.drain_background()
