"""The ledger writer (doc 02 §3.6, doc 04 §2, spend-ledger spec, design D7): the gateway's `LedgerPort`.

- One row per paid call. A reply's energy drain is applied in the SAME writer transaction, under the character's lock
  (taken first): the row and the drain commit together or not at all.
- Text columns pass through the shared redaction before they are stored.
- `spentTodayUsd` = SUM(cost_usd) of today's rows (HORIZON_TZ); creation spend = SUM over a character's
  `counts_to_creation_cap` rows.
- Read helpers for M3: `calls_for_message` (TurnTrace.calls[]) and `reply_usage` (Message.usage).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import tables as t
from horizon.db.uow import Database
from horizon.domain.clock import Clock
from horizon.domain.ids import new_id
from horizon.domain.timeutil import to_iso
from horizon.events.bus import GLOBAL
from horizon.gateway.pipeline import CommitWith, LedgerRow, RecordResult
from horizon.gateway.redact import redact
from horizon.services.energy_writes import EnergyLocks, EnergyParams, apply_energy, drain_change

U = t.usage_records.c


def _r(v: str | None) -> str | None:
    return redact(v) if v else v


class LedgerWriter:
    def __init__(self, db: Database, clock: Clock, locks: EnergyLocks, energy_params: Callable[[], EnergyParams]) -> None:
        self.db = db
        self.clock = clock
        self.locks = locks
        self.energy_params = energy_params

    def today(self) -> str:
        return self.clock.calendar.today(self.clock.now()).isoformat()

    @staticmethod
    async def _sum(conn: AsyncConnection, *where: Any) -> float:
        q = select(func.coalesce(func.sum(U.cost_usd), 0.0))
        for w in where:
            q = q.where(w)
        return float((await conn.execute(q)).scalar_one())

    @classmethod
    async def spent_on(cls, conn: AsyncConnection, local_day: str) -> float:
        return await cls._sum(conn, U.local_day == local_day)

    async def spent_today(self) -> float:
        async with self.db.read() as conn:
            return await self._sum(conn, U.local_day == self.today())

    async def creation_spent(self, character_id: str) -> float:
        async with self.db.read() as conn:
            return await self._sum(conn, U.character_id == character_id, U.counts_to_creation_cap.is_(True))

    async def record(self, row: LedgerRow, *, drain: bool, extra: CommitWith | None = None) -> RecordResult:
        """One row (plus the reply drain) in one writer transaction. `extra(conn, row_id)` runs inside the same
        transaction (a job task's `result_ref`, design D3): if it raises, the row rolls back with it."""
        drained = row.character_id if drain and row.character_id else None
        lock = self.locks.lock(drained) if drained else contextlib.nullcontext()
        async with lock:
            async with self.db.write() as tx:
                now = self.clock.now()
                day = self.clock.calendar.today(now).isoformat()
                before = await self._sum(tx.conn, U.local_day == day)
                creation_before = None
                if row.counts_to_creation_cap and row.character_id:
                    creation_before = await self._sum(tx.conn, U.character_id == row.character_id,
                                                      U.counts_to_creation_cap.is_(True))
                row_id = new_id("use")
                job_id = row.job_id if row.job_id and await self._has(tx.conn, t.generation_jobs, row.job_id) else None
                character_id = (row.character_id if row.character_id and await self._has(tx.conn, t.characters, row.character_id)
                                else None)
                await tx.conn.execute(t.usage_records.insert().values(
                    id=row_id, at=to_iso(now), local_day=day, category=row.category, purpose=row.purpose,
                    model=_r(row.model), provider=_r(row.provider), price_period=row.price_period,
                    generation_id=_r(row.generation_id), session_id=row.session_id, character_id=character_id,
                    job_id=job_id, message_id=row.message_id, tokens_in=row.tokens_in, tokens_cached=row.tokens_cached,
                    tokens_out=row.tokens_out, cost_usd=row.cost_usd, cost_source=row.cost_source,
                    estimated_cost_usd=row.estimated_cost_usd, energy_points=None, latency_ms=row.latency_ms,
                    counts_to_creation_cap=row.counts_to_creation_cap, is_seed=False))
                if drained and await self._exists(tx.conn, drained):
                    await apply_energy(tx, drained, drain_change(row.cost_usd, self.energy_params()), self.energy_params())
                if extra is not None:
                    await extra(tx.conn, row_id)
                tx.publish(GLOBAL, {"type": "entity.changed", "kind": "usage"})
        after_creation = creation_before + row.cost_usd if creation_before is not None else None
        return RecordResult(row_id=row_id, spent_before=before, spent_after=before + row.cost_usd,
                            creation_before=creation_before, creation_after=after_creation)

    @staticmethod
    async def _has(conn: AsyncConnection, table: Any, row_id: str) -> bool:
        """A late row (a shielded call landing after its job or world was deleted) keeps its spend: a reference to a row
        that no longer exists is stored as NULL, like ON DELETE SET NULL would have done (generation-jobs design D6)."""
        return (await conn.execute(select(table.c.id).where(table.c.id == row_id))).first() is not None

    @staticmethod
    async def _exists(conn: AsyncConnection, character_id: str) -> bool:
        """A deleted character keeps its spend in the ledger but has no energy left to drain."""
        q = select(t.characters.c.id).where(t.characters.c.id == character_id).where(t.characters.c.deleted_at.is_(None))
        return (await conn.execute(q)).first() is not None

    # ── reads for M3 (TurnTrace.calls[], Message.usage) ──
    async def calls_for_message(self, message_id: str, since: str | None = None) -> list[dict[str, Any]]:
        """`since` (an ISO instant) keeps one turn's calls when a regenerated message has several turns."""
        q = select(U.purpose, U.model, U.cost_usd, U.latency_ms).where(U.message_id == message_id)
        if since is not None:
            q = q.where(U.at >= since)
        async with self.db.read() as conn:
            rows = (await conn.execute(q.order_by(U.at, U.id))).mappings().all()
        return [{"purpose": r["purpose"] or "", "model": r["model"] or "", "costUsd": round(float(r["cost_usd"]), 6),
                 "latencyMs": int(r["latency_ms"] or 0)} for r in rows]

    async def link_message(self, row_id: str, message_id: str) -> None:
        """A prefetched reply was released as `message_id` (session-runtime D5): link its row (one-row update)."""
        async with self.db.write() as tx:
            await tx.conn.execute(t.usage_records.update().where(U.id == row_id).values(message_id=message_id))

    async def reply_row(self, message_id: str, since: str | None = None) -> dict[str, Any] | None:
        """The reply's ledger row (model, provider, period, latency) for `TurnTrace.model`."""
        q = select(U.model, U.provider, U.price_period, U.latency_ms, U.cost_source).where(
            U.message_id == message_id).where(U.purpose == "reply")
        if since is not None:
            q = q.where(U.at >= since)
        async with self.db.read() as conn:
            r = (await conn.execute(q.order_by(U.at.desc(), U.id.desc()).limit(1))).mappings().first()
        return dict(r) if r is not None else None

    async def reply_usage(self, message_id: str, since: str | None = None) -> dict[str, Any] | None:
        """The reply's tokens and cost (purpose = reply); the actor adds firstTokenMs/totalMs/energySpent in M3."""
        q = select(U.tokens_in, U.tokens_cached, U.tokens_out, U.cost_usd).where(U.message_id == message_id).where(
            U.purpose == "reply")
        if since is not None:
            q = q.where(U.at >= since)
        async with self.db.read() as conn:
            rows = (await conn.execute(q)).mappings().all()
        if not rows:
            return None
        out: dict[str, Any] = {"tokensIn": sum(int(r["tokens_in"] or 0) for r in rows),
                               "tokensOut": sum(int(r["tokens_out"] or 0) for r in rows),
                               "costUsd": round(sum(float(r["cost_usd"]) for r in rows), 6)}
        cached = sum(int(r["tokens_cached"] or 0) for r in rows)
        if cached:
            out["tokensCached"] = cached
        return out
