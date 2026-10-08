"""SessionActor (session-runtime design D3): one per open session; every write to the session's rows goes through it.

Two layers, mirroring the MockClient's `enqueue/pump` (`mock/engines/host.ts`):
- **The inbox.** Commands run one at a time inside the actor task: preconditions, then the immediate events (a user
  `message`, a settings change), then work queued for the turn worker. The caller's future resolves with the result
  (202 for a route) or the rejection. Stop, pause, leave and end run here at once; they never queue behind a turn.
- **The turn queue.** Jobs run one at a time in the turn worker task (FIFO, with front insertion for steering). A Stop
  cancels the worker (and with it the turn), and a fresh worker takes over. `after(ms, fn)` timers (debate pauses,
  watch pace, greeting delays) run beside the queue and are cancelled by `clear()`.

All appends take the actor's write lock, so turn tasks, reaction tasks and commands never interleave their events.
Every task is started through `rt.spawn`, so virtual-time advances wait for it (D2).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from horizon.domain.timeutil import to_ms
from horizon.domain.vclock import Inbox
from horizon.events.bus import session_channel
from horizon.sessions.writer import EventWriter, TraceMeta

if TYPE_CHECKING:
    from horizon.runtime import Runtime
    from horizon.sessions.manager import LiveSessionManager

log = logging.getLogger("horizon.sessions")

Wire = dict[str, Any]
Job = Callable[[], Awaitable[None]]
Handler = Callable[[], Awaitable[Any]]


@dataclass
class Envelope:
    handler: Handler
    fut: asyncio.Future[Any] | None


@dataclass
class TurnInfo:
    """The turn between `turn.next` and `turn.end` (the mock's `live.current`)."""

    message_id: str
    character_id: str
    variant_id: str | None = None
    started: bool = False          # turn.start emitted (a message exists)
    content: str = ""              # streamed so far
    closed: bool = False
    started_iso: str = ""          # when turn.next went out (ledger rows of this turn are at or after it)
    t0_ms: float = 0.0
    first_token_ms: float | None = None
    trace: dict[str, Any] = field(default_factory=dict)
    citations: list[dict[str, Any]] | None = None
    spec: Any = None
    ctx: Any = None
    engine: Any = None


@dataclass
class ModeState:
    """Per-mode cursors the mock keeps on `LiveSession` (rebuilt from the stored state when an actor is re-created)."""

    turn: int = 0                                 # rng seed counter (`live.turn`)
    recent: list[str] = field(default_factory=list)
    nudge: str | None = None
    direction: tuple[str, int] | None = None      # watch: (note, turns left)
    watch_idx: int | None = None
    debate_order: list[str] | None = None
    debate_idx: int = 0
    skip_to_closing: bool = False
    extend: bool = False
    debate_prefetch: dict[int, Any] = field(default_factory=dict)   # opening-round prefetches by order index


class SessionActor:
    def __init__(self, rt: Runtime, manager: LiveSessionManager, writer: EventWriter) -> None:
        self.rt = rt
        self.manager = manager
        self.writer = writer
        self.sid = writer.session_id
        self.inbox: Inbox[Envelope] = Inbox()
        self.turns: Inbox[Job] = Inbox()
        self.write_lock = asyncio.Lock()
        self.held = writer.session["status"] == "paused" and writer.session.get("pausedReason") != "turn_cap"
        self.current: TurnInfo | None = None
        self.pending_query: Any = None   # M5: the latest user message's query embedding (sessions/retrieve.py)
        self.mode = ModeState(turn=len(writer.state["order"]))
        self.busy = False               # a job is running
        self.last_active_ms = to_ms(rt.clock.now())
        self._worker: asyncio.Task[None] | None = None
        self._loop: asyncio.Task[None] | None = None
        self._idle: asyncio.Task[None] | None = None
        self._timers: set[asyncio.Task[None]] = set()
        self._background: set[asyncio.Task[Any]] = set()
        self.prefetches: set[Any] = set()   # sessions.prefetch.Prefetch runs ahead of their slot (design D5)
        self.epoch = 0
        self.stopped = False

    # ── views ──
    @property
    def state(self) -> Wire:
        s: Wire = self.writer.state
        return s

    @property
    def session(self) -> Wire:
        return self.writer.session

    @property
    def mode_name(self) -> str:
        return str(self.session["mode"])

    @property
    def generating(self) -> bool:
        """The mock's `live.current && !live.held`: a turn is under way and the session isn't held."""
        return self.current is not None and not self.current.closed and not self.held

    @property
    def seed(self) -> str:
        """Randomness seed for the scripted ports: stable for the same session state (not the random id)."""
        s = self.session
        return f"{s['createdAt']}|{s['mode']}|{','.join(p['characterId'] for p in s['participants'])}"

    def touch(self) -> None:
        self.last_active_ms = to_ms(self.rt.clock.now())

    # ── lifecycle ──
    def start(self) -> None:
        self._loop = self.rt.spawn(f"actor:{self.sid}", self._run_inbox())
        self._worker = self.rt.spawn(f"turns:{self.sid}", self._run_turns())
        self._idle = self.rt.spawn(f"idle:{self.sid}", self._watch_idle())

    async def stop(self) -> None:
        """Cancel everything (delete, idle release, shutdown). In-flight ledger writes still land (M2 shielding)."""
        self.stopped = True
        tasks = [x for x in (self._loop, self._worker, self._idle, *self._timers, *self._background,
                             *(pf.task for pf in self.prefetches)) if x is not None]
        current = asyncio.current_task()
        for x in tasks:
            if x is not current:
                x.cancel()
        for x in tasks:
            if x is not current:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await x
        self._timers.clear()
        self._background.clear()
        for env in self.inbox.clear():
            if env.fut is not None and not env.fut.done():
                env.fut.cancel()

    # ── commands ──
    async def submit(self, handler: Handler) -> Any:
        """Run `handler` inside the actor (serialised with every other command) and return its result."""
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.inbox.put(Envelope(handler, fut))
        return await fut

    def post(self, handler: Handler) -> None:
        """Fire-and-forget command (cap pause fan-out, budget warning mirror)."""
        self.inbox.put(Envelope(handler, None))

    async def _run_inbox(self) -> None:
        while True:
            env = await self.inbox.get()
            self.touch()
            try:
                result = await env.handler()
            except asyncio.CancelledError:
                if env.fut is not None and not env.fut.done():
                    env.fut.cancel()
                raise
            except Exception as e:
                if env.fut is not None and not env.fut.done():
                    env.fut.set_exception(e)
                elif env.fut is None:
                    log.exception("posted command failed in %s", self.sid)
            else:
                if env.fut is not None and not env.fut.done():
                    env.fut.set_result(result)

    # ── the turn queue ──
    def enqueue(self, job: Job, *, front: bool = False) -> None:
        self.turns.put(job, front=front)

    async def _run_turns(self) -> None:
        while True:
            job = await self.turns.get()
            self.busy = True
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("turn job failed in %s", self.sid)
            finally:
                self.busy = False
                self.touch()

    def after(self, ms: float, fn: Callable[[], Awaitable[None] | None]) -> None:
        """Run `fn` after `ms` of clock time, unless `clear()` cancels it first (the mock's `h.after`)."""
        async def wait() -> None:
            await self.rt.clock.sleep(ms / 1000)
            r = fn()
            if r is not None:
                await r

        task = self.rt.spawn(f"after:{self.sid}", wait())
        self._timers.add(task)
        task.add_done_callback(self._timers.discard)

    def background(self, name: str, coro: Awaitable[Any]) -> None:
        """Work that never delays the next speaker (listener reactions)."""
        async def run() -> None:
            await coro

        task = self.rt.spawn(f"{name}:{self.sid}", run())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def clear(self, *, keep_current: bool = False) -> None:
        """Cancel pending work (the mock's `clearLive`). `keep_current` lets a turn already streaming finish.
        Prefetched turns are discarded either way (D-77: their spend and drain stand)."""
        self.turns.clear()
        for x in list(self._timers):
            x.cancel()
        self._timers.clear()
        for pf in list(self.prefetches):
            if not pf.released:
                await pf.discard()
        if keep_current and self.current is not None and not self.current.closed:
            self.mode_epoch_bump()
            return
        self.mode_epoch_bump()
        await self._cut_worker()

    def mode_epoch_bump(self) -> None:
        """Jobs check the epoch between turns: after a clear, a running job ends at its next boundary."""
        self.epoch += 1

    async def _cut_worker(self) -> None:
        worker = self._worker
        if worker is not None and not worker.done() and worker is not asyncio.current_task():
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker
        self.busy = False
        if not self.stopped:
            self._worker = self.rt.spawn(f"turns:{self.sid}", self._run_turns())

    # ── writing ──
    async def emit(self, *events: Mapping[str, Any], traces: Mapping[str, TraceMeta] | None = None) -> list[Wire]:
        async with self.write_lock:
            return await self.writer.append(list(events), traces=traces)

    async def emit_with(self, events: Sequence[Mapping[str, Any]], extra: Any) -> list[Wire]:
        async with self.write_lock:
            return await self.writer.append(list(events), extra=extra)

    # ── idle release ──
    async def _watch_idle(self) -> None:
        idle_ms = self.rt.runtime_cfg.runtime.idle_release_ms
        while True:
            now = to_ms(self.rt.clock.now())
            wait = max(1.0, self.last_active_ms + idle_ms - now)
            await self.rt.clock.sleep(wait / 1000)
            if self.is_idle(idle_ms):
                self.rt.spawn(f"release:{self.sid}", self.manager.release(self.sid, self))
                return

    def is_idle(self, idle_ms: float) -> bool:
        if self.busy or len(self.turns) or len(self.inbox) or self._timers or self._background:
            return False
        if self.current is not None and not self.current.closed:
            return False
        if self.rt.bus.subscriber_count(session_channel(self.sid)) > 0:
            self.touch()
            return False
        return to_ms(self.rt.clock.now()) - self.last_active_ms >= idle_ms
