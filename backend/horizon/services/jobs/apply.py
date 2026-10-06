"""What a succeeded task does to its character (generation-jobs design D2, D8; the MockClient's `JobRunner.apply`).

Every function runs inside the caller's writer transaction, re-reads the character row there, and stores nothing for a
tombstone (a delete that raced the task). Files are written by the caller inside the same transaction window (atomic
renames; an orphan from a rolled-back transaction is swept after an hour).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.services import assets, theme
from horizon.storage.atomic import write_atomic
from horizon.storage.images import Derived

C = t.characters.c
DRAFT_SONG_NOTE = "Placeholder: procedural WebAudio sketch (D-52)."
CREATION_STEPS = ("seed", "profile", "look", "portrait", "emotions", "song", "review")


async def live_character(conn: AsyncConnection, character_id: str) -> RowMapping | None:
    row = (await conn.execute(select(t.characters).where(C.id == character_id))).mappings().first()
    return row if row is not None and row["deleted_at"] is None else None


async def touch(conn: AsyncConnection, character_id: str, now: str, **values: Any) -> None:
    await conn.execute(update(t.characters).where(C.id == character_id).values(updated_at=now, **values))


# ── profile parts ──
async def apply_profile(conn: AsyncConnection, ch: RowMapping, draft: Mapping[str, Any], now: str) -> None:
    await touch(conn, ch["id"], now, profile=draft["profile"], advisory=bool(draft["advisory"]), creation_step="profile")


async def apply_field(conn: AsyncConnection, ch: RowMapping, patch: Mapping[str, Any], now: str) -> None:
    await touch(conn, ch["id"], now, profile={**ch["profile"], **patch})


async def apply_appearance(conn: AsyncConnection, ch: RowMapping, draft: Mapping[str, Any], now: str) -> None:
    appearance = {**ch["appearance"], "attributes": draft["attributes"], "appearanceSummary": draft["appearanceSummary"]}
    await touch(conn, ch["id"], now, appearance=appearance)


async def apply_palette(conn: AsyncConnection, ch: RowMapping, draft: Mapping[str, Any], now: str) -> None:
    await touch(conn, ch["id"], now, palette_id=draft["paletteId"])


async def apply_song_brief(conn: AsyncConnection, ch: RowMapping, draft: Mapping[str, Any], now: str) -> None:
    """The mock's `song_brief`: a pending theme song carrying the drafted brief."""
    song_id = ch["theme_song_id"] or new_id("song")
    values = {"character_id": ch["id"], "status": "pending", "rel_path": None, "duration_sec": None, "format": None,
              "bytes": None, "loop": None, "gain_db": None, "brief": draft["brief"], "instrumental": True,
              "generation": None, "license_note": DRAFT_SONG_NOTE}
    exists = (await conn.execute(select(t.theme_songs.c.id).where(t.theme_songs.c.id == song_id))).first() is not None
    if exists:
        await conn.execute(update(t.theme_songs).where(t.theme_songs.c.id == song_id).values(**values))
    else:
        await conn.execute(t.theme_songs.insert().values(id=song_id, version=1, is_seed=False, created_at=now, **values))
    await touch(conn, ch["id"], now, theme_song_id=song_id)


# ── images ──
async def write_file(assets_dir: Path, rel: str, data: bytes) -> None:
    await asyncio.to_thread(write_atomic, assets_dir / rel, data)


async def apply_candidate(conn: AsyncConnection, ch: RowMapping, *, task_id: str, derived: Derived, assets_dir: Path,
                          generation: Mapping[str, Any], now: str) -> str:
    cand = assets.cand_id_for(task_id)
    rel = assets.candidate_rel(ch["world_id"], ch["id"], cand)
    await write_file(assets_dir, rel, derived.data)
    await assets.finish_candidate(conn, task_id, rel_path=rel, width=derived.width, height=derived.height,
                                  size=derived.size, generation=generation)
    await touch(conn, ch["id"], now)
    return cand


async def apply_emotion(conn: AsyncConnection, ch: RowMapping, *, emotion: str, variant: str, derived: Derived,
                        assets_dir: Path, generation: Mapping[str, Any], job_id: str, now: str) -> tuple[str, str]:
    """A new emotion (or blink) version; returns (asset id, its URL path)."""
    version = await assets.next_version(conn, ch["id"], emotion, variant)
    rel = assets.emotion_rel(ch["world_id"], ch["id"], emotion, variant, version)
    await write_file(assets_dir, rel, derived.data)
    asset_id, _active = await assets.add_emotion_version(
        conn, character=ch, emotion=emotion, variant=variant, version=version, rel_path=rel, width=derived.width,
        height=derived.height, size=derived.size, fmt="webp", generation=generation, job_id=job_id, now=now)
    await touch(conn, ch["id"], now)
    return asset_id, rel


# ── song ──
async def apply_theme(conn: AsyncConnection, ch: RowMapping, *, spec: Mapping[str, Any], brief: Mapping[str, Any],
                      assets_dir: Path, job_id: str, now: str) -> str:
    """D-83: the procedural theme as a new `.proc.json` version; the character's song row points at it."""
    song_id = ch["theme_song_id"] or new_id("song")
    s = t.theme_songs.c
    prev = (await conn.execute(select(t.theme_songs).where(s.id == song_id))).mappings().first()
    top = (await conn.execute(select(func.coalesce(func.max(s.version), 0)).where(s.character_id == ch["id"]))).scalar_one()
    version = int(top) + 1 if prev is None or prev["rel_path"] else max(1, int(top))
    rel = assets.song_rel(ch["world_id"], ch["id"], version)
    await write_file(assets_dir, rel, json.dumps(spec, ensure_ascii=False).encode("utf-8"))
    values = {"character_id": ch["id"], "status": "ready", "rel_path": rel, "duration_sec": theme.duration_sec(float(brief["bpm"])),
              "format": None, "bytes": None, "loop": None, "gain_db": None, "brief": dict(brief), "instrumental": True,
              "generation": {"model": theme.MODEL, "prompt": f"Instrumental theme: {brief.get('vibe', '')}", "costUsd": 0,
                             "jobId": job_id},
              "license_note": theme.LICENSE_NOTE, "version": version}
    if prev is not None:
        await conn.execute(update(t.theme_songs).where(s.id == song_id).values(**values))
    else:
        await conn.execute(t.theme_songs.insert().values(id=song_id, is_seed=False, created_at=now, **values))
    await touch(conn, ch["id"], now, theme_song_id=song_id)
    return song_id
