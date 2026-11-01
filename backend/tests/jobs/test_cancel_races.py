"""Pass 2 (J5-01, J5-02): a Cancel racing the runner's start of its tasks, and a Retry racing the cancelled runner."""

from __future__ import annotations

import asyncio
from typing import Any

from tests.conftest import Api
from tests.jobs.kit import API, cancel_overlay_jobs, character, job, ledger, start, until
from tests.jobs.test_cancel_retry import lock


class _Swept(dict[str, Any]):
    """`run.attempts` that reports when the cancel sweeps it (`list(run.attempts.values())`)."""

    def __init__(self, ev: asyncio.Event) -> None:
        super().__init__()
        self.ev = ev

    def values(self) -> Any:
        self.ev.set()
        return super().values()


async def test_a_cancel_inside_the_start_of_tasks_sends_and_bills_nothing(api: Api) -> None:
    """J5-01: the cancel's sweep ran while the runner's start transaction was open, before the attempts it starts were
    known to it; they were then sent and billed, and shown as skipped. "Sent" is now decided in the writer."""
    await api.set_key()
    await cancel_overlay_jobs(api)
    await lock(api, "chr_mockSarah")
    await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"image": "naive"}})
    fake = api.rt.fake
    assert fake is not None
    first = fake.counts["images"]
    sched = api.rt.jobs
    rows_of = sched._task_rows
    fired: list[asyncio.Future[Any]] = []
    armed = [True]

    async def task_rows(conn: Any, job_id: str) -> Any:
        out = await rows_of(conn, job_id)
        run = sched.runs.get(job_id)
        if armed[0] and run is not None and run.character_id and not run.attempts \
                and any(x["status"] == "queued" for x in out):
            armed[0] = False
            swept = asyncio.Event()
            run.attempts = _Swept(swept)
            fired.append(asyncio.ensure_future(sched.cancel(job_id)))   # the user's Cancel arrives now
            await asyncio.wait_for(swept.wait(), 5)                       # and sweeps while this transaction is open
        return out

    sched._task_rows = task_rows
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "emotion_set"})
    await until(lambda: bool(fired))
    assert (await fired[0])["status"] == "cancelled"
    for _ in range(20):
        await api.drive(2000)
        await asyncio.sleep(0.05)
    await api.rt.gateway.drain_background()
    done = await job(api, j["id"])
    assert done["status"] == "cancelled" and all(x["status"] == "skipped" for x in done["tasks"])
    assert fake.counts["images"] == first and await ledger(api, j["id"]) == []


async def test_a_retry_right_after_stop_remaining_runs(api: Api) -> None:
    """J5-02: a Retry inside the cancelled runner's last tick set the job running again with no runner, so it stayed
    running and locked the character. It now gets a runner of its own and ends."""
    await api.set_key()
    await cancel_overlay_jobs(api)
    await lock(api, "chr_mockSarah")
    assert (await api.post(f"{API}/_test/scenario", {"id": "image_fail_partial"})).status_code == 204
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "emotion_set"})
    failed = None
    for _ in range(200):
        await api.drive(100)
        cur = await job(api, j["id"])
        failed = next((x for x in cur["tasks"] if x["status"] == "failed"), None)
        if failed is not None:
            break
    assert failed is not None and cur["status"] == "running", cur
    assert (await api.post(f"{API}/jobs/{j['id']}/cancel", status=200)).json()["status"] == "cancelled"
    await api.post(f"{API}/jobs/{j['id']}/tasks/{failed['id']}/retry", status=200)
    await api.drive(60000)
    cur = await job(api, j["id"])
    assert cur["status"] not in ("queued", "running"), cur
    assert next(x for x in cur["tasks"] if x["id"] == failed["id"])["status"] in ("succeeded", "failed")
    assert (await character(api, "chr_mockSarah")).get("activeJobId") is None
