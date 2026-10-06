"""The paid-call hooks for never-pay-twice (generation-jobs task 1.4, design D3, D-84; provider-gateway "Paid calls can
mark and commit with their caller")."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.gateway.fake import FakeOpenRouter
from horizon.gateway.images import ImageResult
from horizon.gateway.pipeline import Caps
from tests.conftest import Api
from tests.gwkit import build_gateway

MODEL = "bytedance-seed/seedream-5-0-flash"


async def rows(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text("SELECT * FROM usage_records WHERE is_seed = 0"))).mappings())


async def marks(api: Api) -> list[str]:
    async with api.rt.db.read() as conn:
        return [r[0] for r in await conn.execute(text("SELECT key FROM idempotency_keys WHERE path = 'hook-test' ORDER BY key"))]


async def mark(api: Api, conn: AsyncConnection | None, key: str) -> None:
    """A stand-in for a job's durable write (any small row will do)."""
    sql = text("INSERT INTO idempotency_keys(key, method, path, body_sha256, state, created_at, expires_at) "
               "VALUES (:k, 'POST', 'hook-test', '', 'done', '2026-10-03T03:00:00.000Z', '2099-01-01T00:00:00.000Z')")
    if conn is not None:
        await conn.execute(sql, {"k": key})
        return
    async with api.rt.db.write() as tx:
        await tx.conn.execute(sql, {"k": key})


def fake_gateway(api: Api, fake: FakeOpenRouter, **kw: Any) -> Any:
    return build_gateway(api, transport=fake.transport(), **kw)


CTX = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_seedHana", job_id=None)


