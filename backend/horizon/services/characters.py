"""Character lifecycle writes (character-lifecycle spec; generation-jobs design D6, D8, D10). Ports of the MockClient's
`createDraft`, `update`, `lockPortrait`, `approve`, `archive`, `restore`, `delete` and `acceptAssetVersion`.

- Every command treats a tombstone as `not_found` (`live`).
- **Drafts** start with placeholder profile values that satisfy the contract (`name` and `role` are required and
  non-empty, `personality.traits` needs at least three) until the `profile_draft` job fills them in a few seconds.
  The mock leaves them empty; the backend validates every response, so it can't.
- **PATCH** deep-merges `profile` and `appearance` (objects key by key, lists replaced) in one writer transaction, so
  a concurrent job write to the same character is never lost (SQLite's single writer serialises them).
- **Delete** leaves a tombstone (D-70): 409 while the character is speaking in a live session; otherwise its job is
  cancelled, then one transaction tombstones the row, drops its other assets, songs, jobs, memory and knowledge and
  queues the AI purge; files go after the commit.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.api.errors import conflict, not_found, validation
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.events.bus import GLOBAL
from horizon.services import assets, reads
from horizon.services.reads import ReadContext

if TYPE_CHECKING:
    from horizon.runtime import Runtime

C = t.characters.c
A = t.image_assets.c
EMOTIONS = list(mp.EMOTIONS)
CREATION_STEPS = ("seed", "profile", "look", "portrait", "emotions", "song", "review")
PLACEHOLDER_ROLE = "Drafting…"
PLACEHOLDER_TRAITS = ["curious", "warm", "candid"]
PATCH_FIELDS = ("seedPrompt", "intent", "advisory", "paletteId", "creationStep", "status", "profileMeta", "emotionSet")
COLUMN = {"seedPrompt": "seed_prompt", "intent": "intent", "advisory": "advisory", "paletteId": "palette_id",
          "creationStep": "creation_step", "status": "status", "profileMeta": "profile_meta", "emotionSet": "emotion_set"}


async def live(conn: AsyncConnection, character_id: str) -> RowMapping:
    row = (await conn.execute(select(t.characters).where(C.id == character_id))).mappings().first()
    if row is None or row["deleted_at"] is not None:
        raise not_found("Character")
    return row


def deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """Objects merge key by key; anything else (lists included) replaces. `None` values in the patch are skipped."""
    out = dict(base)
    for k, v in patch.items():
        if v is None:
            continue
        cur = out.get(k)
        out[k] = deep_merge(cur, v) if isinstance(v, Mapping) and isinstance(cur, Mapping) else v
    return out


def _published(tx: Any, row: Any) -> None:
    tx.publish(GLOBAL, {"type": "entity.changed", "kind": "character", "id": row["id"], "worldId": row["world_id"]})


async def wire(conn: AsyncConnection, rc: ReadContext, character_id: str) -> dict[str, Any]:
    return await reads.get_character(conn, rc, character_id)


def _check(rt: Runtime, character: Mapping[str, Any]) -> None:
    problems = rt.schema.errors("Character", character)
    if problems:
        raise validation("Invalid character.", {"fields": [{"field": p.split(":", 1)[0], "problem": p} for p in problems[:5]]})


# ── createDraft ──
def draft_wire(rt: Runtime, world_id: str, seed_prompt: str, intent: str) -> dict[str, Any]:
    from horizon.domain.jsrng import js_slice

    now = rt.now_iso()
    m = re.match(r"\s*([A-Z][a-z]+)", seed_prompt)
    energy_max = int(rt.settings_doc()["energy"]["defaultMaxPoints"])
    presets = rt.prompt_compiler.presets
    preset = next(iter(presets.values()), {"id": "style_horizon_anime", "version": 1})
    return {
        "id": new_id("chr"), "worldId": world_id, "status": "draft", "creationStep": "seed",
        "seedPrompt": js_slice(seed_prompt, 300), "intent": intent, "advisory": intent == "expert",
        "profile": {"name": m.group(1) if m else "New character", "role": PLACEHOLDER_ROLE, "age": 30, "tagline": "",
                    "personality": {"summary": "", "traits": list(PLACEHOLDER_TRAITS)}, "backstory": "",
                    "speakingStyle": {"summary": "", "tone": "", "formality": "neutral", "quirks": [], "catchphrases": []},
                    "expertise": [], "boundaries": [], "greeting": ""},
        "appearance": {
            "attributes": {
                "body": {"ageBand": "adult", "build": "average", "height": "average", "skinTone": "beige"},
                "face": {"shape": "oval", "baseline": "neutral", "marks": []},
                "eyes": {"shape": "almond", "color": "brown", "glasses": "none"},
                "hair": {"length": "short", "style": "straight", "color": "black", "fringe": "none"},
                "outfit": {"archetype": "casual", "primaryColor": "#2F5D8A", "secondaryColor": "#F5F2EA"},
                "accessories": [], "vibe": []},
            "appearanceSummary": "", "candidates": [], "stylePresetId": str(preset["id"]),
            "stylePresetVersion": int(str(preset.get("version", 1)))},
        "paletteId": rt.palette_ids()[0] if rt.palettes else "pal_ocean_clinic",
        "emotionSet": list(EMOTIONS), "emotions": dict.fromkeys(EMOTIONS), "blink": None,
        "energy": {"max": energy_max, "current": energy_max, "asOf": now, "regenPerHour": energy_max / 24,
                   "spentToday": 0, "state": "active"},
        "version": 1, "isSeed": False, "createdAt": now, "updatedAt": now,
    }


async def create_draft(rt: Runtime, rc: ReadContext, world_id: str, seed_prompt: str, intent: str) -> dict[str, Any]:
    rt.gateway.core.require_key()
    async with rt.db.read() as conn:
        await reads.world_row(conn, world_id)
    draft = draft_wire(rt, world_id, seed_prompt, intent)
    _check(rt, draft)
    job_input = {"characterId": draft["id"], "kind": "profile_draft"}
    plan = rt.jobs.plan(job_input)
    job_id = new_id("job")
    stub = {"id": draft["id"], "world_id": world_id, "status": "draft"}
    await rt.jobs._reserve(stub, job_id, plan.estimate, existing=False)
    try:
        async with rt.db.write() as tx:
            await reads.world_row(tx.conn, world_id)
            row, _assets = mp.character_rows(draft, is_seed=False, energy_day=rt.energy_day)
            await tx.conn.execute(t.characters.insert().values(**row))
            await rt.jobs.insert_job(tx, row, job_id, job_input, plan)
    except BaseException:
        rt.book.release_job(job_id)
        raise
    rt.jobs.launch(job_id)
    async with rt.db.read() as conn:
        return {"character": await wire(conn, rc, draft["id"]), "job": await reads.get_job(conn, job_id)}


# ── PATCH ──
async def update_character(rt: Runtime, rc: ReadContext, character_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
    async with rt.db.write() as tx:
        row = await live(tx.conn, character_id)
        values: dict[str, Any] = {COLUMN[k]: patch[k] for k in PATCH_FIELDS if k in patch}
        if patch.get("profile") is not None:
            values["profile"] = deep_merge(row["profile"], patch["profile"])
        if patch.get("appearance") is not None:
            ap = {k: v for k, v in patch["appearance"].items() if k not in ("candidates", "basePortraitUrl")}
            values["appearance"] = deep_merge(row["appearance"], ap)
        now = rt.now_iso()
        values["updated_at"] = now
        if row["status"] == "approved":
            values["version"] = int(row["version"]) + 1
        merged = {**dict(row), **values}
        assets_rows = (await reads._assets_for(tx.conn, [character_id]))[character_id]
        _check(rt, mp.character_wire(merged, assets_rows, mp.stored_energy(merged) | {"state": "active"}))
        await tx.conn.execute(update(t.characters).where(C.id == character_id).values(**values))
        _published(tx, row)
        return await wire(tx.conn, rc, character_id)


# ── lockPortrait / approve / archive / restore ──
async def lock_portrait(rt: Runtime, rc: ReadContext, character_id: str, candidate_id: str) -> dict[str, Any]:
    async with rt.db.write() as tx:
        conn = tx.conn
        row = await live(conn, character_id)
        cand = (await conn.execute(select(t.image_assets).where(and_(
            A.id == candidate_id, A.character_id == character_id, A.kind == "candidate")))).mappings().first()
        if cand is None:
            raise not_found("Candidate")
        if cand["status"] != "ready" or not cand["rel_path"]:
            raise conflict("That candidate isn't ready.")
        now = rt.now_iso()
        await conn.execute(update(t.image_assets).where(and_(A.character_id == character_id, A.kind == "candidate"))
                           .values(selected=False))
        await conn.execute(update(t.image_assets).where(A.id == candidate_id).values(selected=True))
        version = await assets.next_version(conn, character_id, "neutral", "default")
        fmt = "webp" if str(cand["rel_path"]).endswith(".webp") else None
        await assets.add_emotion_version(
            conn, character=row, emotion="neutral", variant="default", version=version, rel_path=cand["rel_path"],
            width=cand["width"], height=cand["height"], size=cand["bytes"], fmt=fmt, generation=cand["generation"],
            job_id=cand["job_id"], now=now, force_active=True)
        values: dict[str, Any] = {"updated_at": now}
        step = row["creation_step"] or "seed"
        if row["status"] == "draft" and step in CREATION_STEPS and CREATION_STEPS.index(step) < CREATION_STEPS.index("emotions"):
            values["creation_step"] = "emotions"
        await conn.execute(update(t.characters).where(C.id == character_id).values(**values))
        _published(tx, row)
        return await wire(conn, rc, character_id)


async def _has_base(conn: AsyncConnection, character_id: str) -> bool:
    return (await conn.execute(select(A.id).where(and_(A.character_id == character_id, A.kind == "emotion",
                                                        A.emotion == "neutral", A.variant == "default",
                                                        A.is_active.is_(True))))).first() is not None


async def approve(rt: Runtime, rc: ReadContext, character_id: str) -> dict[str, Any]:
    async with rt.db.write() as tx:
        row = await live(tx.conn, character_id)
        p = row["profile"] or {}
        if not p.get("name") or not p.get("role") or p.get("role") == PLACEHOLDER_ROLE or int(p.get("age") or 0) < 18 \
                or not await _has_base(tx.conn, character_id):
            raise validation("Approval needs a valid profile (adult age) and a locked base portrait.")
        now = rt.now_iso()
        await tx.conn.execute(update(t.characters).where(C.id == character_id).values(
            status="approved", approved_at=now, creation_step=None, updated_at=now))
        _published(tx, row)
        return await wire(tx.conn, rc, character_id)


async def archive(rt: Runtime, rc: ReadContext, character_id: str) -> dict[str, Any]:
    async with rt.db.write() as tx:
        row = await live(tx.conn, character_id)
        now = rt.now_iso()
        await tx.conn.execute(update(t.characters).where(C.id == character_id).values(status="archived", archived_at=now,
                                                                                     updated_at=now))
        _published(tx, row)
        return await wire(tx.conn, rc, character_id)


async def restore(rt: Runtime, rc: ReadContext, character_id: str) -> dict[str, Any]:
    async with rt.db.write() as tx:
        row = await live(tx.conn, character_id)
        status = "approved" if row["approved_at"] or row["is_seed"] else "draft"
        await tx.conn.execute(update(t.characters).where(C.id == character_id).values(status=status, archived_at=None,
                                                                                     updated_at=rt.now_iso()))
        _published(tx, row)
        return await wire(tx.conn, rc, character_id)


# ── acceptAssetVersion ──
async def accept_asset_version(rt: Runtime, rc: ReadContext, asset_id: str) -> dict[str, Any]:
    async with rt.db.write() as tx:
        a = (await tx.conn.execute(select(t.image_assets).where(and_(A.id == asset_id, A.kind == "emotion")))).mappings().first()
        if a is None or a["character_id"] is None:
            raise not_found("Asset")
        row = await live(tx.conn, a["character_id"])
        await assets.activate(tx.conn, a)
        values: dict[str, Any] = {"updated_at": rt.now_iso()}
        if row["status"] == "approved":
            values["version"] = int(row["version"]) + 1
        await tx.conn.execute(update(t.characters).where(C.id == row["id"]).values(**values))
        _published(tx, row)
        return await wire(tx.conn, rc, row["id"])


# ── delete → tombstone ──
def tombstone_profile(p: Mapping[str, Any]) -> dict[str, Any]:
    """The mock's `tombstone()`: identity and palette survive; everything else is emptied."""
    out: dict[str, Any] = {"name": p["name"]}
    if p.get("title"):
        out["title"] = p["title"]
    out.update(role=p["role"], age=p["age"])
    if p.get("pronouns"):
        out["pronouns"] = p["pronouns"]
    out.update(tagline=p.get("tagline", ""), personality={"summary": "", "traits": (p.get("personality") or {}).get("traits", [])},
               backstory="", speakingStyle={"summary": "", "tone": "", "formality": (p.get("speakingStyle") or {}).get(
                   "formality", "neutral"), "quirks": [], "catchphrases": []},
               expertise=[], boundaries=[], greeting="")
    return out


