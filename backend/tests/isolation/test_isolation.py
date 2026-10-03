"""Isolation (NFR-23, task 8.4): two near-identical worlds. Nothing read in world A may come from world B.

World B is built through the same mappers the seed uses: a copy of Meridian's characters, memories and knowledge with
the same names and text but different ids. Every list, get, passage list and scoped full-text search for A is
checked for B's ids, and the other way round.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from sqlalchemy import insert

from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.services import reads
from horizon.services.seed import SeedData
from tests.conftest import Api

A = "wld_seedMeridian"
B = "wld_twinB"


ID = re.compile(r"\b(chr|kno|kch|mem|emo|cand|song)_(?!twin)([0-9A-Za-z]+)")


def _rename(v: Any) -> Any:
    """Every Meridian id → its world-B twin (`chr_seedAmara` → `chr_twinseedAmara`, …); text stays identical."""
    if isinstance(v, str):
        return ID.sub(lambda m: f"{m.group(1)}_twin{m.group(2)}", v.replace(A, B))
    if isinstance(v, list):
        return [_rename(x) for x in v]
    if isinstance(v, dict):
        return {k: _rename(x) for k, x in v.items()}
    return v


async def _build_twin(api: Api) -> set[str]:
    rt = api.rt
    seed: SeedData = await rt.load_seed()
    chars = [c for c in seed.characters if c["worldId"] == A and c["isSeed"]]
    ids = {c["id"] for c in chars}
    twin_ids: set[str] = set()
    async with rt.db.write() as tx:
        w = copy.deepcopy(next(x for x in seed.worlds if x["id"] == A))
        w.update(id=B, name="Meridian Twin", isSeed=False)
        await tx.conn.execute(insert(t.worlds).values(**mp.world_row(w, is_seed=False)))
        for c in chars:
            tc = _rename({k: v for k, v in c.items() if k != "themeSongId"})
            row, assets = mp.character_rows(tc, is_seed=False, energy_day=rt.energy_day)
            await tx.conn.execute(insert(t.characters).values(**row))
            await tx.conn.execute(insert(t.image_assets), assets)
            twin_ids.add(tc["id"])
        for m in [m for m in seed.memory if m["characterId"] in ids]:
            tm = _rename(m)
            tm.pop("sourceSessionId", None)
            tm.pop("sourceMessageId", None)
            await tx.conn.execute(insert(t.memory_items).values(**mp.memory_row(tm, is_seed=False)))
            twin_ids.add(tm["id"])
        for k in [k for k in seed.knowledge if k["characterId"] in ids]:
            tk = _rename(k)
            chunks = _rename(seed.chunks.get(k["id"], []))
            await tx.conn.execute(insert(t.knowledge_sources).values(**mp.knowledge_source_row(tk, is_seed=False,
                                                                                               chunk_count=len(chunks))))
            sections, crows = mp.chunk_rows(chunks, tk, lambda ch: "ksec_" + ch["id"].split("_", 1)[1])
            if sections:
                await tx.conn.execute(insert(t.knowledge_sections), sections)
                await tx.conn.execute(insert(t.knowledge_chunks), crows)
            twin_ids.add(tk["id"])
            twin_ids.update(c["id"] for c in chunks)
    return twin_ids


def _ids(v: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(v, dict):
        for k, x in v.items():
            if k in ("id", "characterId", "worldId", "sourceId") and isinstance(x, str):
                out.add(x)
            out |= _ids(x)
    elif isinstance(v, list):
        for x in v:
            out |= _ids(x)
    return out


async def _world_view(api: Api, world: str) -> set[str]:
    seen: set[str] = set()
    roster = await api.json(f"/api/v1/worlds/{world}/characters", params={"includeArchived": "true"})
    seen |= _ids(roster)
    for c in roster:
        seen |= _ids(await api.json(f"/api/v1/characters/{c['id']}"))
        seen |= _ids(await api.json(f"/api/v1/characters/{c['id']}/memory"))
        for k in await api.json(f"/api/v1/characters/{c['id']}/knowledge"):
            seen |= _ids(k)
            seen |= _ids(await api.json(f"/api/v1/knowledge/{k['id']}"))
    seen |= _ids(await api.json(f"/api/v1/worlds/{world}/sessions"))
    return seen


async def test_world_a_never_sees_world_b(api: Api) -> None:
    twins = await _build_twin(api)
    assert len(twins) > 30
    seen_a = await _world_view(api, A)
    assert not (seen_a & twins), sorted(seen_a & twins)[:5]
    seen_b = await _world_view(api, B)
    assert seen_b and all("_twin" in x for x in seen_b), sorted(x for x in seen_b if "_twin" not in x)[:10]


async def test_scoped_full_text_stays_in_its_world(api: Api) -> None:
    await _build_twin(api)
    async with api.rt.db.read() as conn:
        a = await reads.fts_search(conn, world_id=A, character_id="chr_seedAmara", query="triage")
        b = await reads.fts_search(conn, world_id=B, character_id="chr_twinseedAmara", query="triage")
        cross = await reads.fts_search(conn, world_id=A, character_id="chr_twinseedAmara", query="triage")
        ma = await reads.memory_fts_search(conn, world_id=A, character_id="chr_seedAmara", query="Kai")
        mb = await reads.memory_fts_search(conn, world_id=B, character_id="chr_twinseedAmara", query="Kai")
    assert a and b and len(a) == len(b)
    assert all(not x["id"].startswith("kch_twin") for x in a)
    assert all(x["id"].startswith("kch_twin") for x in b)
    assert cross == []
    assert all(x["worldId"] == A for x in ma) and all(x["worldId"] == B for x in mb)


async def test_unknown_world_paths_are_404(api: Api) -> None:
    await _build_twin(api)
    for path in ("/api/v1/worlds/wld_nope/characters", "/api/v1/worlds/wld_nope/sessions"):
        assert (await api.get(path)).status_code == 404
