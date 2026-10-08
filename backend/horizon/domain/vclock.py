"""Virtual time for tests (session-runtime design D2): timers, the activity tracker and settle.

While the test clock is frozen, `sleep` registers a timer and waits until `/_test/clock` advances past it. An advance
fires due timers in deadline order (registration order on ties) and, after each one, waits for the work it woke to
*settle*, i.e. for the activity counter to reach zero. Live sessions over HTTP are then deterministic: `tick(6000)`
returns with the greeting already stored.

- **Activity.** Each runtime task (actor, turn, reaction…) holds a named token while it runs: `spawn()` takes it at
  creation and drops it when the task ends. A task gives its token up while it waits on something only a waker can
  end (a clock timer, its inbox, an LLM slot), and the waker takes it back on the task's behalf *before* waking it, so
  the count never reads zero while woken work is still pending. HTTP handlers and SSE generators hold no token.
- **Guard.** `settle()` raises `SettleTimeout` after 10 s of real time, naming the holders that are still busy.
"""

from __future__ import annotations

import asyncio
import contextvars
import itertools
import logging
from collections import Counter, deque
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

log = logging.getLogger("horizon.vclock")

T = TypeVar("T")
SETTLE_TIMEOUT_S = 10.0
_names = itertools.count(1)


class SettleTimeout(RuntimeError):
    """Work woken by a clock advance did not finish within the real-time guard."""


@dataclass(frozen=True)
class Holder:
    activity: Activity
    name: str

    def hold(self) -> None:
        self.activity.hold(self.name)

    def drop(self) -> None:
        self.activity.drop(self.name)


_holder: contextvars.ContextVar[Holder | None] = contextvars.ContextVar("horizon_activity_holder", default=None)


def current_holder() -> Holder | None:
    return _holder.get()


