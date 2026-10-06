"""One task attempt (generation-jobs design D3): the never-pay-twice order.

| step | durable effect |
|---|---|
| 1. preflight (caps; the task's share of the job hold) | none |
| 2. `before_send`: commit `provider_called_at` and the original's path | the task is marked as sent |
| 3. the provider call (the scripted source paces here instead) | the provider charges |
| 4. `after_response`: write the original atomically under `data/originals/` | the original is on disk |
| 5. the ledger row **and** `result_ref` commit together (`commit_with`) | the paid result is recorded |
| 6. derive the WebP, then apply in one transaction (asset row, character change, task `succeeded`) | done |

A scenario fault fails the attempt at 60 % of its paced duration, before step 1, so it costs nothing. A task whose
job was cancelled after step 2 finishes its call (its spend is recorded) but its result is kept, not applied (D-86).
After a restart, a task with a stored result resumes at step 6 with no call.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.image_prompt import CompiledPrompt, ImagePromptCompiler
from horizon.ai.ports import ImageJob, PaidHooks
from horizon.api.errors import DEFAULT_RETRYABLE
from horizon.db import tables as t
from horizon.events.bus import GLOBAL
from horizon.gateway.errors import ProviderError
from horizon.services import assets
from horizon.services.jobs import apply as ap
from horizon.services.jobs import plans
from horizon.storage.atomic import write_atomic
from horizon.storage.images import EXT, ImageRejected, TooLarge, portrait_webp, sheet_cells, sniff

if TYPE_CHECKING:
    from horizon.services.jobs.scheduler import Attempt, JobScheduler, Run

log = logging.getLogger("horizon.jobs")

T = t.generation_tasks.c
J = t.generation_jobs.c
PURPOSE = {"portrait_candidate": "image_portrait", "emotion_image": "image_emotion", "blink_frame": "image_blink",
           "expression_sheet": "image_sheet"}
PROFILE_PARTS = ("profile", "appearance_summary", "palette_pick", "song_brief")


class Fault(Exception):
    """A test-mode scenario failure (design D12)."""


class Refused(Exception):
    """The prompt compiler refused (an under-18 character): fail without a call."""


async def run_attempt(sched: JobScheduler, run: Run, a: Attempt) -> None:
    rt = sched.rt
    try:
        async with rt.db.read() as conn:
            task = (await conn.execute(select(t.generation_tasks).where(T.id == a.task_id))).mappings().first()
            ch = await ap.live_character(conn, run.character_id)
        if task is None or ch is None:
            return
        if a.sent and task["result_ref"]:  # recovered with a stored original: derive and apply only
            await finish(sched, run, dict(task), resume=True)
            return
        spec = plans.task_spec(run.kind, task["type"], task["emotion"], sheet_job=run.sheet,
                               prices=rt.prices.generation, timing=sched.timing)
        a.expected_ms = expected_ms(sched, spec, task["type"])
        if a.fault:
            await rt.clock.sleep(0.6 * a.expected_ms / 1000)
            raise Fault()
        await call(sched, run, a, dict(task), dict(ch), spec)
        if run.cancelled:
            return  # cancelled after it was sent: the spend and the original are kept, nothing is applied
        async with rt.db.read() as conn:
            task = (await conn.execute(select(t.generation_tasks).where(T.id == a.task_id))).mappings().first()
        if task is not None:
            await finish(sched, run, dict(task), resume=False)
    except asyncio.CancelledError:
        raise
    except Fault:
        kind = "music" if run.kind == "song" else "image"
        await fail(sched, run, a.task_id, "provider_error", plans_message(kind), True)
    except Refused as e:
        await fail(sched, run, a.task_id, "content_refused", str(e), False)
    except ProviderError as e:
        await fail(sched, run, a.task_id, e.code, e.message, DEFAULT_RETRYABLE.get(e.code, True))
    except (ImageRejected, TooLarge) as e:
        log.warning("task %s: unusable image (%s)", a.task_id, e)
        await fail(sched, run, a.task_id, "provider_error", "The image provider returned an image we couldn't use.", True)
    except Exception:
        log.exception("task %s failed", a.task_id)
        await fail(sched, run, a.task_id, "provider_error", "Generation failed.", True)
    finally:
        run.attempts.pop(a.task_id, None)


def plans_message(kind: str) -> str:
    return "The music provider returned an error." if kind == "music" else "The image provider returned an error."


def expected_ms(sched: JobScheduler, spec: plans.TaskPlan, type_: str) -> float:
    rt = sched.rt
    if type_ in PROFILE_PARTS:
        drafter = rt.ai.drafter(True)
        return float(drafter.expected_ms(spec.duration_ms)) if type_ == "profile" or not drafter.shared_call else 0.0
    if type_ == "theme_song":
        return spec.duration_ms if song_paced(sched) else 0.0
    if spec.duration_ms <= 0:
        return 0.0
    image = rt.ai.image(True)
    mode = "sheet" if type_ == "expression_sheet" else "base" if type_ == "portrait_candidate" else "edit"
    probe = ImageJob(task_id="", mode=mode, prompt="", model="", price_kind=spec.price_kind or "portrait",
                     duration_ms=spec.duration_ms, label="", palette=("", "", ""))
    return float(image.expected_ms(probe))


def song_paced(sched: JobScheduler) -> bool:
    """The procedural theme costs nothing; it is paced like the mock's song only in the scripted profile."""
    return sched.rt.ai.impl("drafter", key_set=True) == "scripted"


