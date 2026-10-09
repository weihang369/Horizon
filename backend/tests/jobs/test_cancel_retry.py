"""Cancel, retry and the fault scenarios (generation-jobs tasks 4.1–4.3)."""

from __future__ import annotations

import asyncio

import pytest

from tests.conftest import Api
from tests.jobs.kit import API, Recorder, cancel_overlay_jobs, character, job, ledger, rows, start, until


async def setup(api: Api, *, standard: bool = False, scenario: str | None = None) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    if standard:
        assert (await api.client.patch(f"{API}/settings", json={"generationMode": "standard"})).status_code == 200
    if scenario:
        assert (await api.post(f"{API}/_test/scenario", {"id": scenario})).status_code == 204


async def lock(api: Api, cid: str) -> None:
    j = await start(api, {"characterId": cid, "kind": "portrait_candidates"})
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    cand = next(c for c in (await character(api, cid))["appearance"]["candidates"] if c["status"] == "ready")
    await api.post(f"{API}/characters/{cid}/lock-portrait", {"candidateId": cand["id"]}, status=200)


async def test_cancel_during_an_emotion_set(api: Api) -> None:
    """A sent call finishes at its real cost; its result is kept, not applied (D-86)."""
    await setup(api)
    await lock(api, "chr_mockSarah")
    await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"image": "naive"}})
    fake = api.rt.fake
    assert fake is not None
    first = fake.counts["images"]
    release = fake.park_image(first + 2)   # the second emotion's request is held in flight
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "emotion_set"})
    await asyncio.wait_for(fake.parked.wait(), 5)

    async def one_done() -> bool:
        return any(t["status"] == "succeeded" for t in (await job(api, j["id"]))["tasks"])

    await until(one_done)
    rec = Recorder(api.rt)
    r = await api.post(f"{API}/jobs/{j['id']}/cancel", status=200)
    body = r.json()
    assert body["status"] == "cancelled" and body["finishedAt"]
    statuses = [t["status"] for t in body["tasks"]]
    assert statuses.count("succeeded") == 1 and statuses.count("skipped") == 2
    assert "activeJobId" not in await character(api, "chr_mockSarah")
    assert rec.of(j["id"], "job.done")
    release.set()

    async def in_flight_recorded() -> bool:
        return len(await ledger(api, j["id"])) == 2

    await until(in_flight_recorded)
    await api.rt.gateway.drain_background()
    assert fake.counts["images"] == first + 2   # the third emotion was never sent
    ch = await character(api, "chr_mockSarah")
    done = next(t for t in body["tasks"] if t["status"] == "succeeded")
    skipped_sent = next(t for t in (await job(api, j["id"]))["tasks"] if t["status"] == "skipped" and t["emotion"] != "angry")
    assert ch["emotions"][done["emotion"]] is not None
    assert ch["emotions"][skipped_sent["emotion"]] is None   # stored, not applied
    assert all(r["cost_usd"] == pytest.approx(0.018) for r in await ledger(api, j["id"]))
    assert (await job(api, j["id"]))["status"] == "cancelled"


async def test_partial_failure_then_retry(api: Api) -> None:
    await setup(api, standard=True, scenario="image_fail_partial")
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    await api.drive(25000)
    done = await job(api, j["id"])
    assert done["status"] == "partial"
    failed = next(t for t in done["tasks"] if t["status"] == "failed")
    assert failed["error"] == {"code": "provider_error", "message": "The image provider returned an error.", "retryable": True}
    assert len(await ledger(api, j["id"])) == 1   # the faulted attempt cost nothing
    cands = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    assert sorted(c["status"] for c in cands) == ["failed", "ready"]
    r = await api.post(f"{API}/jobs/{j['id']}/tasks/{failed['id']}/retry", status=200)
    assert r.json()["status"] == "running"
    assert (await character(api, "chr_mockSarah"))["activeJobId"] == j["id"]
    await api.drive(25000)
    after = await job(api, j["id"])
    assert after["status"] == "succeeded"
    assert next(t for t in after["tasks"] if t["id"] == failed["id"])["attempt"] == 2
    assert len(await ledger(api, j["id"])) == 2


async def test_all_fail_then_out_of_attempts(api: Api) -> None:
    await setup(api, scenario="image_fail_all")
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    await api.drive(25000)
    done = await job(api, j["id"])
    assert done["status"] == "failed" and done["error"]["code"] == "provider_error"
    task = done["tasks"][0]
    for _ in range(2):
        await api.post(f"{API}/jobs/{j['id']}/tasks/{task['id']}/retry", status=200)
        await api.drive(25000)
    final = await job(api, j["id"])
    assert final["tasks"][0]["attempt"] == 3 and final["tasks"][0]["status"] == "failed"
    r = await api.post(f"{API}/jobs/{j['id']}/tasks/{task['id']}/retry")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert await ledger(api, j["id"]) == []


async def test_retry_needs_a_failed_task_and_a_key(api: Api) -> None:
    await setup(api, scenario="image_fail_all")
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    r = await api.post(f"{API}/jobs/{j['id']}/tasks/{j['tasks'][0]['id']}/retry")
    assert r.status_code == 409  # not failed (yet)
    assert (await api.post(f"{API}/jobs/{j['id']}/tasks/task_nope/retry")).status_code == 404
    assert (await api.post(f"{API}/jobs/job_nope/cancel")).status_code == 404
    await api.drive(25000)
    await api.client.put(f"{API}/settings/key", json={"key": None})
    r = await api.post(f"{API}/jobs/{j['id']}/tasks/{j['tasks'][0]['id']}/retry")
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"


async def test_retry_under_a_reached_cap_is_refused(api: Api) -> None:
    await setup(api, scenario="image_fail_all")
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    await api.drive(25000)
    spent = (await rows(api, "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM usage_records WHERE local_day = '2026-10-03'"))[0]["s"]
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": round(spent + 0.001, 6)}})).status_code == 200
    rec = Recorder(api.rt)
    r = await api.post(f"{API}/jobs/{j['id']}/tasks/{j['tasks'][0]['id']}/retry")
    assert r.status_code == 402 and r.json()["error"]["code"] == "daily_budget_exceeded"
    reached = [e for e in rec.events if e["type"] == "budget.reached"]
    assert reached and reached[0].get("jobId") == j["id"]
    assert (await job(api, j["id"]))["tasks"][0]["status"] == "failed"


async def test_song_fails_scenario(api: Api) -> None:
    await setup(api, scenario="song_fails")
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
    await api.drive(41000)
    done = await job(api, j["id"])
    assert done["status"] == "failed" and done["tasks"][0]["error"]["message"] == "The music provider returned an error."
    await api.post(f"{API}/jobs/{j['id']}/tasks/{done['tasks'][0]['id']}/retry", status=200)
    await api.drive(41000)
    assert (await job(api, j["id"]))["status"] == "succeeded"


async def test_unknown_scenario_still_rejected(api: Api) -> None:
    r = await api.post(f"{API}/_test/scenario", {"id": "network_down"})
    assert r.status_code == 422 and r.json()["error"]["details"]["clientSide"] is True
