"""Restart recovery and the kill tests (generation-jobs tasks 5.1–5.4, design D4, OQ-8)."""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import text

from horizon.gateway.fake import fake_png
from horizon.services import assets
from horizon.services.jobs.scheduler import INTERRUPTED
from tests.conftest import Api
from tests.jobs.kit import API, cancel_overlay_jobs, character, job, ledger, rows, start, until


async def stored_job(api: Api, kind: str = "portrait_candidates", cid: str = "chr_mockSarah") -> dict[str, Any]:
    """A job written straight to the database (no runner), as a crash would leave it."""
    rt = api.rt
    plan = rt.jobs.plan({"characterId": cid, "kind": kind})
    from horizon.domain.ids import new_id

    job_id = new_id("job")
    async with rt.db.write() as tx:
        ch = (await tx.conn.execute(text("SELECT * FROM characters WHERE id = :c"), {"c": cid})).mappings().one()
        await rt.jobs.insert_job(tx, ch, job_id, {"characterId": cid, "kind": kind}, plan)
        await tx.conn.execute(text("UPDATE generation_jobs SET status = 'running' WHERE id = :j"), {"j": job_id})
    out: dict[str, Any] = await job(api, job_id)
    return out


async def set_task(api: Api, task_id: str, **values: Any) -> None:
    cols = ", ".join(f"{k} = :{k}" for k in values)
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text(f"UPDATE generation_tasks SET {cols} WHERE id = :id"), {**values, "id": task_id})


