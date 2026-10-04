"""Ledger writer (task 6.2, spend-ledger "One row per paid call", energy "Only a character's own reply drains")."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from horizon.domain.timeutil import ms_from_iso, to_iso
from horizon.gateway.pipeline import LedgerRow
from horizon.services import energy_writes
from horizon.services.energy_writes import EnergyLocks, EnergyParams
from horizon.services.ledger import LedgerWriter
from tests.conftest import Api


def params(api: Api) -> EnergyParams:
    return EnergyParams(now_ms=ms_from_iso(to_iso(api.rt.clock.now())), frozen=False, est_reply_points=4,
                        usd_per_point=0.0001, utc_offset_min=480)


def writer(api: Api) -> LedgerWriter:
    return LedgerWriter(api.rt.db, api.rt.clock, EnergyLocks(), lambda: params(api))


def row(**kw: Any) -> LedgerRow:
    base: dict[str, Any] = {"category": "chat", "purpose": "reply", "cost_usd": 0.00042, "cost_source": "provider",
                            "estimated_cost_usd": 0.0006, "price_period": "off_peak", "counts_to_creation_cap": False,
                            "character_id": "chr_seedHana", "model": "deepseek/deepseek-v4.1-flash", "provider": "DeepSeek"}
    return LedgerRow(**{**base, **kw})


async def energy(api: Api, cid: str = "chr_seedHana") -> tuple[float, float]:
    async with api.rt.db.read() as conn:
        r = (await conn.execute(text("SELECT energy_current, energy_spent_today FROM characters WHERE id = :i"), {"i": cid})).one()
    return float(r[0]), float(r[1])


async def set_energy(api: Api, current: float, cid: str = "chr_seedHana") -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE characters SET energy_current = :c, energy_spent_today = 0, energy_as_of = :a "
                                   "WHERE id = :i"), {"c": current, "a": to_iso(api.rt.clock.now()), "i": cid})


async def rows(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text("SELECT * FROM usage_records WHERE is_seed = 0 ORDER BY at, id"))).mappings())


async def test_reply_row_and_drain_commit_together(api: Api) -> None:
    await set_energy(api, 500)
    lw = writer(api)
    before = await lw.spent_today()
    res = await lw.record(row(), drain=True)
    assert res.spent_after == pytest.approx(before + 0.00042)
    (r,) = await rows(api)
    assert r["category"] == "chat" and r["purpose"] == "reply" and r["cost_source"] == "provider"
    assert r["provider"] == "DeepSeek" and r["price_period"] == "off_peak" and r["estimated_cost_usd"] == 0.0006
    assert await energy(api) == (495, 5)


async def test_failure_rolls_back_row_and_drain(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    await set_energy(api, 500)

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("disk full")

    monkeypatch.setattr("horizon.services.ledger.apply_energy", boom)
    with pytest.raises(RuntimeError):
        await writer(api).record(row(), drain=True)
    assert await rows(api) == []
    assert await energy(api) == (500, 0)


async def test_non_reply_purpose_leaves_energy(api: Api) -> None:
    await set_energy(api, 500)
    await writer(api).record(row(category="decision", purpose="route", cost_usd=0.00003), drain=False)
    assert await energy(api) == (500, 0)
    assert len(await rows(api)) == 1


async def test_overdraft_clamps_at_zero(api: Api) -> None:
    await set_energy(api, 3)
    await writer(api).record(row(cost_usd=0.0012), drain=True)  # 12 points
    assert await energy(api) == (0, 12)


async def test_text_columns_are_redacted(api: Api) -> None:
    await writer(api).record(row(provider="echo sk-or-test-0001", purpose="route", category="decision"), drain=False)
    (r,) = await rows(api)
    assert "sk-or-test" not in str(dict(r))


async def test_creation_spend_and_reads(api: Api) -> None:
    lw = writer(api)
    res = await lw.record(row(purpose="image_portrait", category="image", cost_usd=0.018, counts_to_creation_cap=True,
                              message_id=None), drain=False)
    assert res.creation_before == 0 and res.creation_after == pytest.approx(0.018)
    assert await lw.creation_spent("chr_seedHana") == pytest.approx(0.018)
    await lw.record(row(message_id="msg_x1"), drain=True)
    await lw.record(row(message_id="msg_x1", purpose="route", category="decision", cost_usd=0.00003), drain=False)
    calls = await lw.calls_for_message("msg_x1")
    assert {c["purpose"] for c in calls} == {"reply", "route"}
    usage = await lw.reply_usage("msg_x1")
    assert usage is not None and usage["costUsd"] == 0.00042


async def test_deleted_character_keeps_the_spend(api: Api) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE characters SET deleted_at = '2026-10-03T00:00:00.000Z' WHERE id = 'chr_seedHana'"))
    await writer(api).record(row(), drain=True)
    assert len(await rows(api)) == 1


def test_module_has_no_network_import() -> None:
    assert not hasattr(energy_writes, "httpx")
