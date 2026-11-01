"""LiveSessionManager (session-runtime design D1, D3, D7): the open actors, "who is generating", and the cap fan-out.

- `get(sid)` returns the session's actor, creating it from storage under a lock (seq counters from `MAX(seq)`), so two
  racing requests share one actor.
- One streaming session at a time: `active_other(sid)` names another actor that is generating (a turn under way and not
  held), for the 409 `conflict` with `details.activeSessionId`.
- The daily cap (STATE-06, OQ-11): when a recorded call crosses the cap, or a call is refused by it, every active live
  session pauses with `daily_budget` (a reply already streaming finishes). The cap then counts as reached for that day
  and cap until spend is below it again, which a later day or a raised cap allows, or until money held for calls in
  flight then is released (`cap_blocked`).
- `budget.warning` for a call made by a session is mirrored onto that session's stream.
- Pass 2 J3-07 (the user's choice): a watch or debate whose stream has had no subscriber for `memory.leaveGraceMs`
  (a closed tab, a crashed browser) pauses with `navigated_away`, as leaving its screen does, so it stops spending.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from horizon.domain import budget
from horizon.events.bus import session_channel
from horizon.gateway.context import CallContext
from horizon.gateway.pipeline import RecordResult
from horizon.sessions.actor import SessionActor
from horizon.sessions.turn import TurnRunner
from horizon.sessions.writer import EventWriter

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.sessions")
STREAM_PREFIX = "session:"


class LiveSessionManager:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.actors: dict[str, SessionActor] = {}
        self.lock = asyncio.Lock()
        self.lock_create = asyncio.Lock()
        self.runner = TurnRunner(rt)
        # (local day, cap, the refused call's estimate) of the last cap refusal
        self._refused: tuple[str, float, float] | None = None
        self._unwatched: dict[str, asyncio.Task[None]] = {}

    # ── actors ──
    async def get(self, sid: str) -> SessionActor:
        actor = self.actors.get(sid)
        if actor is not None and not actor.stopped:
            return actor
        async with self.lock:
            actor = self.actors.get(sid)
            if actor is not None and not actor.stopped:
                return actor
            writer = await EventWriter.load(self.rt.db, sid, self.rt.now_iso)
            actor = SessionActor(self.rt, self, writer)
            self.actors[sid] = actor
            actor.start()
            runs = self.rt._memory_runs
            if runs is not None and runs.started:   # M13 (memory D7 trigger 5): a shared character's other sitting
                self.rt.spawn(f"memory_opened:{sid}", runs.opened(sid))
            return actor

    # ── a scene nobody watches (pass 2 J3-07) ──
    def watch_streams(self) -> None:
        self.rt.bus.watch(STREAM_PREFIX, self._on_first, self._on_drained)

    def _on_first(self, channel: str) -> None:
        g = self._unwatched.pop(channel[len(STREAM_PREFIX):], None)
        if g is not None:
            g.cancel()

    def _on_drained(self, channel: str) -> None:
        sid = channel[len(STREAM_PREFIX):]
        actor = self.peek(sid)
        if actor is None or actor.session["mode"] not in ("watch", "debate") or sid in self._unwatched:
            return
        self._unwatched[sid] = self.rt.spawn(f"unwatched:{sid}", self._pause_unwatched(sid))

    async def _pause_unwatched(self, sid: str) -> None:
        from horizon.sessions.lifecycle import leave

        try:
            await self.rt.clock.sleep(float(self.rt.runtime_cfg.runtime.memory.leave_grace_ms) / 1000)
        finally:
            if self._unwatched.get(sid) is asyncio.current_task():
                del self._unwatched[sid]
        if self.peek(sid) is None or self.rt.bus.subscriber_count(session_channel(sid)) > 0:
            return
        try:
            await leave(self.rt, sid)   # an active non-seed session only; a streaming reply finishes
        except Exception:
            log.exception("pausing the unwatched session %s failed", sid)

    def peek(self, sid: str) -> SessionActor | None:
        a = self.actors.get(sid)
        return a if a is not None and not a.stopped else None

    async def release(self, sid: str, actor: SessionActor | None = None) -> None:
        """Stop an actor and forget it (idle release, delete, leave/end). The next command re-creates it from storage."""
        async with self.lock:
            current = self.actors.get(sid)
            if current is None or (actor is not None and current is not actor):
                return
            del self.actors[sid]
        await current.stop()

    def generating_with(self, character_id: str) -> str | None:
        """The live session in which this character is a participant while a turn is under way (delete → 409)."""
        for sid, a in self.actors.items():
            if not a.stopped and a.generating and any(p["characterId"] == character_id for p in a.session["participants"]):
                return sid
        return None

    def active_other(self, sid: str | None) -> str | None:
        for other, a in self.actors.items():
            if other != sid and not a.stopped and a.generating:
                return other
        return None

    async def shutdown(self) -> None:
        for g in list(self._unwatched.values()):
            g.cancel()
        self._unwatched.clear()
        actors = list(self.actors.values())
        self.actors.clear()
        for a in actors:
            with contextlib.suppress(Exception):
                await a.stop()

    # ── the daily cap ──
    def _today(self) -> str:
        c = self.rt.clock
        return c.calendar.today(c.now()).isoformat()

    async def cap_blocked(self) -> bool:
        """Today's spend has reached the cap, or a call was refused by this cap today (spend can't fit any more)."""
        cap = self.rt.caps().daily_cap_usd
        if self._refused is not None and self._refused[:2] != (self._today(), cap):
            self._refused = None
        spent = await self.rt.gateway.ledger.spent_today()
        # Pass 2 J1-01: the block lasts while the refused call still wouldn't fit. A refusal caused by money held then
        # (a running job's estimate) ends when that money is released, not at midnight.
        if self._refused is not None and not budget.exceeds_daily(spent, self.rt.book.total(), self._refused[2], cap):
            self._refused = None
        if self._refused is not None:
            return True
        return spent >= cap - 1e-9

    def on_spend(self, ctx: CallContext, res: RecordResult) -> None:
        """Gateway hook after every recorded call: crossing the daily cap pauses the live sessions, unless the call was
        background memory work (M13, memory D11): then the next reply meets the cap itself and pauses there."""
        if not ctx.pauses_sessions:
            return
        cap = self.rt.caps().daily_cap_usd
        if res.spent_before < cap - 1e-9 <= res.spent_after:
            self.pause_all_for_cap()

    def on_budget(self, event: dict[str, Any], ctx: CallContext, estimate: float = 0.0) -> None:
        """Gateway hook for budget events: a refusal pauses everything; a session's warning goes on its stream."""
        if event["type"] == "budget.reached" and event.get("scope") == "daily":
            self._refused = (self._today(), self.rt.caps().daily_cap_usd, estimate)
            self.pause_all_for_cap()
        elif event["type"] == "budget.warning" and event.get("scope") == "daily" and ctx.session_id:
            actor = self.peek(ctx.session_id)
            if actor is not None:
                payload = {k: event[k] for k in ("scope", "spentUsd", "capUsd")}

                async def mirror(a: SessionActor = actor) -> None:
                    await a.emit({"type": "budget.warning", "payload": payload})

                actor.post(mirror)

    def pause_all_for_cap(self) -> None:
        for actor in list(self.actors.values()):
            if actor.stopped:
                continue

            async def pause(a: SessionActor = actor) -> None:
                if a.session["status"] != "active":
                    return
                await a.clear(keep_current=True)
                a.held = True
                await a.emit({"type": "session.paused", "payload": {"reason": "daily_budget"}})

            actor.post(pause)
