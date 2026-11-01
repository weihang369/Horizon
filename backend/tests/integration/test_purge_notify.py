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


async def test_a_failing_purge_row_never_holds_up_the_rows_after_it(api: Api) -> None:
    """Audit 01-06 part 2: the backoff (up to 10 min) was slept inside the row loop, so every row queued after a failing
    one waited for it. Now the pass delivers the rest first and waits once at its end."""
    from typing import Any

    from horizon.services.purge import PurgeWorker

    await api.rt.purge.stop()   # this test's own worker owns the queue

    class Hooks:
        def __init__(self) -> None:
            self.delivered: list[str] = []

        async def on_delete(self, scope: str, ids: list[str]) -> None:
            if scope == "character":
                raise RuntimeError("hook down")
            self.delivered.extend(ids)

        async def on_forget(self, *_a: Any) -> None:
            return None

    never = asyncio.Event()

    async def stuck_backoff(_s: float) -> None:
        await never.wait()

    async with api.rt.db.write() as tx:
        for scope, ids in (("character", ["chr_x"]), ("session", ["ses_after"])):
            await tx.conn.execute(text("INSERT INTO ai_purge_queue (scope, ids, created_at, attempts) "
                                       "VALUES (:s, :i, '2026-10-27T00:00:00.000Z', 0)"), {"s": scope, "i": f'["{ids[0]}"]'})
    hooks = Hooks()
    worker = PurgeWorker(api.rt.db, hooks, api.rt.now_iso, sleeper=stuck_backoff)   # type: ignore[arg-type]
    worker.start()
    try:
        assert await _drained(api, "session")
        assert hooks.delivered == ["ses_after"] and await _undone(api, "character") == 1
        worker.notify()            # a new deletion ends the backoff early: the failure is retried with it
        for _ in range(100):
            async with api.rt.db.read() as conn:
                tries = (await conn.execute(text("SELECT attempts FROM ai_purge_queue WHERE scope = 'character'"))).scalar_one()
            if tries >= 2:
                break
            await asyncio.sleep(0.02)
        assert tries >= 2
    finally:
        await worker.stop()
