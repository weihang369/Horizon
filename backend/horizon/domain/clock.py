"""The Clock (doc 01 §4.7): the only source of "now". Pacing uses `sleep`, so tests can move virtual time.

Pricing period (R-23, ENG-06): DeepSeek peak runs Mon–Fri 09:00–12:00 and 14:00–18:00 Malaysia time. That is the
provider's schedule, so it is pinned to `seed/pricing.json` `peak.tz` whatever HORIZON_TZ says (M2 design OQ-G). Day
boundaries (`today`, `day_start`: spentToday, the energy day) stay in HORIZON_TZ. Same windows as `rushHour.ts`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

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

    def now(self) -> datetime:
        raise NotImplementedError

    async def sleep(self, seconds: float) -> None:
        raise NotImplementedError

    def today_start(self) -> datetime:
        return self.calendar.day_start(self.now())

    def pricing_period(self) -> PricePeriod:
        return self.calendar.period(self.now())

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
    """Test clock: time moves only through `set`/`advance`; `sleep` advances virtual time and yields once."""

    def __init__(self, calendar: PricingCalendar, at: datetime) -> None:
        self.calendar = calendar
        self._now = at.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = at.astimezone(UTC)

    def advance(self, ms: float) -> None:
        self._now = self._now + timedelta(milliseconds=ms)

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds * 1000)
        await asyncio.sleep(0)


def calendar_for(tz_name: str, *, peak_tz: str = PEAK_TZ,
                 windows: Sequence[tuple[int, int]] = PEAK_WINDOWS) -> PricingCalendar:
    return PricingCalendar(tz=ZoneInfo(tz_name), windows=tuple(windows), peak_tz=ZoneInfo(peak_tz))
