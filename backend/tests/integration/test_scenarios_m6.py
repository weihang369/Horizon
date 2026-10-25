"""M6 test scenarios (http-client-parity design D3–D5; http-api "Test-only control routes"; tasks 1.1–1.4):
scenarios replace each other, reset-demo clears the active one in test mode, `daily_cap` is a spend bias with no ledger
row, and `no_worlds` deletes every world while settings, the key and the ledger stay."""

from __future__ import annotations

from typing import Any

from tests.conftest import Api
from tests.jobs.kit import API, cancel_overlay_jobs, job, rows, start
from tests.sessions.kit import create

COVER = {"kind": "preset", "presetId": "cover_night_skyline"}


async def _scenario(api: Api, sid: str) -> None:
    assert (await api.post(f"{API}/_test/scenario", {"id": sid})).status_code == 204


async def _ledger_ids(api: Api) -> list[str]:
    return [r["id"] for r in await rows(api, "SELECT id FROM usage_records ORDER BY id")]


def _drain(sub: Any) -> list[dict[str, Any]]:
    out = []
    while not sub.queue.empty():
        x = sub.queue.get_nowait()
        if isinstance(x, dict):
            out.append(x)
    return out


async def test_scenarios_replace_each_other(api: Api) -> None:
    await _scenario(api, "rush_hour")
    assert (await api.json(f"{API}/settings"))["pricing"]["period"] == "peak"
    await _scenario(api, "stream_cut")
    clock = api.rt.clock
    own = clock.calendar.period(clock.now())
    assert (await api.json(f"{API}/settings"))["pricing"]["period"] == own
    assert clock.period_override is None
    assert api.rt.stream_faults == [24]   # the new scenario is applied, only once


async def test_reset_demo_clears_the_scenario_in_test_mode(api: Api) -> None:
    await api.set_key()
    await _scenario(api, "image_fail_all")
    assert api.rt.job_faults == "all"
    await api.post(f"{API}/admin/reset-demo", {"confirm": True}, status=204)
    assert api.rt.job_faults is None
    await cancel_overlay_jobs(api)
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"


async def test_daily_cap_is_a_bias_without_a_ledger_row(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    before = await _ledger_ids(api)
    real = (await api.json(f"{API}/settings"))["spentTodayUsd"]
    sub = api.rt.bus.subscribe("global")
    await _scenario(api, "daily_cap")
    s = await api.json(f"{API}/settings")
    cap = s["budget"]["dailyCapUsd"]
    assert s["spentTodayUsd"] == cap
    assert await api.rt.gateway.ledger.spent_today() == cap   # the preflight path sees it too
    assert any(e.get("type") == "entity.changed" and e.get("kind") == "settings" for e in _drain(sub))

    r = await api.post(f"{API}/characters/chr_seedHana/energy/top-up", {"points": 500})
    assert r.status_code == 402 and r.json()["error"]["code"] == "daily_budget_exceeded"
    assert await _ledger_ids(api) == before

    await api.post(f"{API}/admin/reset-demo", {"confirm": True}, status=204)
    assert (await api.json(f"{API}/settings"))["spentTodayUsd"] == real


async def test_daily_cap_refuses_a_send(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    await _scenario(api, "daily_cap")
    r = await api.post(f"{API}/sessions/{sid}/send", {"text": "hello"})
    assert r.status_code == 402 and r.json()["error"]["code"] == "daily_budget_exceeded"


async def test_no_worlds_then_reset(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    user = (await api.post(f"{API}/worlds", {"name": "My Harbour", "cover": COVER}, status=201)).json()
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    ledger = await _ledger_ids(api)
    key_status = (await api.json(f"{API}/settings"))["openRouterKeyStatus"]
    sub = api.rt.bus.subscribe("global")

    await _scenario(api, "no_worlds")
    assert await api.json(f"{API}/worlds") == []
    assert any(e.get("type") == "mock.reset" for e in _drain(sub))
    assert (await api.json(f"{API}/settings"))["openRouterKeyStatus"] == key_status
    assert await _ledger_ids(api) == ledger
    await api.drive(30000)
    assert await rows(api, "SELECT id FROM generation_jobs WHERE status IN ('queued','running')") == []
    assert (await api.get(f"{API}/jobs/{j['id']}")).status_code == 404

    await api.post(f"{API}/admin/reset-demo", {"confirm": True}, status=204)
    worlds = await api.json(f"{API}/worlds")
    assert sorted(w["id"] for w in worlds) == ["wld_seedMeridian", "wld_seedSunnyHollow"]
    assert user["id"] not in {w["id"] for w in worlds}