# ── step 1–5: the call ──
def task_ctx(sched: JobScheduler, run: Run, ch: Mapping[str, Any], type_: str) -> Any:
    creation = ch["status"] != "approved"
    if type_ in PROFILE_PARTS:
        return sched.ctx("profile", category="profile", world_id=run.world_id, character_id=run.character_id,
                         job_id=run.job_id, creation=creation)
    purpose = "image_tweak" if run.kind == "portrait_tweak" else PURPOSE[type_]
    return sched.ctx(purpose, category="image", world_id=run.world_id, character_id=run.character_id, job_id=run.job_id,
                     creation=creation)


def hooks_for(sched: JobScheduler, run: Run, a: Attempt, task: Mapping[str, Any], ch: Mapping[str, Any]) -> PaidHooks:
    rt = sched.rt
    stem = assets.original_rel(ch["world_id"], ch["id"], task["id"], int(task["attempt"]), "x")[:-2]
    stored: dict[str, str] = {}

    async def before_send() -> None:
        async def mark() -> None:
            async with rt.db.write() as tx:
                await tx.conn.execute(update(t.generation_tasks).where(T.id == task["id"]).values(
                    provider_called_at=rt.now_iso(), target_path=stem))
        await sched.shielded(f"mark:{task['id']}", mark())
        a.sent = True

    async def after_response(value: Any) -> None:
        if run.deleted:
            return  # the character was deleted while this call was in flight: bill it, keep nothing
        if isinstance(value, bytes | bytearray):
            data, ext = bytes(value), EXT.get(sniff(bytes(value)) or "png", "png")
        else:
            data, ext = json.dumps(value, ensure_ascii=False).encode("utf-8"), "json"
        rel = f"{stem}.{ext}"
        await asyncio.to_thread(write_atomic, rt.cfg.data_dir / rel, data)
        stored["rel"] = rel

    async def commit_with(conn: AsyncConnection, row_id: str) -> None:
        u = t.usage_records.c
        cost = (await conn.execute(select(u.cost_usd).where(u.id == row_id))).scalar()
        await conn.execute(update(t.generation_tasks).where(T.id == task["id"]).values(
            result_ref=stored.get("rel"), cost_usd=cost))
        total = (await conn.execute(select(func.coalesce(func.sum(u.cost_usd), 0.0)).where(u.job_id == task["job_id"]))).scalar()
        await conn.execute(update(t.generation_jobs).where(J.id == task["job_id"]).values(
            actual_cost_usd=round(float(total or 0.0), 6)))

    return PaidHooks(before_send=before_send, after_response=after_response, commit_with=commit_with)


async def call(sched: JobScheduler, run: Run, a: Attempt, task: dict[str, Any], ch: dict[str, Any],
               spec: plans.TaskPlan) -> None:
    rt = sched.rt
    type_ = task["type"]
    models = rt.settings_doc()["models"]
    if type_ in PROFILE_PARTS:
        drafter = rt.ai.drafter(True)
        if drafter.shared_call and type_ != "profile":
            return  # applied from the profile task's stored draft at $0
        hooks = hooks_for(sched, run, a, task, ch)
        ctx = task_ctx(sched, run, ch, type_)
        slots = rt.llm_slots if drafter.shared_call else None
        async with Slot(slots):
            if run.kind == "profile_regenerate":
                await drafter.regenerate_field(ctx, profile=ch["profile"], field=str(run.input.get("targetField") or ""),
                                               attempt=int(task["attempt"]) + int(ch["version"]), cost_usd=spec.est_usd,
                                               duration_ms=spec.duration_ms, model=str(models["chat"]), hooks=hooks)
            else:
                await drafter.draft(ctx, seed_prompt=ch["seed_prompt"], intent=ch["intent"], cost_usd=spec.est_usd,
                                    duration_ms=spec.duration_ms, model=str(models["chat"]), hooks=hooks)
        return
    if type_ == "theme_song":
        if song_paced(sched):
            await rt.clock.sleep(spec.duration_ms / 1000)
        return
    if spec.price_kind is None:
        return  # an emotion sliced from a sheet: nothing to call
    image = rt.ai.image(True)
    job = await image_job(sched, run, task, ch, spec, str(models["image"]))
    hooks = hooks_for(sched, run, a, task, ch)
    async with Slot(rt.image_slots if image.name == "naive" else None):
        await image.generate(task_ctx(sched, run, ch, type_), job, hooks)


