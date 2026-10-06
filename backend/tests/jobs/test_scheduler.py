"""The JobScheduler under the frozen clock (generation-jobs tasks 2.2, 2.3)."""

from __future__ import annotations

import asyncio

import pytest

from tests.conftest import Api
from tests.jobs.kit import API, Recorder, cancel_overlay_jobs, character, job, ledger, rows, start


async def test_lean_portrait_job_runs_to_the_end(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    rec = Recorder(api.rt)
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    assert j["status"] == "queued" and len(j["tasks"]) == 1 and j["estimatedCostUsd"] == 0.018
    ch = await character(api, "chr_mockSarah")
    assert ch["activeJobId"] == j["id"]
    await api.drive(21000)
    done = await job(api, j["id"])
    assert done["status"] == "succeeded" and done["progress"] == 1 and done["finishedAt"]
    assert done["actualCostUsd"] == pytest.approx(0.018)
    ch = await character(api, "chr_mockSarah")
    assert "activeJobId" not in ch
    (cand,) = ch["appearance"]["candidates"]
    assert cand["status"] == "ready" and cand["url"].startswith("/assets/gen/wld_seedMeridian/chr_mockSarah/candidate_")
    (row,) = await ledger(api, j["id"])
    assert row["provider"] == "scripted" and row["category"] == "image" and row["purpose"] == "image_portrait"
    # events: monotonic progress, task updates, exactly one job.done (each payload was schema-checked at publish)
    progress = [e["job"]["progress"] for e in rec.of(j["id"], "job.progress")]
    assert progress and progress == sorted(progress) and max(progress) <= 0.95
    assert len(rec.of(j["id"], "job.done")) == 1
    assert rec.of(j["id"], "job.done")[0]["job"]["status"] == "succeeded"
    statuses = [e["task"]["status"] for e in rec.of(j["id"], "task.update")]
    assert statuses[0] == "running" and statuses[-1] == "succeeded"
    assert any(e["type"] == "entity.changed" and e["kind"] == "job" and e.get("id") == j["id"] for e in rec.events)


async def test_lean_emotion_set_estimate_and_plan(api: Api) -> None:
    """generation-jobs "Lean emotion set estimate" and "Lean emotion set"."""
    r = await api.post(f"{API}/jobs/estimate", {"characterId": "chr_mockSarah", "kind": "emotion_set"}, status=200)
    assert r.json() == {"estimatedCostUsd": 0.054}
    assert await rows(api, "SELECT id FROM usage_records WHERE is_seed = 0") == []
    await api.set_key()
    j = await start(api, {"characterId": "chr_seedHana", "kind": "emotion_set"})
    assert [(x["type"], x.get("emotion")) for x in j["tasks"]] == [("emotion_image", "happy"), ("emotion_image", "sad"),
                                                                   ("emotion_image", "angry")]


async def test_estimate_for_a_tombstone_is_not_found(api: Api) -> None:
    async with api.rt.db.write() as tx:
        from sqlalchemy import text
        await tx.conn.execute(text("UPDATE characters SET deleted_at = '2026-10-03T03:00:00.000Z' WHERE id = 'chr_seedVictor'"))
    r = await api.post(f"{API}/jobs/estimate", {"characterId": "chr_seedVictor", "kind": "song"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


async def test_second_job_for_the_same_character_conflicts(api: Api) -> None:
    await api.set_key()
    await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    r = await api.post(f"{API}/jobs", {"characterId": "chr_mockSarah", "kind": "song"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    jobs = await rows(api, "SELECT id FROM generation_jobs WHERE character_id = 'chr_mockSarah'")
    assert len(jobs) == 1


async def test_without_a_key_nothing_is_stored(api: Api) -> None:
    r = await api.post(f"{API}/jobs", {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"
    assert await rows(api, "SELECT id FROM generation_jobs WHERE character_id = 'chr_mockSarah'") == []


async def test_standard_candidates_and_parallelism(api: Api) -> None:
    await api.set_key()
    await api.client.patch(f"{API}/settings", json={"generationMode": "standard"})
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    assert len(j["tasks"]) == 2
    ch = await character(api, "chr_mockSarah")
    assert [c["status"] for c in ch["appearance"]["candidates"]] == ["generating", "generating"]
    await api.drive(300)
    running = [x for x in (await job(api, j["id"]))["tasks"] if x["status"] == "running"]
    assert len(running) == 2  # portraitParallel = 2
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"


async def test_same_idempotency_key_after_a_restart(make_api: object, tmp_path: object) -> None:
    from pathlib import Path

    data = Path(str(tmp_path)) / "idem"
    a: Api = await make_api(data_dir=data)  # type: ignore[operator]
    await a.set_key()
    headers = {"Idempotency-Key": "idem-job-1"}
    body = {"characterId": "chr_mockSarah", "kind": "portrait_candidates"}
    first = await start(a, body, headers=headers)
    await a.client.aclose()
    await a.rt.stop()
    b: Api = await make_api(data_dir=data)  # type: ignore[operator]
    await b.set_key()
    r = await b.post(f"{API}/jobs", body, headers=headers)
    assert r.status_code == 201 and r.json()["id"] == first["id"] and r.headers.get("idempotent-replay") == "true"
    assert len(await rows(b, "SELECT id FROM generation_jobs WHERE character_id = 'chr_mockSarah'")) == 1


async def test_stop_waits_for_a_shielded_write(api: Api) -> None:
    """A cancelled attempt's `provider_called_at` write runs on; stop() waits for it, so nothing reopens the database
    after it is disposed (that blocked a factory reset's wipe on Windows)."""
    sched = api.rt.jobs
    entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def write() -> None:
        entered.set()
        await release.wait()
        finished.set()

    caller = asyncio.ensure_future(sched.shielded("mark:test", write()))
    await entered.wait()
    caller.cancel()
    stopping = asyncio.ensure_future(sched.stop())
    await asyncio.sleep(0.05)
    assert not stopping.done()   # the shielded write is still running
    release.set()
    await asyncio.wait_for(stopping, 5)
    assert finished.is_set() and caller.cancelled()

