"""Corrections survive a restart (task 7.2): recent estimate rows resume, rows older than 24 h are left alone."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text

from tests.conftest import Api


async def insert_estimate(api: Api, row_id: str, at: str, gid: str) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text(
            "INSERT INTO usage_records(id, at, local_day, category, purpose, generation_id, cost_usd, cost_source, "
            "estimated_cost_usd, counts_to_creation_cap, is_seed) VALUES (:id, :at, substr(:at, 1, 10), 'chat', 'host', :g, "
            "0.0006, 'estimate', 0.0006, 0, 0)"), {"id": row_id, "at": at, "g": gid})


async def test_restart_resumes_recent_corrections(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "restart"
    first: Api = await make_api(data_dir=data)
    first.rt.keys.set_key("sk-or-test-0001")  # the secrets file survives the restart, like a user's saved key
    await insert_estimate(first, "use_recent", "2026-10-03T02:50:00.000Z", "gen-restart-recent")   # 10 min before START
    await insert_estimate(first, "use_stale", "2026-10-02T02:00:00.000Z", "gen-restart-stale")     # 25 h before START
    await first.rt.stop()  # the backend stops while the row awaits correction

    second: Api = await make_api(data_dir=data)
    rt = second.rt
    assert rt.fake is not None
    rt.fake.costs["gen-restart-recent"] = 0.00041  # OpenRouter has indexed the generation by now
    rt.fake.costs["gen-restart-stale"] = 0.00041
    await rt.corrector.idle()  # first lookup may have raced the registration: it retries after the 2 s backoff
    async with rt.db.read() as conn:
        rows = {r["id"]: r for r in (await conn.execute(text(
            "SELECT id, cost_usd, cost_source FROM usage_records WHERE id IN ('use_recent', 'use_stale')"))).mappings()}
    assert rows["use_recent"]["cost_source"] == "provider" and rows["use_recent"]["cost_usd"] == 0.00041
    assert rows["use_stale"]["cost_source"] == "estimate" and rows["use_stale"]["cost_usd"] == 0.0006
