"""The reservation book (doc backend/04 §3, budget-caps "Calls in flight are reserved"): in memory, empty after restart.

Preflight reserves a call's estimate and settling releases it, so concurrent calls see each other's spend before any
of it reaches the ledger. `lock` makes check-and-reserve atomic (the pipeline awaits the ledger SUM inside it). A job
reserves its whole remaining estimate up front (`reserve_job`) and hands it to its steps one by one (`take_from_job`),
releasing what's left at the end (`release_job`).
"""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass


@dataclass
class Hold:
    id: int
    amount: float
    character_id: str | None
    creation: bool


@dataclass
class JobHold:
    job_id: str
    remaining: float
    character_id: str | None
    creation: bool


class ReservationBook:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self._holds: dict[int, Hold] = {}
        self._jobs: dict[str, JobHold] = {}
        self._ids = itertools.count(1)

    # ── totals ──
    def total(self) -> float:
        return sum(h.amount for h in self._holds.values()) + sum(j.remaining for j in self._jobs.values())

    def reserved_for(self, character_id: str) -> float:
        """What is held against a character's creation cap."""
        calls = sum(h.amount for h in self._holds.values() if h.creation and h.character_id == character_id)
        jobs = sum(j.remaining for j in self._jobs.values() if j.creation and j.character_id == character_id)
        return calls + jobs

    def job_remaining(self, job_id: str) -> float:
        j = self._jobs.get(job_id)
        return j.remaining if j else 0.0

    # ── single calls ──
    def reserve(self, amount: float, *, character_id: str | None = None, creation: bool = False) -> Hold:
        h = Hold(next(self._ids), max(0.0, amount), character_id, creation)
        self._holds[h.id] = h
        return h

    def release(self, hold: Hold | None) -> None:
        if hold is not None:
            self._holds.pop(hold.id, None)

    # ── jobs (M4) ──
    def reserve_job(self, job_id: str, amount: float, *, character_id: str | None = None, creation: bool = False) -> JobHold:
        j = JobHold(job_id, max(0.0, amount), character_id, creation)
        self._jobs[job_id] = j
        return j

    def take_from_job(self, job_id: str, amount: float) -> float:
        """Move up to `amount` out of the job's hold (a step is starting); returns how much was moved."""
        j = self._jobs.get(job_id)
        if j is None:
            return 0.0
        moved = min(j.remaining, max(0.0, amount))
        j.remaining -= moved
        return moved

    def release_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def clear(self) -> None:
        self._holds.clear()
        self._jobs.clear()
