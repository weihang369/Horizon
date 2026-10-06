"""Helpers for generation-job tests: the in-process app under the frozen clock, scripted profile, a fake key."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from horizon.events.bus import GLOBAL
from horizon.runtime import Runtime
from tests.conftest import Api

API = "/api/v1"


class Recorder:
    """Every event published on the global channel, in order (captured at the bus, after commit)."""

    def __init__(self, rt: Runtime) -> None:
        self.events: list[dict[str, Any]] = []
        original = rt.bus.publish

        def publish(channel: str, event: dict[str, Any]) -> None:
            if channel == GLOBAL:
                self.events.append(event)
            original(channel, event)

        rt.bus.publish = publish  # type: ignore[method-assign]

    def of(self, job_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        out = []
        for e in self.events:
            jid = e.get("jobId") or (e.get("job") or {}).get("id")
            if jid == job_id and (kind is None or e["type"] == kind):
                out.append(e)
        return out


async def start(api: Api, body: dict[str, Any], status: int = 201, **kw: Any) -> dict[str, Any]:
    r = await api.post(f"{API}/jobs", body, **kw)
    assert r.status_code == status, r.text
    out: dict[str, Any] = r.json()
    return out


async def job(api: Api, job_id: str) -> dict[str, Any]:
    out: dict[str, Any] = await api.json(f"{API}/jobs/{job_id}")
    return out


async def character(api: Api, cid: str) -> dict[str, Any]:
    out: dict[str, Any] = await api.json(f"{API}/characters/{cid}")
    return out


async def rows(api: Api, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with api.rt.db.read() as conn:
        return [dict(r) for r in (await conn.execute(text(sql), params)).mappings()]


async def ledger(api: Api, job_id: str) -> list[dict[str, Any]]:
    return await rows(api, "SELECT * FROM usage_records WHERE job_id = :j ORDER BY at, id", j=job_id)


async def cancel_overlay_jobs(api: Api) -> None:
    """The test-mode overlay job (Kenji) runs in the background; tests that count spend or events stop it first."""
    for j in await rows(api, "SELECT id FROM generation_jobs WHERE status IN ('queued','running')"):
        await api.rt.jobs.cancel(j["id"])


async def until(pred: Callable[[], Any], within: float = 5.0) -> None:
    """Poll a (sync or async) condition in real time: naive calls and parked requests don't move on the clock."""
    deadline = asyncio.get_running_loop().time() + within
    while True:
        v = pred()
        if asyncio.iscoroutine(v):
            v = await v
        if v:
            return
        assert asyncio.get_running_loop().time() < deadline, "condition not met in time"
        await asyncio.sleep(0.02)