class Slot:
    """`async with Slot(slots)`: hold a provider slot around a call, or nothing when `slots` is None."""

    def __init__(self, slots: Any) -> None:
        self.slots = slots

    async def __aenter__(self) -> None:
        if self.slots is not None:
            await self.slots.acquire()

    async def __aexit__(self, *_exc: object) -> None:
        if self.slots is not None:
            self.slots.release()


async def image_job(sched: JobScheduler, run: Run, task: Mapping[str, Any], ch: Mapping[str, Any], spec: plans.TaskPlan,
                    model: str) -> ImageJob:
    rt = sched.rt
    compiler: ImagePromptCompiler = rt.prompt_compiler
    type_ = task["type"]
    profile, appearance = ch["profile"], ch["appearance"]
    reference: bytes | None = None
    if type_ == "portrait_candidate" and run.kind == "portrait_candidates":
        compiled, mode = compiler.base(profile, appearance, note=run.input.get("prompt")), "base"
    elif type_ == "portrait_candidate":
        compiled, mode = compiler.tweak(profile, str(run.input.get("prompt") or "")), "edit"
    elif type_ == "expression_sheet":
        compiled, mode = compiler.sheet(profile, appearance), "sheet"
    else:
        compiled, mode = compiler.emotion_edit(profile, "blink" if type_ == "blink_frame" else str(task["emotion"])), "edit"
    if mode == "edit":
        reference = await base_reference(sched, ch)
    refuse(compiled)
    palette = rt.palette(ch["palette_id"])
    label = "blink" if type_ == "blink_frame" else str(task["emotion"] or "portrait")
    return ImageJob(task_id=task["id"], mode=mode, prompt=compiled.prompt, model=model, price_kind=spec.price_kind or "portrait",
                    duration_ms=spec.duration_ms, label=label, palette=palette, reference=reference,
                    aspect_ratio="3:2" if mode == "sheet" else "3:4")


def refuse(compiled: CompiledPrompt) -> None:
    if compiled.refused:
        raise Refused("Portraits are only made for adult characters.")


async def base_reference(sched: JobScheduler, ch: Mapping[str, Any]) -> bytes | None:
    """The locked base portrait's original (the provider's JPEG in `originals/`), else its served WebP; None when there
    is no raster base (a seed SVG placeholder, which only the scripted generator accepts)."""
    rt = sched.rt
    a = t.image_assets.c
    async with rt.db.read() as conn:
        rel = (await conn.execute(select(a.rel_path).where(and_(
            a.character_id == ch["id"], a.kind == "emotion", a.emotion == "neutral", a.variant == "default",
            a.is_active.is_(True))))).scalar()
        original = None
        name = Path(str(rel or "")).name
        if name.startswith("candidate_cand_"):
            task_id = "task_" + name.removeprefix("candidate_cand_").removesuffix(".webp")
            original = (await conn.execute(select(T.result_ref, T.target_path).where(T.id == task_id))).first()
    if not rel:
        return None
    for cand in ([str(original[0])] if original and original[0] and str(original[0]).startswith("originals/") else []):
        p = rt.cfg.data_dir / cand
        if p.is_file():
            return await asyncio.to_thread(p.read_bytes)
    if original and original[1]:
        for ext in ("jpg", "png", "webp"):
            p = rt.cfg.data_dir / f"{original[1]}.{ext}"
            if p.is_file():
                return await asyncio.to_thread(p.read_bytes)
    served = rt.cfg.assets_dir / str(rel)
    if str(rel).lower().endswith((".webp", ".png", ".jpg", ".jpeg")) and served.is_file():
        return await asyncio.to_thread(served.read_bytes)
    return None


