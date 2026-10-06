"""The JobScheduler (doc 01 §4.4; generation-jobs design D2, D4, D5, D6, D12).

- `start(input)` checks, in order, a usable key, a live character, the one-active-job rule and the caps (the whole
  estimate is reserved through `Gateway.reserve_job`) before it stores anything; then the job, its tasks (and, for
  portraits, its `generating` candidates) and the character's `activeJobId` commit in one transaction.
- One runner per non-terminal job, started with `rt.spawn` so the virtual clock settles over it. Each tick
  (`jobTickMs` on the backend clock) it starts queued tasks up to the plan's parallelism, persists progress and
  publishes `job.progress`; a task attempt (`worker.py`) runs as its own spawned task and holds its provider slot
  only around the call.
- The outcome follows the mock: no task queued or running → `succeeded` / `failed` / `partial`, `finishedAt`,
  `activeJobId` cleared, the hold released, `actualCostUsd` = the job's ledger rows, `job.done`.
- `cancel` skips what hasn't been sent; a call already sent finishes (shielded) at its real cost and its result is
  kept but not applied (D-86). `retry` re-reserves one task's estimate (the only way a task is sent again).
- `recover()` (startup step 6): never sent → queued; result stored → derive and apply only; sent with no result →
  `failed`, retryable. Then the remaining estimate is reserved again and the runner starts.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.api.errors import conflict, not_found, validation
from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.domain.timeutil import ms_from_iso
from horizon.events.bus import GLOBAL
from horizon.gateway.context import CallContext, call_ctx
from horizon.services import assets
from horizon.services.jobs import plans
from horizon.services.reads import get_job

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.jobs")

J = t.generation_jobs.c
T = t.generation_tasks.c
C = t.characters.c
ACTIVE = ("queued", "running")
TERMINAL_TASK = ("succeeded", "failed", "skipped")
INTERRUPTED = "Interrupted after the request was sent; Retry to pay again."
FAULT_MESSAGE = {"image": "The image provider returned an error.", "music": "The music provider returned an error."}
EDIT_KINDS = frozenset({"emotion_set", "emotion_regenerate", "portrait_tweak"})
STOP_WAIT_S = 5.0


@dataclass
class Attempt:
    task_id: str
    started_ms: float
    expected_ms: float
    fault: bool
    sent: bool = False
    handle: asyncio.Task[None] | None = None


@dataclass
class Run:
    job_id: str
    character_id: str
    world_id: str
    kind: str
    input: dict[str, Any]
    parallel: int
    sheet: bool
    fault: str | None
    fail_plan: set[str] = field(default_factory=set)
    cancelled: bool = False
    wait_first: bool = False   # a recovered job starts on the first tick, so startup itself never races a request
    deleted: bool = False   # the character is being deleted: a late answer is billed but its original isn't kept
    attempts: dict[str, Attempt] = field(default_factory=dict)
    loop: asyncio.Task[None] | None = None


def round3(x: float) -> float:
    """JS `Math.round(x * 1000) / 1000`."""
    return math.floor(x * 1000 + 0.5) / 1000


class JobScheduler:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.runs: dict[str, Run] = {}
        self.stopping = False
        self._shielded: set[asyncio.Task[Any]] = set()

    async def shielded(self, name: str, coro: Coroutine[Any, Any, None]) -> None:
        """Run a write a cancel must not interrupt. It is tracked, so stop() waits for it before the database is
        disposed (an untracked one would reopen `horizon.db` and block a factory reset's wipe on Windows)."""
        task = self.rt.spawn(name, coro)
        self._shielded.add(task)
        task.add_done_callback(self._shielded.discard)
        await asyncio.shield(task)

    # ── helpers ──
    @property
    def timing(self) -> Any:
        return self.rt.runtime_cfg.jobs

    def lean(self) -> bool:
        return str(self.rt.settings_doc().get("generationMode", "lean")) == "lean"

    def now_ms(self) -> float:
        return float(ms_from_iso(self.rt.now_iso()))

    def ctx(self, purpose: str, *, category: str, world_id: str, character_id: str, job_id: str,
            creation: bool) -> CallContext:
        return call_ctx(purpose, category=category, world_id=world_id, character_id=character_id,  # type: ignore[arg-type]
                        job_id=job_id, creation=creation)

    async def _job_wire(self, conn: AsyncConnection, job_id: str) -> dict[str, Any]:
        return await get_job(conn, job_id)

    def _publish_task(self, tx: Any, job_id: str, task_row: Mapping[str, Any]) -> None:
        from horizon.contract import mappers as mp

        tx.publish(GLOBAL, {"type": "task.update", "jobId": job_id, "task": mp.task_wire(task_row)})

    async def _task_rows(self, conn: AsyncConnection, job_id: str) -> list[Any]:
        return list((await conn.execute(select(t.generation_tasks).where(T.job_id == job_id).order_by(T.ord)))
                    .mappings().all())

    # ── estimate / start ──
    def plan(self, job_input: Mapping[str, Any]) -> plans.JobPlan:
        try:
            return plans.plan(job_input, lean=self.lean(), prices=self.rt.prices.generation, timing=self.timing)
        except ValueError as e:
            raise validation(str(e), {"field": "kind"}) from e

    async def estimate(self, job_input: Mapping[str, Any]) -> float:
        async with self.rt.db.read() as conn:
            await self._live(conn, str(job_input["characterId"]))
        return self.plan(job_input).estimate

    @staticmethod
    async def _live(conn: AsyncConnection, character_id: str) -> Any:
        row = (await conn.execute(select(t.characters).where(C.id == character_id))).mappings().first()
        if row is None or row["deleted_at"] is not None:
            raise not_found("Character")
        return row

    async def _check_base(self, conn: AsyncConnection, ch: Mapping[str, Any], kind: str) -> None:
        """OQ-2: a naive edit needs a raster base portrait; a seed SVG placeholder can't be sent to the image model."""
        if kind not in EDIT_KINDS or self.rt.ai.impl("image", key_set=True) != "naive":
            return
        a = t.image_assets.c
        neutral = (await conn.execute(select(a.rel_path).where(and_(
            a.character_id == ch["id"], a.kind == "emotion", a.emotion == "neutral", a.variant == "default",
            a.is_active.is_(True))))).scalar()
        if not neutral:
            raise validation("Lock a base portrait first.", {"field": "characterId", "reason": "no_base"})
        if not str(neutral).lower().endswith((".webp", ".png", ".jpg", ".jpeg")):
            raise validation("This character's base portrait is a placeholder drawing that the image model can't edit. "
                             "Generate and lock a new portrait first.", {"field": "characterId", "reason": "base_not_raster"})

    async def start(self, job_input: dict[str, Any]) -> dict[str, Any]:
        self.rt.gateway.core.require_key()
        cid = str(job_input["characterId"])
        async with self.rt.db.read() as conn:
            ch = await self._live(conn, cid)
            await self._check_base(conn, ch, str(job_input["kind"]))
            active = (await conn.execute(select(J.id).where(and_(J.character_id == cid, J.status.in_(ACTIVE))))).first()
        if active is not None:
            raise conflict("This character already has a generation job running.", {"activeJobId": active[0]})
        plan = self.plan(job_input)
        job_id = new_id("job")
        await self._reserve(ch, job_id, plan.estimate, existing=False)
        try:
            async with self.rt.db.write() as tx:
                ch2 = await self._live(tx.conn, cid)
                await self.insert_job(tx, ch2, job_id, job_input, plan)
        except IntegrityError as e:
            self.rt.book.release_job(job_id)
            raise conflict("This character already has a generation job running.") from e
        except BaseException:
            self.rt.book.release_job(job_id)
            raise
        self.launch(job_id)
        if job_input["kind"] == "song":
            self.rt.spawn(f"music-probe:{job_id}", self._probe_music())
        async with self.rt.db.read() as conn:
            return await self._job_wire(conn, job_id)

    async def _probe_music(self) -> None:
        """D-83: a free check that the configured music model is listed, logged once per song job start."""
        model = str(self.rt.settings_doc()["models"].get("music", ""))
        try:
            listed = await self.rt.gateway.meta.model_exists(model)
        except Exception as e:  # informational only
            log.info("music model check failed for %s: %s", model, type(e).__name__)
            return
        log.info("music model %s is %s on OpenRouter; the song job uses the procedural theme (D-83)", model,
                 "listed" if listed else "not listed")

    async def _reserve(self, ch: Mapping[str, Any], job_id: str, amount: float, *, existing: bool) -> None:
        ctx = self.ctx("job", category="image", world_id=ch["world_id"], character_id=ch["id"], job_id=job_id,
                       creation=ch["status"] != "approved")
        await self.rt.gateway.reserve_job(ctx, amount, existing=existing)

    async def insert_job(self, tx: Any, ch: Mapping[str, Any], job_id: str, job_input: Mapping[str, Any],
                         plan: plans.JobPlan) -> None:
        """The job, its tasks, any `generating` candidates and `activeJobId`, in the caller's transaction."""
        now = self.rt.now_iso()
        conn = tx.conn
        stored = {k: v for k, v in job_input.items() if v is not None}
        await conn.execute(t.generation_jobs.insert().values(
            id=job_id, character_id=ch["id"], kind=stored["kind"], target_field=stored.get("targetField"), status="queued",
            progress=0.0, estimated_cost_usd=plan.estimate, actual_cost_usd=0.0, input=stored, error=None, is_seed=False,
            created_at=now, started_at=None, finished_at=None))
        task_ids: list[str] = []
        for i, tp in enumerate(plan.tasks):
            tid = new_id("task")
            task_ids.append(tid)
            await conn.execute(t.generation_tasks.insert().values(
                id=tid, job_id=job_id, ord=i, type=tp.type, emotion=tp.emotion, status="queued", attempt=0, max_attempts=3,
                idempotency_key=f"{job_id}:{i}", provider_called_at=None, target_path=None, result_ref=None,
                preview_url=None, cost_usd=None, error=None, created_at=now, started_at=None, finished_at=None))
        if stored["kind"] in ("portrait_candidates", "portrait_tweak"):
            await assets.insert_candidates(conn, world_id=ch["world_id"], character_id=ch["id"], job_id=job_id,
                                           task_ids=task_ids, now=now)
        await conn.execute(update(t.characters).where(C.id == ch["id"]).values(active_job_id=job_id, updated_at=now))
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "job", "id": job_id})
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "character", "id": ch["id"], "worldId": ch["world_id"]})

    # ── the runner ──
    def launch(self, job_id: str, *, fault: str | bool | None = True, wait_first: bool = False) -> None:
        """Start (or adopt) the runner for a stored non-terminal job. `fault=True` takes the current scenario fault."""
        if self.stopping or job_id in self.runs:
            return
        run = Run(job_id=job_id, character_id="", world_id="", kind="", input={}, parallel=1, sheet=False,
                  fault=self.rt.job_faults if fault is True else (fault or None), wait_first=wait_first)
        self.runs[job_id] = run
        run.loop = self.rt.spawn(f"job:{job_id}", self._run(run))

    async def _load_run(self, run: Run) -> bool:
        async with self.rt.db.read() as conn:
            job = (await conn.execute(select(t.generation_jobs).where(J.id == run.job_id))).mappings().first()
            if job is None or job["status"] not in ACTIVE:
                return False
            ch = (await conn.execute(select(t.characters).where(C.id == job["character_id"]))).mappings().first()
            tasks = await self._task_rows(conn, run.job_id)
        if ch is None:
            return False
        run.character_id, run.world_id, run.kind = ch["id"], ch["world_id"], job["kind"]
        run.input = dict(job["input"] or {"characterId": ch["id"], "kind": job["kind"]})
        run.sheet = any(x["type"] == "expression_sheet" for x in tasks)
        run.parallel = plans.parallel_for(run.kind, self.timing, sheet_job=run.sheet)
        run.fail_plan = self.fail_plan(run.fault, tasks)
        return True

    @staticmethod
    def fail_plan(fault: str | None, tasks: list[Any]) -> set[str]:
        """The mock's scenario faults (design D12): `all` every image task, `partial` the second image task (first
        attempt only), `song` theme-song tasks (first attempt only)."""
        images = [x["id"] for x in tasks if x["type"] in ("portrait_candidate", "emotion_image", "expression_sheet")]
        if fault == "all":
            return set(images)
        if fault == "partial" and images:
            return {images[1] if len(images) > 1 else images[0]}
        if fault == "song":
            return {x["id"] for x in tasks if x["type"] == "theme_song"}
        return set()

    def faults_now(self, run: Run, task_id: str, attempt: int) -> bool:
        if task_id not in run.fail_plan:
            return False
        return run.fault == "all" or attempt <= 1

    async def _run(self, run: Run) -> None:
        try:
            if not await self._load_run(run):
                return
            tick = self.timing.job_tick_ms / 1000
            if run.wait_first:
                await self.rt.clock.sleep(tick)
                if getattr(self.rt.clock, "frozen", False):
                    # Test mode: the HTTP harness freezes the clock right after a reset, while this first tick was a
                    # real sleep. Wait for virtual time too, so the overlay job only moves when a test advances it.
                    await self.rt.clock.sleep(tick)
            while not run.cancelled:
                state = await self._start_ready(run)
                if state == "gone":
                    return
                if state == "done":
                    await self._finish(run)
                    return
                await self.rt.clock.sleep(tick)
                if run.cancelled:
                    return
                state = await self._progress(run)
                if state == "gone":
                    return
                if state == "done":
                    await self._finish(run)
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("job runner %s failed", run.job_id)
        finally:
            if self.runs.get(run.job_id) is run:
                del self.runs[run.job_id]

    async def _start_ready(self, run: Run) -> str:
        from horizon.services.jobs.worker import run_attempt

        started: list[Attempt] = []
        async with self.rt.db.write() as tx:
            job = (await tx.conn.execute(select(t.generation_jobs).where(J.id == run.job_id))).mappings().first()
            if job is None or job["status"] not in ACTIVE:
                return "gone"
            tasks = await self._task_rows(tx.conn, run.job_id)
            pending = [x for x in tasks if x["status"] in ACTIVE]
            if not pending and not run.attempts:
                return "done"
            now = self.rt.now_iso()
            if job["status"] == "queued":
                await tx.conn.execute(update(t.generation_jobs).where(J.id == run.job_id).values(
                    status="running", started_at=job["started_at"] or now))
            busy = sum(1 for x in tasks if x["status"] == "running")
            for x in tasks:  # a recovered task with a stored result: finish it from the original, no call
                if x["status"] == "running" and x["id"] not in run.attempts and x["result_ref"]:
                    started.append(Attempt(task_id=x["id"], started_ms=self.now_ms(), expected_ms=0.0, fault=False,
                                           sent=True))
            for x in tasks:
                if busy >= run.parallel:
                    break
                if x["status"] != "queued" or x["id"] in run.attempts:
                    continue
                if run.sheet and x["type"] == "emotion_image":
                    continue  # sliced from the sheet
                attempt = int(x["attempt"]) + 1
                await tx.conn.execute(update(t.generation_tasks).where(T.id == x["id"]).values(
                    status="running", attempt=attempt, started_at=now, error=None))
                self._publish_task(tx, run.job_id, {**x, "status": "running", "attempt": attempt, "error": None})
                started.append(Attempt(task_id=x["id"], started_ms=self.now_ms(), expected_ms=0.0,
                                       fault=self.faults_now(run, x["id"], attempt)))
                busy += 1
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "job", "id": run.job_id})
        for a in started:
            run.attempts[a.task_id] = a
            a.handle = self.rt.spawn(f"task:{a.task_id}", run_attempt(self, run, a))
        return "running"

    async def _progress(self, run: Run) -> str:
        now = self.now_ms()
        async with self.rt.db.write() as tx:
            job = (await tx.conn.execute(select(t.generation_jobs).where(J.id == run.job_id))).mappings().first()
            if job is None or job["status"] not in ACTIVE:
                return "gone"
            tasks = await self._task_rows(tx.conn, run.job_id)
            if not any(x["status"] in ACTIVE for x in tasks) and not run.attempts:
                return "done"
            total = 0.0
            for x in tasks:
                if x["status"] in TERMINAL_TASK:
                    total += 1
                elif x["status"] == "running":
                    a = run.attempts.get(x["id"])
                    if a is not None and a.expected_ms > 0:
                        cap = 0.6 if a.fault else 0.95
                        total += min(cap, max(0.0, (now - a.started_ms) / a.expected_ms))
            progress = round3(total / max(1, len(tasks)))
            await tx.conn.execute(update(t.generation_jobs).where(J.id == run.job_id).values(progress=progress))
            wire = await self._job_wire(tx.conn, run.job_id)
            # job.progress carries the whole job; no entity.changed per tick (it made clients refetch 4×/s).
            tx.publish(GLOBAL, {"type": "job.progress", "job": wire})
        return "running"

    async def _actual(self, conn: AsyncConnection, job_id: str) -> float:
        u = t.usage_records.c
        return round(float((await conn.execute(select(func.coalesce(func.sum(u.cost_usd), 0.0))
                                                .where(u.job_id == job_id))).scalar_one()), 6)

    async def _finish(self, run: Run) -> None:
        async with self.rt.db.write() as tx:
            job = (await tx.conn.execute(select(t.generation_jobs).where(J.id == run.job_id))).mappings().first()
            if job is None or job["status"] not in ACTIVE:
                return
            tasks = await self._task_rows(tx.conn, run.job_id)
            ok = sum(1 for x in tasks if x["status"] == "succeeded")
            failed = sum(1 for x in tasks if x["status"] == "failed")
            status = "succeeded" if failed == 0 else "failed" if ok == 0 else "partial"
            error = {"code": "provider_error", "message": "Generation failed."} if status == "failed" else None
            now = self.rt.now_iso()
            await tx.conn.execute(update(t.generation_jobs).where(J.id == run.job_id).values(
                status=status, progress=1.0, finished_at=now, error=error, actual_cost_usd=await self._actual(tx.conn, run.job_id)))
            name = await self._release_character(tx, run.job_id, job["character_id"], now)
            wire = await self._job_wire(tx.conn, run.job_id)
            done: dict[str, Any] = {"type": "job.done", "job": wire}
            if name:
                done["characterName"] = name
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "job", "id": run.job_id})
            tx.publish(GLOBAL, done)
        self.rt.book.release_job(run.job_id)

    async def _release_character(self, tx: Any, job_id: str, character_id: str, now: str) -> str | None:
        ch = (await tx.conn.execute(select(t.characters).where(C.id == character_id))).mappings().first()
        if ch is None:
            return None
        values: dict[str, Any] = {"updated_at": now}
        if ch["active_job_id"] == job_id:
            values["active_job_id"] = None
        await tx.conn.execute(update(t.characters).where(C.id == character_id).values(**values))
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "character", "id": character_id, "worldId": ch["world_id"]})
        name = (ch["profile"] or {}).get("name")
        return str(name) if name else None

    # ── cancel / retry ──
    async def cancel(self, job_id: str) -> dict[str, Any]:
        async with self.rt.db.read() as conn:
            job = (await conn.execute(select(t.generation_jobs).where(J.id == job_id))).mappings().first()
        if job is None:
            raise not_found("Job")
        if job["status"] not in ACTIVE:
            async with self.rt.db.read() as conn:
                return await self._job_wire(conn, job_id)
        run = self.runs.get(job_id)
        if run is not None:
            run.cancelled = True
            for a in list(run.attempts.values()):
                if not a.sent and a.handle is not None:
                    a.handle.cancel()  # nothing was sent: drop it (a sent call finishes, shielded)
        async with self.rt.db.write() as tx:
            await self.mark_cancelled(tx, job_id)
            wire = await self._job_wire(tx.conn, job_id)
        self.rt.book.release_job(job_id)
        return wire

    async def mark_cancelled(self, tx: Any, job_id: str) -> None:
        now = self.rt.now_iso()
        job = (await tx.conn.execute(select(t.generation_jobs).where(J.id == job_id))).mappings().first()
        if job is None or job["status"] not in ACTIVE:
            return
        for x in await self._task_rows(tx.conn, job_id):
            if x["status"] in ACTIVE:
                await tx.conn.execute(update(t.generation_tasks).where(T.id == x["id"]).values(status="skipped", finished_at=now))
                if x["type"] == "portrait_candidate":
                    await assets.fail_candidate(tx.conn, x["id"])
                self._publish_task(tx, job_id, {**x, "status": "skipped"})
        await tx.conn.execute(update(t.generation_jobs).where(J.id == job_id).values(
            status="cancelled", finished_at=now, actual_cost_usd=await self._actual(tx.conn, job_id)))
        name = await self._release_character(tx, job_id, job["character_id"], now)
        wire = await self._job_wire(tx.conn, job_id)
        done: dict[str, Any] = {"type": "job.done", "job": wire}
        if name:
            done["characterName"] = name
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "job", "id": job_id})
        tx.publish(GLOBAL, done)

    async def retry(self, job_id: str, task_id: str) -> dict[str, Any]:
        self.rt.gateway.core.require_key()
        async with self.rt.db.read() as conn:
            job = (await conn.execute(select(t.generation_jobs).where(J.id == job_id))).mappings().first()
            task = (await conn.execute(select(t.generation_tasks).where(and_(T.id == task_id, T.job_id == job_id)))) \
                .mappings().first()
            if job is None:
                raise not_found("Job")
            if task is None:
                raise not_found("Task")
            ch = await self._live(conn, job["character_id"])
            sheet = (await conn.execute(select(T.id).where(and_(T.job_id == job_id, T.type == "expression_sheet")))).first()
        if task["status"] != "failed":
            raise conflict("Only a failed task can be retried.", {"status": task["status"]})
        if int(task["attempt"]) >= int(task["max_attempts"]):
            raise conflict("This task has used all its retries.", {"attempt": task["attempt"]})
        spec = plans.task_spec(job["kind"], task["type"], task["emotion"], sheet_job=sheet is not None,
                               prices=self.rt.prices.generation, timing=self.timing)
        await self._reserve(ch, job_id, spec.est_usd, existing=True)
        try:
            async with self.rt.db.write() as tx:
                now = self.rt.now_iso()
                await tx.conn.execute(update(t.generation_tasks).where(T.id == task_id).values(
                    status="queued", error=None, finished_at=None, provider_called_at=None, result_ref=None))
                if task["type"] == "portrait_candidate":
                    await tx.conn.execute(update(t.image_assets).where(t.image_assets.c.id == assets.cand_id_for(task_id))
                                          .values(status="generating"))
                await tx.conn.execute(update(t.generation_jobs).where(J.id == job_id).values(
                    status="running", finished_at=None, error=None))
                await tx.conn.execute(update(t.characters).where(C.id == ch["id"]).values(active_job_id=job_id, updated_at=now))
                self._publish_task(tx, job_id, {**task, "status": "queued", "error": None, "result_ref": None})
                tx.publish(GLOBAL, {"type": "entity.changed", "kind": "job", "id": job_id})
                tx.publish(GLOBAL, {"type": "entity.changed", "kind": "character", "id": ch["id"], "worldId": ch["world_id"]})
                wire = await self._job_wire(tx.conn, job_id)
        except IntegrityError as e:
            self.rt.book.release_job(job_id)
            raise conflict("This character already has another generation job running.") from e
        run = self.runs.get(job_id)
        if run is None:
            self.launch(job_id)
        return wire

    # ── delete support ──
    async def cancel_for_character(self, character_id: str) -> None:
        """Cancel the character's non-terminal job (a delete) and wait (bounded) for its runner to stop or reach a sent
        call. A call already sent still lands in the ledger, but its original is not stored for a deleted character."""
        async with self.rt.db.read() as conn:
            ids = [r[0] for r in await conn.execute(select(J.id).where(and_(J.character_id == character_id,
                                                                           J.status.in_(ACTIVE))))]
        for live in self.runs.values():
            if live.character_id == character_id:
                live.deleted = True
        for job_id in ids:
            await self.cancel(job_id)
            run = self.runs.get(job_id)
            if run is not None and run.loop is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(asyncio.shield(run.loop), STOP_WAIT_S)

    # ── demo reset (demo-data "Reset demo data restores seed records only") ──
    async def before_reset(self, seed_characters: set[str], seed_jobs: set[str]) -> None:
        """Cancel user jobs on seed characters; halt the shipped overlay jobs, whose rows the reset replaces (they are
        re-adopted by `recover()` afterwards)."""
        async with self.rt.db.read() as conn:
            active = (await conn.execute(select(J.id, J.character_id).where(J.status.in_(ACTIVE)))).all()
        for job_id, character_id in active:
            if job_id in seed_jobs:
                await self.halt(job_id)
            elif character_id in seed_characters:
                await self.cancel(job_id)

    async def halt(self, job_id: str) -> None:
        """Stop a runner without touching its rows (a sent call is recorded at its estimate by the gateway)."""
        run = self.runs.pop(job_id, None)
        if run is None:
            return
        run.cancelled = True
        handles = [h for h in (run.loop, *(a.handle for a in run.attempts.values())) if h is not None]
        for h in handles:
            h.cancel()
        if handles:
            with contextlib.suppress(Exception):
                await asyncio.wait(handles, timeout=STOP_WAIT_S)
        self.rt.book.release_job(job_id)

    # ── recovery (startup step 6) ──
    async def recover(self) -> list[str]:
        """Design D4. Returns the recovered job IDs (their runners are started)."""
        async with self.rt.db.read() as conn:
            jobs = (await conn.execute(select(t.generation_jobs).where(J.status.in_(ACTIVE)).order_by(J.created_at)))\
                .mappings().all()
        recovered: list[str] = []
        for job in jobs:
            if job["id"] in self.runs:
                continue  # already running in this process (a demo reset re-adopts only what it replaced)
            async with self.rt.db.write() as tx:
                ch = (await tx.conn.execute(select(t.characters).where(C.id == job["character_id"]))).mappings().first()
                if ch is None or ch["deleted_at"] is not None:
                    await self.mark_cancelled(tx, job["id"])
                    continue
                now = self.rt.now_iso()
                for x in await self._task_rows(tx.conn, job["id"]):
                    if x["status"] == "queued" or (x["status"] == "running" and x["provider_called_at"] is None):
                        if x["status"] == "running":  # never sent: the attempt doesn't count
                            await tx.conn.execute(update(t.generation_tasks).where(T.id == x["id"]).values(
                                status="queued", attempt=max(0, int(x["attempt"]) - 1), started_at=None))
                    elif x["status"] == "running" and x["result_ref"] is None:
                        err = {"code": "provider_error", "message": INTERRUPTED, "retryable": True}
                        await tx.conn.execute(update(t.generation_tasks).where(T.id == x["id"]).values(
                            status="failed", error=err, finished_at=now))
                        if x["type"] == "portrait_candidate":
                            await assets.fail_candidate(tx.conn, x["id"])
                        self._publish_task(tx, job["id"], {**x, "status": "failed", "error": err})
                # `running` with a stored result stays running: the worker finishes it from the original (no call).
            remaining = await self._remaining_estimate(job["id"], job["kind"])
            async with self.rt.db.read() as conn:
                chrow = (await conn.execute(select(t.characters).where(C.id == job["character_id"]))).mappings().first()
            if chrow is not None and remaining > 0:
                ctx = self.ctx("job", category="image", world_id=chrow["world_id"], character_id=chrow["id"],
                               job_id=job["id"], creation=chrow["status"] != "approved")
                held = self.rt.book.job_remaining(job["id"])  # not a cap check: an over-cap task fails at its preflight
                self.rt.book.reserve_job(job["id"], held + remaining, character_id=ctx.character_id, creation=ctx.creation)
            self.launch(job["id"], wait_first=True)
            recovered.append(job["id"])
        return recovered

    async def _remaining_estimate(self, job_id: str, kind: str) -> float:
        async with self.rt.db.read() as conn:
            tasks = await self._task_rows(conn, job_id)
        sheet = any(x["type"] == "expression_sheet" for x in tasks)
        return sum(plans.task_spec(kind, x["type"], x["emotion"], sheet_job=sheet, prices=self.rt.prices.generation,
                                   timing=self.timing).est_usd for x in tasks if x["status"] == "queued")

    # ── shutdown ──
    async def stop(self) -> None:
        """Stop every runner and attempt (shutdown, factory reset). A call already sent is recorded at its estimate by
        the gateway's shielded write (no spend is lost), and on the next start its task is failed and retryable."""
        self.stopping = True
        runs = list(self.runs.values())
        for run in runs:
            run.cancelled = True
            for a in run.attempts.values():
                if a.handle is not None:
                    a.handle.cancel()
            if run.loop is not None:
                run.loop.cancel()
        handles = [h for run in runs for h in [run.loop, *(a.handle for a in run.attempts.values())] if h is not None]
        if handles:
            with contextlib.suppress(Exception):
                await asyncio.wait(handles, timeout=STOP_WAIT_S)
        while self._shielded:
            await asyncio.gather(*list(self._shielded), return_exceptions=True)
        self.runs.clear()
