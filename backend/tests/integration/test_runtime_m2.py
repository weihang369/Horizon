"""Runtime wiring (task 11.1, design D15): factory reset tears M2 state down; a real test-mode server uses the fake."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from tests.conftest import Api, Live
from tests.gwkit import block_network

KEY = "sk-or-test-0001"


async def test_factory_reset_during_a_pending_correction(api: Api) -> None:
    rt = api.rt
    await api.client.put("/api/v1/settings/key", json={"key": KEY})
    async with rt.db.write() as tx:
        await tx.conn.execute(text(
            "INSERT INTO usage_records(id, at, local_day, category, purpose, generation_id, cost_usd, cost_source, "
            "estimated_cost_usd, counts_to_creation_cap, is_seed) VALUES ('use_pending', '2026-10-03T02:59:00.000Z', "
            "'2026-10-03', 'chat', 'host', 'gen-never-indexed', 0.0006, 'estimate', 0.0006, 0, 0)"))
    rt.corrector.enqueue("use_pending")  # the fake answers 404: it sits in backoff
    rt.book.reserve(0.25)
    old_corrector = rt.corrector
    await asyncio.sleep(0.05)
    assert old_corrector.pending == 1

    r = await api.client.post("/api/v1/admin/factory-reset", json={"confirm": "DELETE EVERYTHING"})
    assert r.status_code == 204
    assert old_corrector.pending == 0 and rt.corrector is not old_corrector and rt.corrector.pending == 0
    # The old holds are gone; the only one is the test-mode overlay job's remaining estimate, re-reserved by the
    # restart's job recovery (M4, generation-jobs design D4).
    assert rt.book.total() == pytest.approx(rt.book.job_remaining("job_mockKenjiEmotions"))
    assert not (api.data_dir / "secrets.local.json").exists()
    s = await api.json("/api/v1/settings")
    assert s["openRouterKeyStatus"] == "missing" and s["demoMode"] is True
    names = {t.get_name() for t in asyncio.all_tasks()}
    assert not any(n.startswith("correct:") for n in names)


def test_test_mode_server_answers_from_the_fake(live: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = block_network(monkeypatch)
    with httpx.Client(base_url=f"{live.base}/api/v1", timeout=30) as c:
        assert c.put("/settings/key", json={"key": KEY}).status_code == 200
        r = c.post("/settings/test-connection")
        assert r.status_code == 200 and r.json()["creditsUsd"] == 4.21
        bad: Any = c.put("/settings/key", json={"key": "sk-or-bad-zzz"})
        assert bad.status_code == 200
        assert c.post("/settings/test-connection").json()["error"]["code"] == "invalid_key"
    assert attempts == []
