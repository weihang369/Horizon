"""Deleting a world and resetting the demo wake the purge worker (v1 test stage, audit 01-06).

Before, both queued their `ai_purge_queue` row and left it there until the next restart (found by deleting a real
world on 2026-10-20); character and session deletes already woke the worker.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from tests.conftest import Api

API = "/api/v1"


async def _undone(api: Api, scope: str) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM ai_purge_queue WHERE scope = :s AND done_at IS NULL"),
                                       {"s": scope})).scalar_one())


async def _drained(api: Api, scope: str) -> bool:
    for _ in range(100):
        if await _undone(api, scope) == 0:
            return True
        await asyncio.sleep(0.05)
    return False


async def test_deleting_a_world_runs_its_purge_at_once(api: Api) -> None:
    r = await api.post(f"{API}/worlds", {"name": "Melaka", "cover": {"kind": "preset", "presetId": "cover_night_skyline"}},
                       status=201)
    wid = r.json()["id"]
    assert (await api.client.delete(f"{API}/worlds/{wid}")).status_code == 204
    assert await _drained(api, "world")


async def test_resetting_the_demo_runs_the_seed_sessions_purge_at_once(api: Api) -> None:
    await api.post(f"{API}/admin/reset-demo", {"confirm": True}, status=204)
    async with api.rt.db.read() as conn:
        queued = (await conn.execute(text("SELECT count(*) FROM ai_purge_queue WHERE scope = 'session'"))).scalar_one()
    assert queued >= 1
    assert await _drained(api, "session")
