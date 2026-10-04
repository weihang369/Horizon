"""Character energy (doc backend/04 §4, D-42, D-76, D-78): the SAME algorithm as `frontend/src/domain/energy.ts`.

Both are pinned by `backend/tests/fixtures/energy/cases.json`; fix them together if they ever diverge.
Functions take and return wire-shaped dicts (camelCase) and epoch milliseconds, exactly like the TS module.
Storage keeps `current` / `spentToday` as REAL; only the wire floors them (`to_wire_energy`).
"""

from __future__ import annotations

import math
from typing import Any, Literal, TypedDict

from horizon.domain.timeutil import iso_from_ms, ms_from_iso

EnergyState = Literal["active", "tired", "exhausted"]
Energy = dict[str, Any]

USD_PER_POINT = 0.0001
TIRED_PCT = 0.2
EST_REPLY_POINTS: dict[str, int] = {"off_peak": 4, "peak": 8}
DAY_UTC_OFFSET_MIN = 8 * 60


def points_for_cost(cost_usd: float, usd_per_point: float = USD_PER_POINT) -> int:
    if cost_usd <= 0:
        return 0
    return math.ceil(cost_usd / usd_per_point - 1e-9)  # tolerate float noise (0.0005 / 0.0001 = 5.000000001)


def energy_state(current: float, max_: float, est_reply_points: float = EST_REPLY_POINTS["off_peak"]) -> EnergyState:
    if current < est_reply_points:
        return "exhausted"
    if current < max_ * TIRED_PCT:
        return "tired"
    return "active"


def regen_at(e: Energy, now_ms: float) -> float:
    """Lazily regenerated value (never above max by regeneration; top-ups may exceed max)."""
    since = max(0.0, now_ms - ms_from_iso(e["asOf"])) / 3_600_000
    if e["current"] >= e["max"]:
        return float(e["current"])
    return float(min(e["max"], e["current"] + e["regenPerHour"] * since))


def full_at(current: float, max_: float, regen_per_hour: float, now_ms: float) -> str | None:
    if current >= max_ or regen_per_hour <= 0:
        return None
    return iso_from_ms(now_ms + ((max_ - current) / regen_per_hour) * 3_600_000)


def energy_day(epoch_ms: float, utc_offset_min: int = DAY_UTC_OFFSET_MIN) -> str:
    return iso_from_ms(epoch_ms + utc_offset_min * 60_000)[:10]


def day_roll(e: Energy, now_ms: float, utc_offset_min: int = DAY_UTC_OFFSET_MIN) -> Energy:
    if energy_day(ms_from_iso(e["asOf"]), utc_offset_min) == energy_day(now_ms, utc_offset_min):
        return e
    return {**e, "spentToday": 0}


def _with(e: Energy, **fields: Any) -> Energy:
    """Object spread where `None` means `undefined` (the key is dropped), matching the JSON comparison."""
    out = dict(e)
    for k, v in fields.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def _est(est_reply_points: float | None) -> float:
    return EST_REPLY_POINTS["off_peak"] if est_reply_points is None else est_reply_points


def settle(e: Energy, now_ms: float, *, frozen: bool = False, est_reply_points: float | None = None,
           utc_offset_min: int = DAY_UTC_OFFSET_MIN) -> Energy:
    """Materialise regen and the day roll at `now_ms` (REAL value kept). `frozen` = demo mode: state only.

    `utc_offset_min` is the energy-day offset: the fixtures pin MYT; the backend passes HORIZON_TZ's offset."""
    est = _est(est_reply_points)
    if frozen:
        return _with(e, state=energy_state(e["current"], e["max"], est))
    rolled = day_roll(e, now_ms, utc_offset_min)
    current = regen_at(rolled, now_ms)
    return _with(rolled, current=current, asOf=iso_from_ms(now_ms), state=energy_state(current, e["max"], est),
                 fullAt=full_at(current, e["max"], e["regenPerHour"], now_ms))


def drain(e: Energy, points: float, now_ms: float, *, frozen: bool = False, est_reply_points: float | None = None,
          utc_offset_min: int = DAY_UTC_OFFSET_MIN) -> Energy:
    """A character's own reply (D-42). Overdraft clamps at 0; the reply still finishes."""
    est = _est(est_reply_points)
    s = settle(e, now_ms, frozen=frozen, est_reply_points=est, utc_offset_min=utc_offset_min)
    current = max(0.0, s["current"] - points)
    return _with(s, current=current, state=energy_state(current, e["max"], est),
                 fullAt=full_at(current, e["max"], e["regenPerHour"], now_ms), spentToday=s["spentToday"] + points)


def top_up(e: Energy, points: float, now_ms: float, *, frozen: bool = False, est_reply_points: float | None = None,
           utc_offset_min: int = DAY_UTC_OFFSET_MIN) -> Energy:
    """ENG-05: may exceed max for today. Gate it with `can_top_up` first (D-76)."""
    est = _est(est_reply_points)
    s = settle(e, now_ms, frozen=frozen, est_reply_points=est, utc_offset_min=utc_offset_min)
    current = s["current"] + points
    return _with(s, current=current, state=energy_state(current, e["max"], est),
                 fullAt=full_at(current, e["max"], e["regenPerHour"], now_ms))


def with_max(e: Energy, max_: float, now_ms: float, *, frozen: bool = False,
             est_reply_points: float | None = None, utc_offset_min: int = DAY_UTC_OFFSET_MIN) -> Energy:
    """Set-max (ENG-05): settle first, then the new max with `regenPerHour = max / 24`. Current is kept, even above max."""
    est = _est(est_reply_points)
    s = settle(e, now_ms, frozen=frozen, est_reply_points=est, utc_offset_min=utc_offset_min)
    regen = max_ / 24
    return _with(s, max=max_, regenPerHour=regen, state=energy_state(s["current"], max_, est),
                 fullAt=full_at(s["current"], max_, regen, now_ms))


class TopUpGate(TypedDict):
    spentTodayUsd: float
    todayTopUpPoints: float
    points: float
    usdPerPoint: float
    dailyCapUsd: float


def can_top_up(g: TopUpGate) -> bool:
    """D-76: allowed while spentToday + (todayTopUpPoints + points) × usdPerPoint ≤ dailyCap."""
    return g["spentTodayUsd"] + (g["todayTopUpPoints"] + g["points"]) * g["usdPerPoint"] <= g["dailyCapUsd"] + 1e-9


def to_wire_energy(e: Energy) -> Energy:
    """The wire form: `current` and `spentToday` floored to integers; everything else as stored."""
    return {**e, "current": math.floor(e["current"]), "spentToday": math.floor(e["spentToday"])}


def read_energy(stored: Energy, now_ms: float, *, frozen: bool, est_reply_points: float,
                utc_offset_min: int = DAY_UTC_OFFSET_MIN) -> Energy:
    """A character read (energy spec): derive `state` / `fullAt` for the current period, then floor for the wire.

    Frozen (demo mode, ENG-07): nothing regenerates, and `fullAt` is what it was at `asOf`.
    """
    if frozen:
        cur = float(stored["current"])
        out = _with(stored, state=energy_state(cur, stored["max"], est_reply_points),
                    fullAt=full_at(cur, stored["max"], stored["regenPerHour"], ms_from_iso(stored["asOf"])))
    else:
        out = settle(stored, now_ms, est_reply_points=est_reply_points, utc_offset_min=utc_offset_min)
    return to_wire_energy(out)
