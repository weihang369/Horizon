"""The cost corrector (doc 04 §2, spend-ledger "Estimates are corrected exactly once", design D7).

A call that was cancelled or broke after it was sent is recorded at its estimate, with its generation ID. This worker
asks OpenRouter for the actual cost (`GET /generation?id=`, free) with backoff, and corrects the row once:
`UPDATE … WHERE id = ? AND cost_source = 'estimate'` (rowcount 1 = it was us). For a reply, the difference in points
goes to the character's energy (drain more, or refund), in the same transaction, followed by `entity.changed`.

- Restart-safe: `scan()` re-enqueues estimate rows with a generation ID that are ≤ 24 h old; older ones keep their
  estimate (spend-ledger "Corrections survive a restart").
- Backoff uses an injected sleeper (default `asyncio.sleep`), never `clock.sleep`: in tests the frozen clock's sleep
  advances shared virtual time, and a background task must never move it (OQ-J). Row age is measured with the Clock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update

from horizon.db import tables as t
from horizon.db.uow import Database
from horizon.domain.clock import Clock
from horizon.domain.energy import points_for_cost
from horizon.domain.timeutil import parse_iso, to_iso
from horizon.gateway.errors import ProviderError
from horizon.gateway.meta import GenerationInfo
from horizon.services.energy_writes import EnergyLocks, EnergyParams, adjust_change, apply_energy

log = logging.getLogger("horizon.corrector")

BACKOFF_S = (2.0, 5.0, 15.0, 60.0, 300.0)   # then every 5 min until the row is 24 h old
MAX_AGE = timedelta(hours=24)
U = t.usage_records.c

Lookup = Callable[[str], Awaitable[GenerationInfo | None]]
Sleeper = Callable[[float], Awaitable[None]]


class CostCorrector:
    def __init__(self, db: Database, clock: Clock, lookup: Lookup, locks: EnergyLocks,
                 energy_params: Callable[[], EnergyParams], *, sleeper: Sleeper = asyncio.sleep,
                 max_attempts: int | None = None) -> None:
        self.db = db
        self.clock = clock
        self.lookup = lookup
        self.locks = locks
        self.energy_params = energy_params
        self.sleeper = sleeper
        self.max_attempts = max_attempts
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._stopped = False

    # ── queue ──
    def enqueue(self, row_id: str) -> None:
        if self._stopped or row_id in self._tasks:
            return  # after stop() (a late shielded record on the way out) the next startup scan() picks the row up
        task = asyncio.get_running_loop().create_task(self._correct(row_id), name=f"correct:{row_id}")
        self._tasks[row_id] = task

        def done(_t: asyncio.Task[None]) -> None:
            self._tasks.pop(row_id, None)

        task.add_done_callback(done)

    @property
    def pending(self) -> int:
        return len(self._tasks)

    async def scan(self) -> int:
        """Startup: resume corrections for recent estimate rows (≤ 24 h)."""
        since = to_iso(self.clock.now() - MAX_AGE)
        async with self.db.read() as conn:
            ids = (await conn.execute(select(U.id).where(U.cost_source == "estimate").where(U.generation_id.is_not(None))
                                      .where(U.at >= since))).scalars().all()
        for rid in ids:
            self.enqueue(str(rid))
        return len(ids)

    async def idle(self) -> None:
        """Wait until every queued correction has finished (tests, shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def stop(self) -> None:
        self._stopped = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()

    # ── one row ──
    async def _row(self, row_id: str) -> Any:
        async with self.db.read() as conn:
            return (await conn.execute(select(t.usage_records).where(U.id == row_id))).mappings().first()

    async def _correct(self, row_id: str) -> None:
        attempt = 0
        while True:
            row = await self._row(row_id)
            if row is None or row["cost_source"] != "estimate" or not row["generation_id"]:
                return
            if self.clock.now() - parse_iso(row["at"]) > MAX_AGE:
                log.info("giving up on correcting %s: older than 24 h", row_id)
                return
            try:
                info = await self.lookup(str(row["generation_id"]))
            except ProviderError as e:
                if e.code in ("missing_key", "invalid_key"):
                    return  # can't look anything up until the key is fixed; the next startup scan retries
                info = None
            except Exception:
                log.exception("generation lookup failed for %s", row_id)
                info = None
            if info is not None:
                await self.apply(row, info)
                return
            if self.max_attempts is not None and attempt + 1 >= self.max_attempts:
                return
            await self.sleeper(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
            attempt += 1

    async def apply(self, row: Any, info: GenerationInfo) -> bool:
        """Correct the row once. Returns False when someone else already did."""
        cid = row["character_id"] if row["purpose"] == "reply" else None
        lock = self.locks.lock(cid) if cid else contextlib.nullcontext()
        async with lock:
            async with self.db.write() as tx:
                values: dict[str, Any] = {"cost_usd": info.cost_usd, "cost_source": "provider"}
                if info.provider and not row["provider"]:
                    values["provider"] = info.provider
                for col, v in (("tokens_in", info.tokens_in), ("tokens_out", info.tokens_out),
                               ("tokens_cached", info.tokens_cached)):
                    if v is not None and row[col] is None:
                        values[col] = v
                res = await tx.conn.execute(update(t.usage_records).where(U.id == row["id"])
                                            .where(U.cost_source == "estimate").values(**values))
                if res.rowcount != 1:
                    return False
                if cid:
                    p = self.energy_params()
                    delta = points_for_cost(info.cost_usd, p.usd_per_point) - points_for_cost(float(row["cost_usd"]), p.usd_per_point)
                    exists = (await tx.conn.execute(select(t.characters.c.id).where(t.characters.c.id == cid)
                                                    .where(t.characters.c.deleted_at.is_(None)))).first()
                    if delta and exists:
                        await apply_energy(tx, cid, adjust_change(delta, p), p)
        return True