# ── 5.1: the three task states, rows written directly ──
async def test_recover_never_sent_requeues(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    j = await stored_job(api)
    tid = j["tasks"][0]["id"]
    await set_task(api, tid, status="running", attempt=1, started_at="2026-10-03T02:59:00.000Z")
    assert await api.rt.jobs.recover() == [j["id"]]
    await api.drive(21000)
    done = await job(api, j["id"])
    assert done["status"] == "succeeded" and done["tasks"][0]["attempt"] == 1   # the interrupted attempt didn't count
    assert len(await ledger(api, j["id"])) == 1


async def test_recover_with_a_stored_result_derives_only(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    j = await stored_job(api)
    tid = j["tasks"][0]["id"]
    ref = assets.original_rel("wld_seedMeridian", "chr_mockSarah", tid, 1, "png")
    path = api.data_dir / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fake_png("stored", "3:4"))
    await set_task(api, tid, status="running", attempt=1, provider_called_at="2026-10-03T02:59:00.000Z", result_ref=ref)
    fake = api.rt.fake
    assert fake is not None
    before = sum(fake.counts.values())
    await api.rt.jobs.recover()
    await api.drive(1500)
    done = await job(api, j["id"])
    assert done["status"] == "succeeded" and done["tasks"][0]["resultRef"].startswith("cand_")
    assert sum(fake.counts.values()) == before and await ledger(api, j["id"]) == []
    cand = (await character(api, "chr_mockSarah"))["appearance"]["candidates"][0]
    assert cand["status"] == "ready" and (await api.get(cand["url"])).status_code == 200


async def test_recover_sent_without_a_result_fails_retryably(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    j = await stored_job(api)
    tid = j["tasks"][0]["id"]
    await set_task(api, tid, status="running", attempt=1, provider_called_at="2026-10-03T02:59:00.000Z")
    await api.rt.jobs.recover()
    await api.drive(1500)
    done = await job(api, j["id"])
    assert done["status"] == "failed"
    assert done["tasks"][0]["error"] == {"code": "provider_error", "message": INTERRUPTED, "retryable": True}
    assert (await character(api, "chr_mockSarah"))["appearance"]["candidates"][0]["status"] == "failed"
    assert await ledger(api, j["id"]) == []


# ── 5.2: kill tests (a SQLite online backup + a copy of data/ while a request is in flight) ──
def snapshot(src: Path, dst: Path) -> None:
    """What a power cut leaves: the committed database state and the files on disk at that moment."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("horizon.db*", "logs"))
    with sqlite3.connect(src / "horizon.db") as s, sqlite3.connect(dst / "horizon.db") as d:
        s.backup(d)


async def test_kill_mid_job_and_restart(make_api: Callable[..., Any], tmp_path: Path) -> None:
    a: Api = await make_api(data_dir=tmp_path / "a")
    await a.set_key()
    await cancel_overlay_jobs(a)
    await a.client.patch(f"{API}/settings", json={"generationMode": "standard"})
    await a.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"image": "naive"}}, status=204)
    fake = a.rt.fake
    assert fake is not None
    release = fake.park_image(fake.counts["images"] + 2)
    j = await start(a, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    await asyncio.wait_for(fake.parked.wait(), 5)

    async def first_ready() -> bool:
        return any(t["status"] == "succeeded" for t in (await job(a, j["id"]))["tasks"])

    await until(first_ready)
    snapshot(a.data_dir, tmp_path / "b")
    release.set()

    b: Api = await make_api(data_dir=tmp_path / "b")
    fb = b.rt.fake
    assert fb is not None
    await b.drive(30000)
    assert fb.counts["images"] == 0 and fb.counts["chat"] == 0   # recovery and the runner never call the provider
    done = await job(b, j["id"])
    assert done["status"] == "partial"
    ok = next(t for t in done["tasks"] if t["status"] == "succeeded")
    bad = next(t for t in done["tasks"] if t["status"] == "failed")
    assert bad["error"]["retryable"] and bad["error"]["message"] == INTERRUPTED
    cands = {c["id"]: c for c in (await character(b, "chr_mockSarah"))["appearance"]["candidates"]}
    assert cands[ok["resultRef"]]["status"] == "ready"
    assert sorted(c["status"] for c in cands.values()) == ["failed", "ready"]
    assert len(await ledger(b, j["id"])) == 1   # one row per paid call that was recorded before the cut


async def test_queued_task_resumes_once(make_api: Callable[..., Any], tmp_path: Path) -> None:
    a: Api = await make_api(data_dir=tmp_path / "a")
    await a.set_key()
    await cancel_overlay_jobs(a)
    await a.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"image": "naive"}}, status=204)
    j = await stored_job(a)   # never started: its task was never sent
    snapshot(a.data_dir, tmp_path / "b")
    b: Api = await make_api(data_dir=tmp_path / "b")
    await b.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"image": "naive"}}, status=204)
    fb = b.rt.fake
    assert fb is not None
    # recovery started the runner at startup with the scripted image port (the env profile); it is sent exactly once
    await b.drive(21000)

    async def finished() -> bool:
        return (await job(b, j["id"]))["status"] == "succeeded"

    await until(finished)
    assert len(await ledger(b, j["id"])) == 1


async def test_restart_with_a_job_in_flight(make_api: Callable[..., Any], tmp_path: Path) -> None:
    """local-backend "Restart with a job in flight": recovery runs before the first request is served."""
    a: Api = await make_api(data_dir=tmp_path / "a")
    await a.set_key()
    await cancel_overlay_jobs(a)
    j = await start(a, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    await a.drive(300)   # the scripted call is under way (sent)
    snapshot(a.data_dir, tmp_path / "b")
    b: Api = await make_api(data_dir=tmp_path / "b")
    first = await job(b, j["id"])   # the first request already sees the recovered state
    assert first["tasks"][0]["status"] == "failed" and first["tasks"][0]["error"]["message"] == INTERRUPTED


# ── 5.3: the test-mode overlay job ──
async def test_kenjis_overlay_job_finishes(api: Api) -> None:
    seeded = await rows(api, "SELECT id, provider_called_at FROM generation_tasks WHERE job_id = 'job_mockKenjiEmotions'")
    assert len(seeded) == 6 and all(r["provider_called_at"] is None for r in seeded)
    before = await character(api, "chr_mockKenji")
    await api.drive(60000)
    done = await job(api, "job_mockKenjiEmotions")
    assert done["status"] in ("succeeded", "partial", "failed")
    after = await character(api, "chr_mockKenji")
    for e in ("happy", "sad", "angry"):
        assert after["emotions"][e] == before["emotions"][e]
    assert "activeJobId" not in after


async def test_kenjis_overlay_job_with_a_key_succeeds(api: Api) -> None:
    await api.set_key()
    await api.drive(60000)
    assert (await job(api, "job_mockKenjiEmotions"))["status"] == "succeeded"
    ch = await character(api, "chr_mockKenji")
    assert all(ch["emotions"][e] for e in ("surprised", "thinking", "embarrassed"))


# ── 5.4: derived files and the sweeper ──
async def test_derived_file_re_made_for_free(make_api: Callable[..., Any], tmp_path: Path) -> None:
    a: Api = await make_api(data_dir=tmp_path / "a")
    await a.set_key()
    await cancel_overlay_jobs(a)
    j = await stored_job(a)
    tid = j["tasks"][0]["id"]
    ref = assets.original_rel("wld_seedMeridian", "chr_mockSarah", tid, 1, "png")
    (a.data_dir / ref).parent.mkdir(parents=True, exist_ok=True)
    (a.data_dir / ref).write_bytes(fake_png("stored", "3:4"))
    await set_task(a, tid, status="running", attempt=1, provider_called_at="2026-10-03T02:59:00.000Z", result_ref=ref)
    snapshot(a.data_dir, tmp_path / "b")
    b: Api = await make_api(data_dir=tmp_path / "b")
    fb = b.rt.fake
    assert fb is not None
    await b.drive(1500)
    assert (await job(b, j["id"]))["status"] == "succeeded"
    cand = (await character(b, "chr_mockSarah"))["appearance"]["candidates"][0]
    assert (await b.get(cand["url"])).status_code == 200
    assert sum(fb.counts.values()) == 0


async def test_leftover_temp_and_old_orphans_are_swept(make_api: Callable[..., Any], tmp_path: Path) -> None:
    data = tmp_path / "data"
    a: Api = await make_api(data_dir=data)
    gen = data / "assets" / "gen" / "wld_seedMeridian" / "chr_mockSarah"
    gen.mkdir(parents=True, exist_ok=True)
    (gen / "portrait_happy_v9.webp.1a2b3c4d.tmp").write_bytes(b"partial")
    old = gen / "candidate_cand_orphan.webp"
    old.write_bytes(b"x")
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    fresh = gen / "candidate_cand_fresh.webp"
    fresh.write_bytes(b"x")
    original = data / "originals" / "wld_seedMeridian" / "chr_mockSarah" / "task_x_a1.png"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"x")
    os.utime(original, (time.time() - 7200, time.time() - 7200))
    await a.client.aclose()
    await a.rt.stop()
    await make_api(data_dir=data)
    assert not (gen / "portrait_happy_v9.webp.1a2b3c4d.tmp").exists()
    assert not old.exists() and fresh.exists() and original.exists()