# ── step 6: derive and apply ──
async def load_original(sched: JobScheduler, ref: str) -> bytes:
    return await asyncio.to_thread((sched.rt.cfg.data_dir / ref).read_bytes)


async def shared_draft(sched: JobScheduler, run: Run) -> dict[str, Any]:
    """A naive draft part: the profile task's stored answer."""
    async with sched.rt.db.read() as conn:
        ref = (await conn.execute(select(T.result_ref).where(and_(T.job_id == run.job_id, T.type == "profile")))).scalar()
    if not ref or not str(ref).startswith("originals/"):
        raise ProviderError("provider_error", "The profile draft failed, so this part has nothing to use.")
    loaded: dict[str, Any] = json.loads(await load_original(sched, str(ref)))
    return loaded


async def finish(sched: JobScheduler, run: Run, task: dict[str, Any], *, resume: bool) -> None:
    type_ = task["type"]
    ref = task["result_ref"]
    payload: Any = None
    if type_ in PROFILE_PARTS:
        if ref and str(ref).startswith("originals/"):
            payload = json.loads(await load_original(sched, str(ref)))
        else:
            payload = await shared_draft(sched, run)
    elif type_ == "theme_song":
        payload = None
    elif type_ == "emotion_image" and run.sheet:
        return  # filled by the sheet's own finish
    else:
        if not ref or not str(ref).startswith("originals/"):
            raise ProviderError("provider_error", "The provider's image was not stored.")
        original = await load_original(sched, str(ref))
        payload = await asyncio.to_thread(sheet_cells if type_ == "expression_sheet" else portrait_webp, original)
    await commit_result(sched, run, task, payload)


def generation(model: str, technique: str, prompt: str, refs: list[str], cost: float | None, job_id: str) -> dict[str, Any]:
    return {"model": model, "technique": technique, "prompt": prompt, "referenceUrls": refs,
            "costUsd": round(float(cost or 0.0), 6), "jobId": job_id}


async def commit_result(sched: JobScheduler, run: Run, task: dict[str, Any], payload: Any) -> None:
    from horizon.contract import mappers as mp

    rt = sched.rt
    type_ = task["type"]
    async with rt.db.write() as tx:
        conn = tx.conn
        now = rt.now_iso()
        cur = (await conn.execute(select(t.generation_tasks).where(T.id == task["id"]))).mappings().first()
        job = (await conn.execute(select(t.generation_jobs).where(J.id == run.job_id))).mappings().first()
        ch = await ap.live_character(conn, run.character_id)
        if cur is None or job is None or job["status"] not in ("queued", "running") or cur["status"] != "running" \
                or ch is None or run.cancelled:
            return  # cancelled, deleted or reset meanwhile: the result is kept, not applied
        models = rt.settings_doc()["models"]
        base_url = mp.rel_to_url((await _neutral_rel(conn, ch["id"])) or None)
        values: dict[str, Any] = {"status": "succeeded", "finished_at": now, "error": None}
        extra_tasks: list[dict[str, Any]] = []
        if type_ == "profile":
            if run.kind == "profile_regenerate":
                await ap.apply_field(conn, ch, payload, now)
            else:
                await ap.apply_profile(conn, ch, payload, now)
        elif type_ == "appearance_summary":
            await ap.apply_appearance(conn, ch, payload, now)
        elif type_ == "palette_pick":
            await ap.apply_palette(conn, ch, payload, now)
        elif type_ == "song_brief":
            await ap.apply_song_brief(conn, ch, payload, now)
        elif type_ == "theme_song":
            song = rt.ai.song(True)
            prev = (await conn.execute(select(t.theme_songs.c.brief).where(t.theme_songs.c.id == ch["theme_song_id"]))).scalar() \
                if ch["theme_song_id"] else None
            brief = run.input.get("brief") or prev or (await _draft_brief(sched, dict(ch)))
            title = f"{str(ch['profile'].get('name', '')).split(' ')[0]}'s Theme"
            spec = song.theme(ch["id"], brief, title)
            values["result_ref"] = await ap.apply_theme(conn, ch, spec=spec, brief=brief, assets_dir=rt.cfg.assets_dir,
                                                        job_id=run.job_id, now=now)
        elif type_ == "portrait_candidate":
            gen = generation(str(models["image"]), "prompt_only" if run.kind == "portrait_candidates" else "reference_edit",
                             "", [base_url] if run.kind == "portrait_tweak" and base_url else [], cur["cost_usd"], run.job_id)
            cand = await ap.apply_candidate(conn, ch, task_id=task["id"], derived=payload, assets_dir=rt.cfg.assets_dir,
                                            generation=gen, now=now)
            values["result_ref"] = cand
            values["preview_url"] = mp.rel_to_url(assets.candidate_rel(ch["world_id"], ch["id"], cand))
        elif type_ in ("emotion_image", "blink_frame"):
            emotion = "neutral" if type_ == "blink_frame" else str(task["emotion"])
            variant = "blink" if type_ == "blink_frame" else "default"
            gen = generation(str(models["image"]), "reference_edit", "", [base_url] if base_url else [], cur["cost_usd"],
                             run.job_id)
            asset_id, rel = await ap.apply_emotion(conn, ch, emotion=emotion, variant=variant, derived=payload,
                                                   assets_dir=rt.cfg.assets_dir, generation=gen, job_id=run.job_id, now=now)
            values["result_ref"] = asset_id
            values["preview_url"] = mp.rel_to_url(rel)
        elif type_ == "expression_sheet":
            cells: dict[str, Any] = payload
            siblings = (await conn.execute(select(t.generation_tasks).where(and_(
                T.job_id == run.job_id, T.type == "emotion_image", T.status == "queued")).order_by(T.ord))).mappings().all()
            for x in siblings:
                cell = cells.get(str(x["emotion"]))
                if cell is None:
                    continue
                gen = generation(str(models["image"]), "expression_sheet", "", [], 0.0, run.job_id)
                ch2 = await ap.live_character(conn, run.character_id)
                assert ch2 is not None
                asset_id, rel = await ap.apply_emotion(conn, ch2, emotion=str(x["emotion"]), variant="default", derived=cell,
                                                       assets_dir=rt.cfg.assets_dir, generation=gen, job_id=run.job_id,
                                                       now=now)
                upd = {"status": "succeeded", "attempt": 1, "finished_at": now, "result_ref": asset_id,
                       "preview_url": mp.rel_to_url(rel), "started_at": now}
                await conn.execute(update(t.generation_tasks).where(T.id == x["id"]).values(**upd))
                extra_tasks.append({**x, **upd})
        await conn.execute(update(t.generation_tasks).where(T.id == task["id"]).values(**values))
        for extra in extra_tasks:
            sched._publish_task(tx, run.job_id, extra)
        sched._publish_task(tx, run.job_id, {**cur, **values})
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "character", "id": ch["id"], "worldId": ch["world_id"]})
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "job", "id": run.job_id})


