"""World create / rename / delete (worlds spec, demo-data "reserved names", doc 02 §4).

Names are trimmed, cut to 40 characters and default to "New World" (the MockClient's rules). They are unique
case-insensitively, and a world may not take a shipped seed world's name unless it *is* that seed world, so a
demo reset can always restore the seed names.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.api.errors import conflict
from horizon.contract import mappers as mp
from horizon.contract.validate import ContractSchema
from horizon.db import tables as t
from horizon.db.uow import WriteTx
from horizon.domain.ids import new_id
from horizon.events.bus import GLOBAL
from horizon.services import reads

MAX_NAME = 40
DEFAULT_NAME = "New World"


def clean_name(name: str) -> str:
    return name.strip()[:MAX_NAME] or DEFAULT_NAME


def _key(name: str) -> str:
    return name.strip().casefold()


async def _check_name(conn: AsyncConnection, name: str, *, world_id: str | None, seed_names: dict[str, str]) -> None:
    key = _key(name)
    for seed_id, seed_name in seed_names.items():
        if _key(seed_name) == key and seed_id != world_id:
            raise conflict("That name belongs to a demo world.", {"field": "name", "reserved": True})
    names = (await conn.execute(select(t.worlds.c.id, t.worlds.c.name))).all()
    clash = {wid for wid, n in names if _key(n) == key and wid != world_id}
    if clash:
        raise conflict("A world with that name already exists.", {"field": "name"})


def _validate(schema: ContractSchema, world: dict[str, Any]) -> None:
    from horizon.api.errors import validation

    problems = schema.errors("World", world)
    if problems:
        raise validation("Invalid world.", {"fields": [{"field": p.split(":", 1)[0], "problem": p} for p in problems]})


async def create_world(tx: WriteTx, *, schema: ContractSchema, now: str, seed_names: dict[str, str],
                       name: str, cover: dict[str, Any], you: dict[str, Any] | None) -> dict[str, Any]:
    clean = clean_name(name)
    await _check_name(tx.conn, clean, world_id=None, seed_names=seed_names)
    wire: dict[str, Any] = {"id": new_id("wld"), "name": clean, "cover": cover}
    if you is not None:
        wire["you"] = you
    wire.update(characterCount=0, isSeed=False, createdAt=now, updatedAt=now, lastActiveAt=now)
    _validate(schema, wire)
    await tx.conn.execute(t.worlds.insert().values(**mp.world_row(wire, is_seed=False)))
    tx.publish(GLOBAL, {"type": "entity.changed", "kind": "world", "id": wire["id"], "worldId": wire["id"]})
    return wire


async def update_world(tx: WriteTx, world_id: str, *, schema: ContractSchema, now: str, seed_names: dict[str, str],
                       patch: dict[str, Any]) -> dict[str, Any]:
    row = await reads.world_row(tx.conn, world_id)
    values: dict[str, Any] = {"updated_at": now}
    if "name" in patch and patch["name"] is not None:
        clean = clean_name(patch["name"])
        await _check_name(tx.conn, clean, world_id=world_id, seed_names=seed_names)
        values["name"] = clean
    if patch.get("cover") is not None:
        values["cover"] = patch["cover"]
    if "you" in patch:
        values["you"] = patch["you"]
    merged = dict(row) | values
    _validate(schema, mp.world_wire(merged, 0))
    await tx.conn.execute(t.worlds.update().where(t.worlds.c.id == world_id).values(**values))
    tx.publish(GLOBAL, {"type": "entity.changed", "kind": "world", "id": world_id, "worldId": world_id})
    return await reads.get_world(tx.conn, world_id)


async def delete_world(tx: WriteTx, world_id: str, *, now: str) -> None:
    """Cascade (doc 02 §4): sessions first (participants RESTRICT characters), then the world takes characters,
    assets, songs, memory and knowledge with it. Ledger references become NULL. An AI purge is queued."""
    await reads.world_row(tx.conn, world_id)
    await tx.conn.execute(delete(t.sessions).where(t.sessions.c.world_id == world_id))
    await tx.conn.execute(delete(t.worlds).where(t.worlds.c.id == world_id))
    await tx.conn.execute(t.ai_purge_queue.insert().values(scope="world", ids=[world_id], created_at=now, attempts=0,
                                                           done_at=None))
    tx.publish(GLOBAL, {"type": "entity.changed", "kind": "world", "id": world_id, "worldId": world_id})


def remove_world_files(data_dir: Path, world_id: str) -> None:
    """After the commit: the world's generated assets, provider originals and uploaded documents."""
    for root in (data_dir / "assets" / "gen", data_dir / "originals", data_dir / "knowledge"):
        target = root / world_id
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

