"""Timestamps: ISO-8601 UTC with exactly millisecond precision (doc 02 §1), so text order equals time order."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

_FMT = "%Y-%m-%dT%H:%M:%S"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def to_iso(dt: datetime) -> str:
    """Format an aware datetime as `YYYY-MM-DDTHH:MM:SS.mmmZ`."""
    u = dt.astimezone(UTC)
    return f"{u.strftime(_FMT)}.{u.microsecond // 1000:03d}Z"


def parse_iso(s: str) -> datetime:
    """Parse any ISO-8601 instant the contract allows (`Z` or an offset, 0–9 fractional digits)."""
    t = s.strip()
    if t.endswith(("Z", "z")):
        t = t[:-1] + "+00:00"
    if "." in t:
        head, rest = t.split(".", 1)
        i = 0
        while i < len(rest) and rest[i].isdigit():
            i += 1
        frac, tail = rest[:i], rest[i:]
        t = f"{head}.{(frac + '000000')[:6]}{tail}"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalise_iso(s: str) -> str:
    """Seed import: any ISO instant → the stored millisecond form."""
    return to_iso(parse_iso(s))


def iso_from_ms(ms: float) -> str:
    """JS `new Date(ms).toISOString()`: the time value is truncated to whole milliseconds, then formatted."""
    return to_iso(_EPOCH + timedelta(milliseconds=math.trunc(ms)))


def ms_from_iso(s: str) -> int:
    """JS `Date.parse(iso)` for the instants the contract carries (exact integer milliseconds)."""
    d = parse_iso(s) - _EPOCH
    return (d.days * 86_400 + d.seconds) * 1000 + d.microseconds // 1000


def to_ms(dt: datetime) -> int:
    d = dt.astimezone(UTC) - _EPOCH
    return (d.days * 86_400 + d.seconds) * 1000 + d.microseconds // 1000


def from_ms(ms: float) -> datetime:
    return _EPOCH + timedelta(milliseconds=math.trunc(ms))