async def test_hooks_run_in_order_and_commit_together(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = fake_gateway(api, fake)
    order: list[str] = []
    seen_in_tx: dict[str, Any] = {}

    async def before() -> None:
        order.append(f"before_send(sent={fake.counts['images']})")
        await mark(api, None, "a-sent")

    async def after(r: ImageResult) -> None:
        order.append(f"after_response(images={len(r.images)})")

    async def commit(conn: AsyncConnection, row_id: str) -> None:
        order.append("commit_with")
        await mark(api, conn, "b-result")
        seen_in_tx["row"] = (await conn.execute(text("SELECT id FROM usage_records WHERE id = :i"), {"i": row_id})).scalar()

    r = await gw.generate_image(CTX, model=MODEL, prompt="p", before_send=before, after_response=after, commit_with=commit)
    assert r.images and fake.counts["images"] == 1
    assert order == ["before_send(sent=0)", "after_response(images=1)", "commit_with"]
    assert seen_in_tx["row"] is not None  # the row and the caller's step share one transaction
    assert await marks(api) == ["a-sent", "b-result"] and len(await rows(api)) == 1
    assert gw.book.total() == 0


async def test_refusal_runs_no_hook(api: Api) -> None:
    """provider-gateway "Refused job task is not marked as sent"."""
    fake = FakeOpenRouter()
    gw = fake_gateway(api, fake, caps=Caps(daily_cap_usd=1.0, creation_cap_usd=0.01, warn_at_pct=80))
    calls: list[str] = []

    async def before() -> None:
        calls.append("before")

    async def after(_r: ImageResult) -> None:
        calls.append("after")

    async def commit(_c: AsyncConnection, _i: str) -> None:
        calls.append("commit")

    ctx = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_seedHana", creation=True)
    with pytest.raises(ProviderError) as e:
        await gw.generate_image(ctx, model=MODEL, prompt="p", before_send=before, after_response=after, commit_with=commit)
    assert e.value.code == "creation_budget_exceeded"
    assert calls == [] and fake.counts["images"] == 0 and await rows(api) == []


async def test_after_response_failure_still_records_one_row(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = fake_gateway(api, fake)
    committed: list[str] = []

    async def after(_r: ImageResult) -> None:
        raise OSError("disk full")

    async def commit(_c: AsyncConnection, row_id: str) -> None:
        committed.append(row_id)

    with pytest.raises(OSError):
        await gw.generate_image(CTX, model=MODEL, prompt="p", after_response=after, commit_with=commit)
    await gw.drain_background()
    (row,) = await rows(api)
    assert row["cost_usd"] == pytest.approx(0.018) and row["cost_source"] == "provider"
    assert committed == [] and fake.counts["images"] == 1 and gw.book.total() == 0


async def test_failing_commit_with_rolls_back_its_row_then_spend_is_kept(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = fake_gateway(api, fake)
    attempts: list[str] = []

    async def commit(conn: AsyncConnection, row_id: str) -> None:
        attempts.append(row_id)
        await mark(api, conn, "never")
        raise RuntimeError("constraint")

    with pytest.raises(RuntimeError):
        await gw.generate_image(CTX, model=MODEL, prompt="p", commit_with=commit)
    await gw.drain_background()
    remaining = await rows(api)
    assert len(attempts) == 1 and await marks(api) == []          # the caller's write rolled back...
    assert attempts[0] not in {r["id"] for r in remaining}        # ...together with the row in that transaction
    assert len(remaining) == 1                                    # the spend itself is recorded once, separately


async def test_ledger_extra_rolls_back_the_row(api: Api) -> None:
    from horizon.gateway.pipeline import LedgerRow

    async def boom(conn: AsyncConnection, _row_id: str) -> None:
        await mark(api, conn, "x")
        raise RuntimeError("no")

    row = LedgerRow(category="image", purpose="image_portrait", cost_usd=0.018, cost_source="provider",
                    estimated_cost_usd=0.018, price_period="off_peak", counts_to_creation_cap=False)
    with pytest.raises(RuntimeError):
        await api.rt.ledger.record(row, drain=False, extra=boom)
    assert await rows(api) == [] and await marks(api) == []


async def test_scripted_generation_bills_scripted_row(api: Api) -> None:
    fake = FakeOpenRouter()
    gw = fake_gateway(api, fake)

    async def produce() -> bytes:
        return b"png"

    ctx = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_seedHana", job_id=None)
    assert await gw.scripted_generation(ctx, cost_usd=0.018, model=MODEL, produce=produce) == b"png"
    (row,) = await rows(api)
    assert row["provider"] == "scripted" and row["category"] == "image" and row["cost_usd"] == pytest.approx(0.018)
    assert sum(fake.counts.values()) == 0


# ── Gateway.reserve_job (task 1.5, budget-caps "Jobs are refused before they are queued") ──
async def spend(api: Api, usd: float, *, character_id: str | None = None, creation: bool = False) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text(
            "INSERT INTO usage_records(id, at, local_day, category, cost_usd, cost_source, counts_to_creation_cap, "
            "character_id, is_seed) VALUES (:id, '2026-10-03T02:00:00.000Z', '2026-10-03', 'image', :c, 'provider', "
            ":cr, :ch, 0)"), {"id": f"use_pre{int(usd * 1e6)}", "c": usd, "cr": creation, "ch": character_id})


async def test_creation_cap_blocks_a_portrait_job(api: Api) -> None:
    events: list[Any] = []
    fake = FakeOpenRouter()
    gw = fake_gateway(api, fake, events=events)
    await spend(api, 0.59, character_id="chr_mockSarah", creation=True)
    ctx = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_mockSarah", job_id="job_x",
                   creation=True)
    with pytest.raises(ProviderError) as e:
        await gw.reserve_job(ctx, 0.018)
    assert e.value.code == "creation_budget_exceeded"
    assert gw.book.total() == 0 and sum(fake.counts.values()) == 0
    (ev,) = events
    assert ev["type"] == "budget.reached" and ev["scope"] == "creation" and "jobId" not in ev
    api.rt.schema.check("GlobalEvent", ev)


async def test_two_jobs_share_the_daily_headroom(api: Api) -> None:
    events: list[Any] = []
    gw = fake_gateway(api, FakeOpenRouter(), events=events)
    await spend(api, 0.95)
    first = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_mockSarah", job_id="job_a",
                     creation=True)
    second = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_mockKenji", job_id="job_b",
                      creation=True)
    await gw.reserve_job(first, 0.036)
    assert gw.book.job_remaining("job_a") == pytest.approx(0.036)
    with pytest.raises(ProviderError) as e:
        await gw.reserve_job(second, 0.036)
    assert e.value.code == "daily_budget_exceeded" and gw.book.job_remaining("job_b") == 0
    gw.book.release_job("job_a")
    await gw.reserve_job(second, 0.036)  # the headroom is back once the first job's hold is released


async def test_retry_adds_to_the_job_hold(api: Api) -> None:
    gw = fake_gateway(api, FakeOpenRouter())
    ctx = call_ctx("image_portrait", world_id="wld_seedMeridian", character_id="chr_seedHana", job_id="job_r")
    await gw.reserve_job(ctx, 0.018)
    await gw.reserve_job(ctx, 0.018, existing=True)
    assert gw.book.job_remaining("job_r") == pytest.approx(0.036)