async def delete_character(rt: Runtime, character_id: str) -> None:
    async with rt.db.read() as conn:
        row = await live(conn, character_id)
    speaking = rt.sessions.generating_with(character_id)
    if speaking is not None:
        name = (row["profile"] or {}).get("name", "This character")
        raise conflict(f"{name} is in the live session. Stop or leave it first.", {"activeSessionId": speaking})
    await rt.jobs.cancel_for_character(character_id)
    now = rt.now_iso()
    async with rt.db.write() as tx:
        conn = tx.conn
        row = await live(conn, character_id)
        neutral = (await conn.execute(select(t.image_assets).where(and_(
            A.character_id == character_id, A.kind == "emotion", A.emotion == "neutral", A.variant == "default",
            A.is_active.is_(True))))).mappings().first()
        keep_rel = neutral["rel_path"] if neutral is not None else None
        await conn.execute(update(t.characters).where(C.id == character_id).values(
            profile=tombstone_profile(row["profile"]), profile_meta=None,
            appearance={k: v for k, v in (row["appearance"] or {}).items() if k not in ("candidates", "basePortraitUrl")},
            theme_song_id=None, active_job_id=None, deleted_at=now, updated_at=now))
        q = delete(t.image_assets).where(A.character_id == character_id)
        if neutral is not None:
            q = q.where(A.id != neutral["id"])
        await conn.execute(q)
        await conn.execute(delete(t.theme_songs).where(t.theme_songs.c.character_id == character_id))
        await conn.execute(delete(t.generation_jobs).where(t.generation_jobs.c.character_id == character_id))
        await conn.execute(delete(t.memory_items).where(t.memory_items.c.character_id == character_id))
        await conn.execute(delete(t.knowledge_sources).where(t.knowledge_sources.c.character_id == character_id))
        await conn.execute(t.ai_purge_queue.insert().values(scope="character", ids=[character_id], created_at=now,
                                                            attempts=0, done_at=None))
        _published(tx, row)
    rt.purge.notify()
    remove_character_files(rt.cfg.data_dir, row["world_id"], character_id, keep_rel)


def remove_character_files(data_dir: Path, world_id: str, character_id: str, keep_rel: str | None) -> None:
    """After the commit: generated files except the kept neutral portrait, provider originals and uploaded documents."""
    gen = data_dir / "assets" / assets.gen_dir(world_id, character_id)
    if gen.is_dir():
        keep = (data_dir / "assets" / keep_rel).resolve() if keep_rel else None
        for p in gen.rglob("*"):
            if p.is_file() and (keep is None or p.resolve() != keep):
                p.unlink(missing_ok=True)
    for root in (data_dir / "originals" / world_id / character_id, data_dir / "knowledge" / world_id / character_id):
        if root.is_dir():
            shutil.rmtree(root, ignore_errors=True)
