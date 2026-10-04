"""Energy routes (group 10; energy spec "Top-up route", "Set-max route", "Energy writes are serialised")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text

from horizon.domain.timeutil import to_iso
from horizon.gateway.pipeline import LedgerRow
from tests.conftest import Api

HANA = "chr_seedHana"
KEY = "sk-or-test-0001"


async def keyed(api: Api) -> None:
    assert (await api.client.put("/api/v1/settings/key", json={"key": KEY})).status_code == 200


async def set_energy(api: Api, current: float, *, max_: int = 1000, as_of: str | None = None) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE characters SET energy_current = :c, energy_max = :m, energy_spent_today = 0, "
                                   "energy_as_of = :a WHERE id = :i"),
                              {"c": current, "m": max_, "a": as_of or to_iso(api.rt.clock.now()), "i": HANA})


async def stored(api: Api) -> tuple[float, float, int]:
    async with api.rt.db.read() as conn:
        r = (await conn.execute(text("SELECT energy_current, energy_spent_today, energy_max FROM characters WHERE id = :i"),
                                {"i": HANA})).one()
    return float(r[0]), float(r[1]), int(r[2])


def capture(api: Api) -> tuple[list[Any], Any]:
    """Spy on the bus: committed writes publish through the database's publisher, not `rt.publish` directly."""
    events: list[Any] = []
    bus = api.rt.bus
    real = bus.publish

    def spy(channel: str, event: dict[str, Any]) -> None:
        events.append(event)
        real(channel, event)

    bus.publish = spy  # type: ignore[method-assign]
    return events, lambda: setattr(bus, "publish", real)


def top_up(api: Api, points: int, cid: str = HANA) -> Any:
    return api.client.post(f"/api/v1/characters/{cid}/energy/top-up", json={"points": points})


# ── 10.1 top-up ──
async def test_two_large_top_ups_under_a_small_cap(api: Api) -> None:
    await keyed(api)
    assert (await api.client.patch("/api/v1/settings", json={"budget": {"dailyCapUsd": 0.6}})).status_code == 200
    await set_energy(api, 100)
    first = await top_up(api, 5000)
    assert first.status_code == 200, first.text
    assert first.json()["current"] == 5100 and first.json()["state"] == "active"
    events, undo = capture(api)
    second = await top_up(api, 5000)
    undo()
    assert second.status_code == 402 and second.json()["error"]["code"] == "daily_budget_exceeded"
    assert second.json()["error"]["details"] == {"todayTopUpPoints": 5000, "points": 5000}
    assert (await api.json(f"/api/v1/characters/{HANA}"))["energy"]["current"] == 5100
    assert events == []  # a refused top-up publishes nothing


async def test_top_up_row_costs_nothing(api: Api) -> None:
    await keyed(api)
    before = (await api.json("/api/v1/settings"))["spentTodayUsd"]
    events, undo = capture(api)
    assert (await top_up(api, 500)).status_code == 200
    undo()
    rows = (await api.json("/api/v1/usage", params={"sinceDays": 1}))["items"]
    last = [r for r in rows if r["category"] == "energy_topup"][-1]
    assert last["energyPoints"] == 500 and last["costUsd"] == 0 and last["characterId"] == HANA
    assert (await api.json("/api/v1/settings"))["spentTodayUsd"] == before
    assert {"type": "entity.changed", "kind": "character", "id": HANA, "worldId": "wld_seedSunnyHollow"} in events


async def test_top_up_needs_a_key(api: Api) -> None:
    r = await top_up(api, 500)
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"
    await api.client.put("/api/v1/settings/key", json={"key": "sk-or-bad-zzz"})
    await api.client.post("/api/v1/settings/test-connection")  # OpenRouter rejects it → status invalid
    assert (await top_up(api, 500)).json()["error"]["code"] == "invalid_key"


async def test_top_up_unknown_character_and_bad_points(api: Api) -> None:
    await keyed(api)
    assert (await top_up(api, 500, "chr_nobody")).json()["error"]["code"] == "not_found"
    for bad in (0, -5, "lots"):
        r = await api.client.post(f"/api/v1/characters/{HANA}/energy/top-up", json={"points": bad})
        assert r.status_code == 422


# ── 10.2 set-max ──
async def test_lower_the_max(api: Api) -> None:
    await keyed(api)
    await set_energy(api, 800)
    r = await api.client.put(f"/api/v1/characters/{HANA}/energy/max", json={"points": 500})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["current"] == 800 and e["max"] == 500 and e["regenPerHour"] == pytest.approx(500 / 24) and "fullAt" not in e
    api.rt.schema.check("Energy", e)


async def test_set_max_in_demo_mode_applies_no_regen(api: Api) -> None:
    await set_energy(api, 300, as_of="2026-10-02T03:00:00.000Z")  # a day before START, no key → demo mode
    r = await api.client.put(f"/api/v1/characters/{HANA}/energy/max", json={"points": 1200})
    assert r.status_code == 200 and r.json()["current"] == 300
    assert await stored(api) == (300, 0, 1200)


# ── 10.3 a top-up racing a reply's drain ──
async def test_top_up_races_a_drain(api: Api) -> None:
    await keyed(api)
    gw = api.rt.gateway
    reply = LedgerRow(category="chat", purpose="reply", cost_usd=0.0005, cost_source="provider", estimated_cost_usd=0.0005,
                      price_period="off_peak", counts_to_creation_cap=False, character_id=HANA)
    for _ in range(50):
        await set_energy(api, 100)
        async with api.rt.db.write() as tx:  # D-76 bounds top-ups per day: start each round with a clean day
            await tx.conn.execute(text("DELETE FROM usage_records WHERE is_seed = 0"))
        r, _ = await asyncio.gather(top_up(api, 500), gw.ledger.record(reply, drain=True))
        assert r.status_code == 200
        cur, _spent, _ = await stored(api)
        assert cur == pytest.approx(595)
