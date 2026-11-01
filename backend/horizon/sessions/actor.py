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
import copy
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
    system1: list[dict[str, Any]] = field(default_factory=list)   # rows appended mid-stream (D24), merged at finish
    system1_calls: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] | None = None
    face: str | None = None        # M9: the last face this turn emitted (the face check reads it)
    auto: bool = True              # M9: the emotion mode was AUTO at turn.start (doc 13 W2)
    spec: Any = None
    ctx: Any = None
    engine: Any = None
    guard: Any = None              # M14 (safety D10): the output check in flight, handed to `output_check` on Stop
    checked: Any = None            # M14 (D10): a released prefetch's check result, so it isn't checked twice
    stream_end: Any = None         # M14 (D10): when the stream ended (the waits after a turn count from here)
    key: bool | None = None        # M15 (images-music D4): the key status, read once when the reply starts


@dataclass
class ModeState:
    """Per-mode cursors the mock keeps on `LiveSession` (rebuilt from the stored state when an actor is re-created)."""

    turn: int = 0                                 # rng seed counter (`live.turn`)
    recent: list[str] = field(default_factory=list)
    nudge: str | None = None
    direction: tuple[str, int] | None = None      # watch: (note, turns left)
    watch_idx: int | None = None
    skip_to_closing: bool = False
    extend: bool = False
    debate_prefetch: dict[int, Any] = field(default_factory=dict)   # opening-round prefetches by slot index
    # M11 (debate design D3): the slot and member the last `turn.next` named; the cursor itself is read from the log
    debate_announced: tuple[int, str] | None = None
    debate_plan: Any = None                       # M11 (debate D8): the stored plan for the next slot (sessions/debate_plan)
    host_line: Any = None                         # M11 (debate D11): the host line requested ahead (sessions/debate_host)
    verdict_work: Any = None                      # M11 (debate D14): the verdict work and its fingerprint
    picked: str | None = None                     # M11 (debate D14): You decide's click, delivered when the work is done
    verdict_checked: bool = False                 # M11 (debate D14): the resume rule ran on this actor's first command
    debate_armed: bool = False                    # U-43: this actor started or stepped the debate (its chain is its own)
    plan_ahead: tuple[Any, Any, Any, Any] | None = None   # M10 watch (D15): (fingerprint, task, M12's deep work, faces)
    regenerating: set[str] = field(default_factory=set)   # pass 2 J2-02: messages with a regenerate queued or running


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
        self._named: dict[str, set[asyncio.Task[Any]]] = {}   # M9 D20: the same tasks by name, for cancel_background
        self.prefetches: set[Any] = set()   # sessions.prefetch.Prefetch runs ahead of their slot (design D5)
        self.epoch = 0
        # M10 (doc 07 G5; group-watch D12): a user message cancels the previous message's unannounced replies. Each
        # group or watch reply job captures `reply_epoch` when queued; `supersede()` bumps it and resolves the future
        # that cooperative waits (the follow plan's, the turn gap) race.
        self.reply_epoch = 0
        self._superseded: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.stopped = False
        self.summary: Any = None   # M8: sessions.summary.SummaryTask, made on first use (docs/ai/05 X2, X3)
        # M13 (memory D23): each `agent` speaker's memory list, frozen for the sitting; Forget and a run's commit drop it
        self.memory_blocks: dict[str, list[Any]] = {}
        self.memory_overflow: dict[str, bool] = {}
        self.memory_gen: dict[str, int] = {}   # bumped by each drop, so a read that raced one is never cached
        # M14 (safety D4): the user lines a plan of this session is asking the safety questions about right now
        self.safety_asking: set[str] = set()

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
        self._named.clear()
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
    def enqueue(self, job: Job, *, front: bool = False, epoch: int | None = None) -> None:
        """Queue `job`. With `epoch` (G5), the worker skips it if a user message superseded that epoch meanwhile."""
        if epoch is not None:
            inner = job

            async def job() -> None:
                if epoch == self.reply_epoch:
                    await inner()

        self.turns.put(job, front=front)

    # ── G5: the reply epoch (group-watch D12) ──
    async def supersede(self) -> int:
        """A user message arrives (a group send, a watch Step in), before it is appended: under the write lock, bump
        the epoch and resolve the superseded future, so no older reply can announce after this point (its `turn.next`
        check runs under the same lock). Then discard unreleased prefetches (D-77: their spend and drain stand); queued
        older jobs are skipped by the worker. Returns the new epoch."""
        async with self.write_lock:
            self.reply_epoch += 1
            old, self._superseded = self._superseded, asyncio.get_running_loop().create_future()
            old.set_result(None)
        for pf in list(self.prefetches):
            if not pf.released:
                await pf.discard()
        return self.reply_epoch

    def superseded(self, epoch: int) -> asyncio.Future[None]:
        """A future that is done once `epoch` has been superseded (at once if it already is)."""
        if epoch == self.reply_epoch:
            return self._superseded
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        done.set_result(None)
        return done

    def current_epoch(self, epoch: int | None) -> bool:
        return epoch is None or epoch == self.reply_epoch

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

    def background(self, name: str, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        """Work that never delays the next speaker (listener reactions, the rolling summary, a watch's plan made
        ahead). Stop cancels it; idle release waits for it. The task's result is the coroutine's."""
        async def run() -> Any:
            return await coro

        task = self.rt.spawn(f"{name}:{self.sid}", run())
        self._background.add(task)
        named = self._named.setdefault(name, set())
        named.add(task)

        def done(t: asyncio.Task[Any]) -> None:
            self._background.discard(t)
            named.discard(t)

        task.add_done_callback(done)
        return task

    def cancel_background(self, *names: str) -> int:
        """Cancel and forget the named background tasks (M9 D20: reactions, face checks). Returns how many were
        running. The cancelled tasks finish their own cleanup (a Decider call detaches; nothing is written)."""
        n = 0
        for name in names:
            for task in list(self._named.pop(name, ())):
                self._background.discard(task)
                if not task.done():
                    task.cancel()
                    n += 1
        return n

    async def clear(self, *, keep_current: bool = False) -> None:
        """Cancel pending work (the mock's `clearLive`). `keep_current` lets a turn already streaming finish.
        Prefetched turns are discarded either way (D-77: their spend and drain stand). Listener reactions and face
        checks are dropped (M9 D20; E5, W2), and so is a watch's plan made ahead (M10 D15); the rolling summary and the
        memory writer keep running."""
        self.turns.clear()
        self.cancel_background("reactions", "face_check", "plan_ahead", "debate_plan", "debate_plan_late", "host_line",
                               "verdict", "deep")   # M12 (rag D15): deep work started ahead of its turn
        self.mode.plan_ahead = None
        self.mode.regenerating.clear()   # their queued jobs went with the queue
        self.mode.debate_plan = None   # M11 (debate D8): its call is cancelled with its holding task
        self.mode.host_line = None     # M11 (debate D11): its call is recorded `cancelled`
        self.mode.verdict_work = None  # M11 (debate D14): End with verdict takes it out first, to reuse it
        for x in list(self._timers):
            x.cancel()
        self._timers.clear()
        for pf in list(self.prefetches):
            if not pf.released:
                await pf.discard()
        # M9 (turn-plan-emotion D8): only a turn that has started streaming is kept; one still planning is cut
        if keep_current and self.current is not None and not self.current.closed and self.current.started:
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
            # not `await worker`: a cancel of this command (actor.stop()) would reach the worker a second time, in the
            # middle of the write its first cancel is rolling back (docs/ai/checks/m9.md 9.6)
            await asyncio.wait((worker,))
        self.busy = False
        if not self.stopped:
            self._worker = self.rt.spawn(f"turns:{self.sid}", self._run_turns())

    # ── writing ──
    async def emit(self, *events: Mapping[str, Any], traces: Mapping[str, TraceMeta] | None = None) -> list[Wire]:
        async with self.write_lock:
            stored = await self.writer.append(list(events), traces=traces)
        self._memory_triggers(stored)
        return stored

    async def emit_checked(self, event: Mapping[str, Any], check: Callable[[Wire], bool]) -> list[Wire]:
        """Append `event` only if `check(state)` passes under the writer lock, just before the append (M9 D20): nothing
        can land between the check and the write. A failed check appends nothing and returns []."""
        async with self.write_lock:
            if not check(self.state):
                return []
            stored = await self.writer.append([event])
        self._memory_triggers(stored)
        return stored

    async def emit_with(self, events: Sequence[Mapping[str, Any]], extra: Any) -> list[Wire]:
        async with self.write_lock:
            stored = await self.writer.append(list(events), extra=extra)
        self._memory_triggers(stored)
        return stored

    def _memory_triggers(self, stored: Sequence[Mapping[str, Any]]) -> None:
        """M13 (memory D7): leave, end, a debate's end, watch's turn cap and a kept turn's end request a pause run."""
        runs = self.rt._memory_runs
        if runs is not None and stored:
            runs.on_events(self.sid, stored)

    # ── System 1 rows after the turn (contract rev 1.4; ai-foundation design D24) ──
    async def append_system1(self, message_id: str, variant_id: str | None, rows: Sequence[Mapping[str, Any]],
                             calls: Sequence[Mapping[str, Any]] = ()) -> bool:
        """Add System 1 rows (and their paid calls) to a message's trace, inside the actor (the one writer).
        Returns whether anything was (or will be, for a streaming reply) written. The three guards:
        - **Regenerate:** rows for a variant that is no longer active are dropped;
        - **streaming:** while the target reply streams, rows wait in its `TurnInfo` and `finish()` merges them;
        - **Forget:** inside the writer transaction, recalled entries and rows about memories that no longer exist
          are removed before the trace is stored, so an append queued before a Forget can't write the text back."""
        from horizon.sessions import system1

        async def run() -> bool:
            msg = self.state.get("messages", {}).get(message_id)
            if msg is None:
                return False
            active = msg.get("activeVariantId")
            if (active or f"{message_id}_v1") != (variant_id or f"{message_id}_v1"):
                log.debug("system1 rows for %s variant %s dropped (active %s)", message_id, variant_id, active)
                return False
            cur = self.current
            if cur is not None and cur.message_id == message_id and not cur.closed:
                cur.system1 = system1.merge_rows(cur.system1, rows)
                cur.system1_calls.extend(dict(c) for c in calls)
                return True
            trace = copy.deepcopy(msg.get("trace") or {})
            if not trace:
                return False
            trace["system1"] = system1.section(trace.get("system1"), rows)
            if calls:
                trace["calls"] = [*(trace.get("calls") or []), *(dict(c) for c in calls)]

            async def guard(tx: Any, stamped: list[Wire]) -> None:
                for e in stamped:
                    if e["type"] == "insight":
                        e["payload"]["trace"] = await system1.forget_guard(tx.conn, e["payload"]["trace"])

            async with self.write_lock:
                await self.writer.append([{"type": "insight", "payload": {"messageId": message_id, "trace": trace}}],
                                         traces={message_id: TraceMeta()}, prepare=guard)
            return True

        result: bool = await self.submit(run)
        return result

    # ── idle release ──
    async def _watch_idle(self) -> None:
        idle_ms = self.rt.runtime_cfg.runtime.idle_release_ms
        while True:
            now = to_ms(self.rt.clock.now())
            wait = max(1.0, self.last_active_ms + idle_ms - now)
            await self.rt.clock.sleep(wait / 1000)
            if self.is_idle(idle_ms):
                if self.rt._memory_runs is not None:   # M13 (memory D7 trigger 7): the backstop
                    self.rt._memory_runs.request(self.sid, reason="idle release")
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
