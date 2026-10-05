"""The Clock (doc 01 §4.7): the only source of "now". Pacing uses `sleep`, so tests can move virtual time.

Test clock (session-runtime design D2): while frozen, `FrozenClock.sleep` waits for virtual time, and `advance` fires
due timers in order and settles the work they wake (`domain/vclock.py`). Released, it behaves like the system clock.
A test-mode `period_override` (the `rush_hour` scenario) pins the pricing period.

Pricing period (R-23, ENG-06): DeepSeek peak runs Mon–Fri 09:00–12:00 and 14:00–18:00 Malaysia time. That is the
provider's schedule, so it is pinned to `seed/pricing.json` `peak.tz` whatever HORIZON_TZ says (M2 design OQ-G). Day
boundaries (`today`, `day_start`: spentToday, the energy day) stay in HORIZON_TZ. Same windows as `rushHour.ts`.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from horizon.domain.vclock import Activity, Timer, current_holder, wait_handoff

PricePeriod = Literal["peak", "off_peak"]

DEFAULT_TZ = "Asia/Kuala_Lumpur"
PEAK_TZ = "Asia/Kuala_Lumpur"  # mirrors seed/pricing.json peak.tz (a test pins the two together)
# Peak windows in PEAK_TZ minutes-of-day: [start, end).
PEAK_WINDOWS: tuple[tuple[int, int], ...] = ((9 * 60, 12 * 60), (14 * 60, 18 * 60))


@dataclass(frozen=True)
class PricingCalendar:
    tz: ZoneInfo
    windows: Sequence[tuple[int, int]] = PEAK_WINDOWS
    peak_tz: ZoneInfo = field(default_factory=lambda: ZoneInfo(PEAK_TZ))

    def local(self, at: datetime) -> datetime:
        return at.astimezone(self.tz)

    def peak_local(self, at: datetime) -> datetime:
        return at.astimezone(self.peak_tz)

    def today(self, at: datetime) -> date:
        return self.local(at).date()

    def day_start(self, at: datetime) -> datetime:
        d = self.today(at)
        return datetime.combine(d, time(0), tzinfo=self.tz).astimezone(UTC)

    def period(self, at: datetime) -> PricePeriod:
        loc = self.peak_local(at)
        if loc.weekday() >= 5:
            return "off_peak"
        minutes = loc.hour * 60 + loc.minute + loc.second / 60 + loc.microsecond / 60_000_000
        return "peak" if any(a <= minutes < b for a, b in self.windows) else "off_peak"

    def next_change(self, at: datetime) -> datetime:
        """The first peak/off-peak boundary strictly after `at`."""
        start = self.peak_local(at).date()
        for offset in range(8):
            d = start + timedelta(days=offset)
            if d.weekday() >= 5:
                continue
            for a, b in self.windows:
                for m in (a, b):
                    t = datetime.combine(d, time(m // 60, m % 60), tzinfo=self.peak_tz).astimezone(UTC)
                    if t > at:
                        return t
        return at + timedelta(days=1)


class Clock:
    """Base clock. Subclasses provide `now` and `sleep`; the pricing helpers derive from `now`."""

    calendar: PricingCalendar
    period_override: PricePeriod | None = None   # test mode only (`rush_hour`)
    _activity: Activity | None = None

    @property
    def activity(self) -> Activity:
        """The runtime's activity tracker (one per clock, so `advance` settles exactly the work it woke)."""
        if self._activity is None:
            self._activity = Activity()
        return self._activity

    def now(self) -> datetime:
        raise NotImplementedError

    async def sleep(self, seconds: float) -> None:
        raise NotImplementedError

    def today_start(self) -> datetime:
        return self.calendar.day_start(self.now())

    def pricing_period(self) -> PricePeriod:
        return self.period_override or self.calendar.period(self.now())

    def next_change_at(self) -> datetime:
        return self.calendar.next_change(self.now())


class SystemClock(Clock):
    def __init__(self, calendar: PricingCalendar) -> None:
        self.calendar = calendar

    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FrozenClock(Clock):
    """Test clock. Frozen: time moves only through `set`/`advance`, and `sleep` waits for an advance past its deadline.
    Released: real time, like `SystemClock` (the same object, so everything holding it follows)."""

    def __init__(self, calendar: PricingCalendar, at: datetime | None = None, *, released: bool = False) -> None:
        self.calendar = calendar
        self._now = (at or datetime.now(UTC)).astimezone(UTC)
        self._released = released or at is None
        self._timers: list[Timer] = []
        self._seq = itertools.count()
        self._advancing = asyncio.Lock()

    @property
    def frozen(self) -> bool:
        return not self._released

    def now(self) -> datetime:
        return datetime.now(UTC) if self._released else self._now

    def set(self, at: datetime) -> None:
        """Freeze at `at` without firing timers."""
        self._released = False
        self._now = at.astimezone(UTC)

    def release(self) -> None:
        """Back to real time: every pending sleeper wakes now, so nothing hangs."""
        self._released = True
        timers, self._timers = self._timers, []
        for t in sorted(timers):
            self._fire(t)

    @property
    def pending(self) -> int:
        return sum(1 for t in self._timers if not t.fut.done())

    def _fire(self, t: Timer) -> bool:
        if t.fut.done():
            return False
        if t.holder is not None:
            t.holder.hold()
        t.fut.set_result(None)
        return True

    async def advance(self, ms: float) -> None:
        """Fire due timers in deadline order, settling after each; then move to the target and settle once more."""
        async with self._advancing:
            if self._released:
                self.set(datetime.now(UTC))
            await self.activity.settle()
            target = self._now + timedelta(milliseconds=ms)
            while self._timers and self._timers[0].deadline_ms <= _ms(target):
                t = heapq.heappop(self._timers)
                if t.fut.done():
                    continue
                self._now = max(self._now, _from_ms(t.deadline_ms))
                self._fire(t)
                await self.activity.settle()
            self._now = max(self._now, target)
            await self.activity.settle()

    async def settle(self) -> None:
        await self.activity.settle()

    async def sleep(self, seconds: float) -> None:
        if self._released:
            await asyncio.sleep(seconds)
            return
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        timer = Timer(_ms(self._now) + seconds * 1000, next(self._seq), fut, current_holder())
        heapq.heappush(self._timers, timer)
        await wait_handoff(fut, timer.holder)


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _ms(at: datetime) -> float:
    return (at - _EPOCH) / timedelta(milliseconds=1)


def _from_ms(ms: float) -> datetime:
    return _EPOCH + timedelta(milliseconds=ms)


def calendar_for(tz_name: str, *, peak_tz: str = PEAK_TZ,
                 windows: Sequence[tuple[int, int]] = PEAK_WINDOWS) -> PricingCalendar:
    return PricingCalendar(tz=ZoneInfo(tz_name), windows=tuple(windows), peak_tz=ZoneInfo(peak_tz))
