"""Generated files and asset versions (generation-jobs design D7, D8; generated-assets spec).

Paths (immutable names, doc 02 §2): served files live under `data/assets/gen/{worldId}/…` and are stored in
`image_assets.rel_path` relative to `data/assets/`; provider originals live under `data/originals/{worldId}/{characterId}/`
and are referenced from `generation_tasks.result_ref` relative to `data/`.

- **Candidates** are inserted `generating` when their job starts (`cand_` + the task ID's suffix) and become `ready`
  or `failed` when their task ends. Until then the contract's required `url` is a blank 1×1 data URL.
- **Emotion versions** number `MAX(version) + 1` per `(emotion, variant)` slot. A new version is active unless the
  character is approved and the slot already has an active one (the mock's `replaceLater`); activating always
  deactivates first (the partial unique index allows one active row per slot).
- **Lock** makes a ready candidate the next neutral version, pointing at the candidate's own file, so
  `emotions.neutral.url` equals the candidate's URL (D-85).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import tables as t
from horizon.domain.ids import new_id

A = t.image_assets.c
BLANK_URL = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
VFX = {"neutral": "none", "happy": "sparkle", "sad": "rain", "angry": "anger", "surprised": "shock", "thinking": "ponder",
       "embarrassed": "blush"}


# ── paths ──
def gen_dir(world_id: str, character_id: str) -> str:
    return f"gen/{world_id}/{character_id}"


def candidate_rel(world_id: str, character_id: str, cand_id: str) -> str:
    return f"{gen_dir(world_id, character_id)}/candidate_{cand_id}.webp"


def emotion_rel(world_id: str, character_id: str, emotion: str, variant: str, version: int) -> str:
    blink = "_blink" if variant == "blink" else ""
    return f"{gen_dir(world_id, character_id)}/portrait_{emotion}{blink}_v{version}.webp"


def song_rel(world_id: str, character_id: str, version: int) -> str:
    return f"{gen_dir(world_id, character_id)}/song_v{version}.proc.json"


def cover_rel(world_id: str, version: int) -> str:
    return f"gen/{world_id}/cover_v{version}.webp"


def original_rel(world_id: str, character_id: str, task_id: str, attempt: int, ext: str) -> str:
    return f"originals/{world_id}/{character_id}/{task_id}_a{attempt}.{ext}"


def cand_id_for(task_id: str) -> str:
    return "cand_" + task_id.split("_", 1)[1]


# ── candidates ──
async def insert_candidates(conn: AsyncConnection, *, world_id: str, character_id: str, job_id: str,
                            task_ids: list[str], now: str) -> None:
    for i, task_id in enumerate(task_ids):
        await conn.execute(t.image_assets.insert().values(
            id=cand_id_for(task_id), world_id=world_id, character_id=character_id, job_id=job_id, kind="candidate",
            emotion=None, variant="default", status="generating", rel_path=None, width=None, height=None, format=None,
            bytes=None, vfx_preset="none", generation=None, version=1, is_active=False, selected=False, ord=i,
            created_at=now))


async def finish_candidate(conn: AsyncConnection, task_id: str, *, rel_path: str, width: int, height: int, size: int,
                           generation: Mapping[str, Any]) -> None:
    await conn.execute(update(t.image_assets).where(A.id == cand_id_for(task_id)).values(
        status="ready", rel_path=rel_path, width=width, height=height, format="webp", bytes=size,
        generation=dict(generation)))


async def fail_candidate(conn: AsyncConnection, task_id: str) -> None:
    await conn.execute(update(t.image_assets).where(and_(A.id == cand_id_for(task_id), A.status != "ready"))
                       .values(status="failed"))


# ── emotion versions ──
async def next_version(conn: AsyncConnection, character_id: str, emotion: str, variant: str) -> int:
    q = select(func.coalesce(func.max(A.version), 0)).where(and_(
        A.character_id == character_id, A.kind == "emotion", A.emotion == emotion, A.variant == variant))
    return int((await conn.execute(q)).scalar_one()) + 1


async def has_active(conn: AsyncConnection, character_id: str, emotion: str, variant: str) -> bool:
    q = select(A.id).where(and_(A.character_id == character_id, A.kind == "emotion", A.emotion == emotion,
                                A.variant == variant, A.is_active.is_(True)))
    return (await conn.execute(q)).first() is not None


async def deactivate_slot(conn: AsyncConnection, character_id: str, emotion: str, variant: str) -> None:
    await conn.execute(update(t.image_assets).where(and_(
        A.character_id == character_id, A.kind == "emotion", A.emotion == emotion, A.variant == variant,
        A.is_active.is_(True))).values(is_active=False))


async def add_emotion_version(conn: AsyncConnection, *, character: RowMapping, emotion: str, variant: str, version: int,
                              rel_path: str, width: int | None, height: int | None, size: int | None, fmt: str | None,
                              generation: Mapping[str, Any] | None, job_id: str | None, now: str,
                              force_active: bool = False) -> tuple[str, bool]:
    """Insert one version; returns (asset id, is_active)."""
    cid = character["id"]
    replace_later = character["status"] == "approved" and await has_active(conn, cid, emotion, variant)
    active = force_active or not replace_later
    if active:
        await deactivate_slot(conn, cid, emotion, variant)
    asset_id = new_id("emo")
    await conn.execute(t.image_assets.insert().values(
        id=asset_id, world_id=character["world_id"], character_id=cid, job_id=job_id, kind="emotion", emotion=emotion,
        variant=variant, status="ready", rel_path=rel_path, width=width, height=height, format=fmt, bytes=size,
        vfx_preset=VFX.get(emotion, "none") if variant == "default" else "none",
        generation=dict(generation) if generation is not None else None, version=version, is_active=active,
        selected=False, ord=0, created_at=now))
    return asset_id, active


async def activate(conn: AsyncConnection, asset: RowMapping) -> None:
    """acceptAssetVersion: deactivate the slot, then activate this version (one transaction, the caller's)."""
    await deactivate_slot(conn, asset["character_id"], asset["emotion"], asset["variant"])
    await conn.execute(update(t.image_assets).where(A.id == asset["id"]).values(is_active=True))


async def next_cover_version(conn: AsyncConnection, world_id: str) -> int:
    q = select(func.coalesce(func.max(A.version), 0)).where(and_(A.world_id == world_id, A.kind == "cover"))
    return int((await conn.execute(q)).scalar_one()) + 1
