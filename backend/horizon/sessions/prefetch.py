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
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import Token, TurnEvent
from horizon.domain.ids import new_id
from horizon.domain.timeutil import to_ms
from horizon.domain.vclock import Inbox
from horizon.gateway.errors import ProviderError
from horizon.gateway.pipeline import RECORDED_SINK
from horizon.sessions.context import character_view, characters, session_context

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
        self.released = False

    @classmethod
    async def start(cls, actor: SessionActor, spec: TurnSpec) -> Prefetch | None:
        rt = actor.rt
        row = (await characters(rt, [spec.speaker])).get(spec.speaker)
        if row is None or row["deleted_at"] is not None:
            return None
        sctx = await session_context(rt, actor)
        caps = rt.runtime_cfg.runtime.reply_max_tokens
        cfg = sctx.config or {}
        from horizon.sessions.retrieve import retrieve

        got = await retrieve(rt, actor, sctx, spec.speaker, spec.prompt)   # M5: retrieved at prefetch time (D10)
        spec.calls.extend(got.calls)
        ctx = TurnContext(session=sctx, speaker=character_view(row), message_id=None, prompt=spec.prompt, line=spec.line,
                          turn_index=actor.mode.turn,
                          max_tokens=caps.for_mode(sctx.mode, str(cfg.get("turnLength")) if sctx.mode == "debate" else None),
                          direction_note=spec.direction_note, debate=spec.debate, knowledge=got.knowledge,
                          memory=got.memory, query=got.query)
        actor.mode.turn += 1
        engine = rt.ai.turn(rt.keys.status() == "set")
        pf = cls(actor, spec, ctx, new_id("msg"), engine)
        pf.task = rt.spawn(f"prefetch:{actor.sid}", pf._produce())
        actor.prefetches.add(pf)
        return pf

    async def _produce(self) -> None:
        rt = self.actor.rt
        token = RECORDED_SINK.set(self.rows.append)
        try:
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
        if self.task is not None and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task
        await self.actor.rt.gateway.drain_background()