async def _neutral_rel(conn: AsyncConnection, character_id: str) -> str | None:
    a = t.image_assets.c
    rel = (await conn.execute(select(a.rel_path).where(and_(a.character_id == character_id, a.kind == "emotion",
                                                            a.emotion == "neutral", a.variant == "default",
                                                            a.is_active.is_(True))))).scalar()
    return str(rel) if rel else None


async def _draft_brief(sched: JobScheduler, ch: Mapping[str, Any]) -> dict[str, Any]:
    from horizon.ai.scripted.drafts import draft_from_seed

    brief: dict[str, Any] = draft_from_seed(ch["seed_prompt"], ch["intent"], sched.rt.palette_ids())["brief"]
    return brief


async def fail(sched: JobScheduler, run: Run, task_id: str, code: str, message: str, retryable: bool) -> None:
    rt = sched.rt
    async with rt.db.write() as tx:
        cur = (await tx.conn.execute(select(t.generation_tasks).where(T.id == task_id))).mappings().first()
        if cur is None or cur["status"] != "running":
            return
        now = rt.now_iso()
        err = {"code": code if code in DEFAULT_RETRYABLE else "provider_error", "message": message, "retryable": retryable}
        await tx.conn.execute(update(t.generation_tasks).where(T.id == task_id).values(status="failed", error=err,
                                                                                       finished_at=now))
        if cur["type"] == "portrait_candidate":
            await assets.fail_candidate(tx.conn, task_id)
        if cur["type"] == "expression_sheet":  # its emotions can't be sliced: skipped, as the mock does
            for x in (await tx.conn.execute(select(t.generation_tasks).where(and_(
                    T.job_id == cur["job_id"], T.type == "emotion_image", T.status == "queued")))).mappings().all():
                await tx.conn.execute(update(t.generation_tasks).where(T.id == x["id"]).values(status="skipped", finished_at=now))
                sched._publish_task(tx, run.job_id, {**x, "status": "skipped"})
        sched._publish_task(tx, run.job_id, {**cur, "status": "failed", "error": err})
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "job", "id": run.job_id})