class Activity:
    """Counts busy tokens by holder name; `settle()` waits for the count to reach zero."""

    def __init__(self) -> None:
        self._busy: Counter[str] = Counter()
        self._waiters: list[asyncio.Future[None]] = []

    def hold(self, name: str) -> None:
        self._busy[name] += 1

    def drop(self, name: str) -> None:
        n = self._busy[name] - 1
        if n > 0:
            self._busy[name] = n
        else:
            del self._busy[name]
            if n < 0:
                log.error("activity token %s dropped more often than held", name)
        if not self._busy:
            for w in self._waiters:
                if not w.done():
                    w.set_result(None)
            self._waiters.clear()

    @property
    def busy(self) -> dict[str, int]:
        return dict(self._busy)

    async def settle(self, guard_s: float = SETTLE_TIMEOUT_S) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + guard_s
        while self._busy:
            fut: asyncio.Future[None] = loop.create_future()
            self._waiters.append(fut)
            left = deadline - loop.time()
            try:
                await asyncio.wait_for(fut, timeout=max(0.0, left))
            except TimeoutError as e:
                raise SettleTimeout(f"virtual time did not settle within {guard_s:g}s; still busy: "
                                    f"{', '.join(sorted(self._busy))}") from e
        # Let callbacks scheduled by the last step run (task done-callbacks, queue wake-ups).
        for _ in range(3):
            await asyncio.sleep(0)
        if self._busy:
            await self.settle(max(0.0, deadline - loop.time()))

    def spawn(self, name: str, coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        """A background task holding a token for as long as it runs (`rt.spawn`)."""
        holder = Holder(self, f"{name}#{next(_names)}")
        holder.hold()
        ctx = contextvars.copy_context()
        ctx.run(_holder.set, holder)
        started = False

        async def run() -> T:
            nonlocal started
            started = True
            return await coro

        task = asyncio.get_running_loop().create_task(run(), name=holder.name, context=ctx)

        def done(_t: asyncio.Task[T]) -> None:
            if not started:
                coro.close()  # cancelled before its first step: never awaited
            holder.drop()

        task.add_done_callback(done)
        return task

    def track(self, task: asyncio.Task[Any], name: str) -> None:
        """Count a task created elsewhere (a shielded ledger write, a late decision) until it finishes."""
        self.hold(name)
        task.add_done_callback(lambda _t: self.drop(name))


def track(task: asyncio.Task[Any], name: str) -> None:
    """Count `task` against the caller's activity, if the caller runs under one (no-op otherwise)."""
    h = current_holder()
    if h is not None:
        h.activity.track(task, f"{name}#{next(_names)}")


async def wait_handoff(fut: asyncio.Future[Any], holder: Holder | None) -> Any:
    """Await `fut` with the caller's token given up; the waker must `hold()` it before resolving `fut`."""
    if holder is not None:
        holder.drop()
    try:
        return await fut
    except asyncio.CancelledError:
        if fut.cancelled() and holder is not None:
            holder.hold()  # cancelled while waiting: nobody took the token back for us
        raise


@dataclass(order=True)
class Timer:
    deadline_ms: float
    seq: int
    fut: asyncio.Future[None] = field(compare=False)
    holder: Holder | None = field(compare=False)


class Inbox[T]:
    """A single-consumer queue whose waiting consumer gives up its token; `put` takes it back (hand-off)."""

    def __init__(self) -> None:
        self._items: deque[T] = deque()
        self._waiter: tuple[asyncio.Future[None], Holder | None] | None = None

    def __len__(self) -> int:
        return len(self._items)

    def put(self, item: T, *, front: bool = False) -> None:
        if front:
            self._items.appendleft(item)
        else:
            self._items.append(item)
        self._wake()

    def clear(self) -> list[T]:
        out = list(self._items)
        self._items.clear()
        return out

    def items(self) -> list[T]:
        return list(self._items)

    def _wake(self) -> None:
        if self._waiter is None:
            return
        fut, holder = self._waiter
        self._waiter = None
        if fut.done():
            return
        if holder is not None:
            holder.hold()
        fut.set_result(None)

    async def get(self) -> T:
        while not self._items:
            fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            holder = current_holder()
            self._waiter = (fut, holder)
            try:
                await wait_handoff(fut, holder)
            finally:
                if self._waiter is not None and self._waiter[0] is fut:
                    self._waiter = None
        return self._items.popleft()


class Slots:
    """A semaphore with token hand-off (the shared `llm_slots`)."""

    def __init__(self, n: int) -> None:
        self.size = n
        self._free = n
        self._waiters: deque[tuple[asyncio.Future[None], Holder | None]] = deque()
        self.peak = 0

    @property
    def in_use(self) -> int:
        return self.size - self._free

    async def acquire(self) -> None:
        if self._free > 0 and not self._waiters:
            self._take()
            return
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        entry = (fut, current_holder())
        self._waiters.append(entry)
        try:
            await wait_handoff(fut, entry[1])
        except asyncio.CancelledError:
            if fut.cancelled():
                if entry in self._waiters:
                    self._waiters.remove(entry)
            else:
                self.release()  # granted, then cancelled before it ran: pass the slot on
            raise

    def _take(self) -> None:
        self._free -= 1
        self.peak = max(self.peak, self.in_use)

    def release(self) -> None:
        while self._waiters:
            fut, holder = self._waiters.popleft()
            if fut.done():
                continue
            if holder is not None:
                holder.hold()
            self.peak = max(self.peak, self.in_use)
            fut.set_result(None)  # the slot passes straight to the waiter
            return
        self._free += 1

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        await self.acquire()
        try:
            yield
        finally:
            self.release()


async def wait_at_most(clock: Any, task: asyncio.Future[Any], seconds: float) -> bool:
    """Wait for `task` for at most `seconds` of clock time, with the caller's token given up; True if it finished.

    The timeout is a clock timer (virtual in tests), so a slow task loses the race in virtual time exactly as it would
    in real time. `task` is never cancelled; the caller decides what a late result means.
    """
    if task.done():
        return True
    fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    holder = current_holder()

    def wake(_t: Any = None) -> None:
        if not fut.done():
            if holder is not None:
                holder.hold()
            fut.set_result(None)

    async def timer() -> None:
        await clock.sleep(seconds)
        wake()

    t = clock.activity.spawn("wait-at-most", timer())
    task.add_done_callback(wake)
    try:
        await wait_handoff(fut, holder)
    finally:
        task.remove_done_callback(wake)
        t.cancel()
    return task.done()
