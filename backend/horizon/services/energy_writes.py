"""Energy writes (doc 04 §4, doc 03 §6, energy spec, design D8).

Every write to a character's energy (a reply drain, a top-up, set-max, a cost correction) runs under that character's
`asyncio.Lock`, taken BEFORE the writer lock (order: character → writer, never the reverse), and is applied inside a
writer transaction, so a top-up racing a drain can't lose either. The maths is `domain/energy.py` (shared fixtures
with `energy.ts`); storage keeps REAL values, and the wire floors them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.api.errors import HorizonHTTPError, not_found
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.db.uow import WriteTx
from horizon.domain import energy as en
from horizon.domain.ids import new_id
from horizon.domain.timeutil import iso_from_ms
from horizon.events.bus import GLOBAL

Energy = dict[str, Any]


class EnergyLocks:
    """One lock per character, created lazily (the character count is small, so they are never pruned)."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, character_id: str) -> asyncio.Lock:
        lk = self._locks.get(character_id)
        if lk is None:
            lk = self._locks[character_id] = asyncio.Lock()
        return lk


@dataclass(frozen=True)
class EnergyParams:
    """What the energy maths needs for "now": demo freeze, the period's threshold, the price of a point, the day."""

    now_ms: float
    frozen: bool
    est_reply_points: float
    usd_per_point: float
    utc_offset_min: int

    def energy_day(self) -> str:
        return en.energy_day(self.now_ms, self.utc_offset_min)


async def load_character(conn: AsyncConnection, character_id: str) -> Any:
    row = (await conn.execute(select(t.characters).where(t.characters.c.id == character_id)
                              .where(t.characters.c.deleted_at.is_(None)))).mappings().first()
    if row is None:
        raise not_found("Character")
    return row


async def apply_energy(tx: WriteTx, character_id: str, change: Callable[[Energy], Energy], p: EnergyParams) -> Energy:
    """Read, change and store one character's energy inside `tx`; announce it after commit. Returns the wire Energy."""
    row = await load_character(tx.conn, character_id)
    stored = mp.stored_energy(row)
    out = change(stored)
    await tx.conn.execute(update(t.characters).where(t.characters.c.id == character_id).values(
        energy_max=int(out["max"]), energy_current=float(out["current"]), energy_as_of=out["asOf"],
        energy_spent_today=float(out["spentToday"]),
        energy_day=row["energy_day"] if p.frozen else p.energy_day()))
    tx.publish(GLOBAL, {"type": "entity.changed", "kind": "character", "id": character_id, "worldId": row["world_id"]})
    return en.read_energy(out, p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points,
                          utc_offset_min=p.utc_offset_min)


def drain_change(cost_usd: float, p: EnergyParams) -> Callable[[Energy], Energy]:
    points = en.points_for_cost(cost_usd, p.usd_per_point)
    return lambda e: en.drain(e, points, p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points,
                              utc_offset_min=p.utc_offset_min)


def adjust_change(delta_points: int, p: EnergyParams) -> Callable[[Energy], Energy]:
    """A cost correction: positive drains more (clamped at 0); negative refunds (spentToday floored at 0)."""
    def change(e: Energy) -> Energy:
        if delta_points >= 0:
            return en.drain(e, delta_points, p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points,
                            utc_offset_min=p.utc_offset_min)
        s = en.settle(e, p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points, utc_offset_min=p.utc_offset_min)
        refund = -delta_points
        cur = s["current"] + refund
        return {**s, "current": cur, "spentToday": max(0.0, s["spentToday"] - refund),
                "state": en.energy_state(cur, s["max"], p.est_reply_points)}
    return change


# ── routes (top-up, set-max) ──
@dataclass(frozen=True)
class TopUpBudget:
    spent_today_usd: float
    daily_cap_usd: float
    local_day: str
    at: str


async def top_up(tx: WriteTx, character_id: str, points: int, p: EnergyParams, b: TopUpBudget) -> Energy:
    """D-76: gated by today's budget headroom; writes the `energy_topup` row ($0, `energy_points`) in the same tx."""
    await load_character(tx.conn, character_id)
    today_points = float((await tx.conn.execute(
        select(func.coalesce(func.sum(t.usage_records.c.energy_points), 0.0))
        .where(t.usage_records.c.category == "energy_topup").where(t.usage_records.c.local_day == b.local_day))).scalar_one())
    gate: en.TopUpGate = {"spentTodayUsd": b.spent_today_usd, "todayTopUpPoints": today_points, "points": points,
                          "usdPerPoint": p.usd_per_point, "dailyCapUsd": b.daily_cap_usd}
    if not en.can_top_up(gate):
        raise HorizonHTTPError("daily_budget_exceeded",
                               "Top-ups are bounded by today's budget: raise the daily cap in Settings or wait until tomorrow.",
                               details={"todayTopUpPoints": today_points, "points": points})
    wire = await apply_energy(tx, character_id, lambda e: en.top_up(
        e, points, p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points, utc_offset_min=p.utc_offset_min), p)
    await tx.conn.execute(t.usage_records.insert().values(
        id=new_id("use"), at=b.at, local_day=b.local_day, category="energy_topup", purpose=None, character_id=character_id,
        cost_usd=0.0, cost_source="provider", energy_points=float(points), counts_to_creation_cap=False, is_seed=False))
    tx.publish(GLOBAL, {"type": "entity.changed", "kind": "usage"})
    return wire


async def set_max(tx: WriteTx, character_id: str, points: int, p: EnergyParams) -> Energy:
    return await apply_energy(tx, character_id, lambda e: en.with_max(
        e, points, p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points, utc_offset_min=p.utc_offset_min), p)


def now_iso(p: EnergyParams) -> str:
    return iso_from_ms(p.now_ms)
