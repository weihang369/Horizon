"""Cancel storms on the paths M15 adds (images-music design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed while it writes (`storm_during_write`) or cut while it waits on a held call
(`storm_during_call`). Afterwards the writer is free, the clock settles and the log reduces.

Task 0.2 lists each path of D2's list as a strict xfail naming the phase that builds it. Each phase replaces its
placeholder with the real storm, so no path is forgotten.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import Api
from tests.helpers.storm import assert_writer_free
from tests.sessions.kit import API


def _todo(task: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=f"built in task {task}")


# ── phase 1 (tasks 1.2, 1.4): the identity edit and the song prompt ──
@pytest.mark.parametrize("cut", ["cancel", "character"])
async def test_a_hinted_regenerate_cut_between_compile_and_the_call_sends_nothing(api: Api, cut: str) -> None:
    """Both image slots are held, so the task compiles its identity edit and then waits for a slot: the cut lands
    between the compile and the provider call."""
    from tests.jobs.kit import rows, start
    from tests.jobs.test_identity_m15 import HINT, SARAH, image_prompts, ready

    fake = await ready(api)
    sent = len(image_prompts(fake))
    slots = api.rt.image_slots
    for _ in range(slots.size):
        await slots.acquire()
    j = await start(api, {"characterId": SARAH, "kind": "emotion_regenerate", "emotions": ["happy"], "prompt": HINT})
    for _ in range(200):
        await api.drive(5)
        if slots._waiters:
            break
    assert slots._waiters, "the task should be waiting for an image slot, its edit compiled"
    if cut == "cancel":
        assert (await api.client.post(f"{API}/jobs/{j['id']}/cancel")).status_code in (200, 202, 204)
    else:
        assert (await api.client.delete(f"{API}/characters/{SARAH}")).status_code in (200, 204)
    for _ in range(slots.size):
        slots.release()
    await api.drive(3000)
    await assert_writer_free(api.rt.db)
    assert len(image_prompts(fake)) == sent                          # no image request after the cut
    assert await rows(api, "SELECT id FROM image_assets WHERE job_id = :j", j=j["id"]) == []
    assert api.rt.book.total() == 0


@pytest.mark.parametrize("cut", ["cancel", "character"])
async def test_a_song_task_cut_after_its_prompt_is_built_sends_no_music_call(api: Api, cut: str) -> None:
    """Under `agent` the task builds the title-free prompt, has Jev check it, then waits for the music slot (held
    here): the cut lands after the prompt is built and before `before_send`."""
    from tests.jobs.kit import cancel_overlay_jobs, job, start

    await api.set_key()
    await cancel_overlay_jobs(api)
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    fake = api.rt.fake
    assert fake is not None
    music = fake.counts["music"]
    slots = api.rt.music_slots
    await slots.acquire()
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
    for _ in range(400):
        await api.drive(5)
        if slots._waiters:
            break
    assert slots._waiters, "the task should be waiting for the music slot, its prompt built and checked"
    if cut == "cancel":
        assert (await api.client.post(f"{API}/jobs/{j['id']}/cancel")).status_code in (200, 202, 204)
    else:
        assert (await api.client.delete(f"{API}/characters/chr_seedHana")).status_code in (200, 204)
    slots.release()
    await api.drive(3000)
    await assert_writer_free(api.rt.db)
    assert fake.counts["music"] == music                             # no music call after the cut
    assert api.rt.book.total() == 0
    if cut == "cancel":
        assert (await job(api, j["id"]))["status"] == "cancelled"


# ── phase 6 (tasks 6.1, 6.6): a stopped eval run keeps what it saved ──
async def test_a_conversations_run_stopped_between_and_inside_a_turn_is_incomplete(tmp_path: Path) -> None:
    """6.1: the cap between units and inside one. Every saved line stays whole JSON, and the report gives no figure for
    the conversation the run was inside."""
    import json

    from horizon.evals.runner import Options
    from tests.integration.test_eval_runner import runner

    for cap, where in ((1e-9, "inside"), (0.0002, "between")):
        tmp = tmp_path / where
        r, _ = runner(tmp)
        assert await r.run(Options("conversations", limit=2, yes=True, max_usd=cap)) == 1
        (run,) = [p for p in (tmp / "evals").iterdir() if p.is_dir()]
        report = (run / "naive" / "report.md").read_text(encoding="utf-8")
        assert "incomplete" in report and "stopped" in report
        for name in ("replies.jsonl", "judge_states.jsonl"):
            f = run / "naive" / name
            for line in (f.read_text(encoding="utf-8").splitlines() if f.is_file() else []):
                json.loads(line)
        f = run / "naive" / "replies.jsonl"
        saved = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.is_file() else []
        assert (where == "inside") == (not saved)
        finished = 2 if len(saved) >= 2 else 0   # the first conversation plans 2 units: half of it gives no figure
        assert f"## Conversations: {finished} of 8 unit(s) in finished conversations" in report


async def test_a_latency_run_stopped_between_and_inside_a_turn_is_incomplete(tmp_path: Path) -> None:
    """6.6: the blended run's cap inside the first turn and between parts; every saved turn line stays whole."""
    import json

    from horizon.evals.runner import Options
    from tests.integration.test_eval_runner import runner

    for cap, where in ((1e-9, "inside"), (0.0005, "between")):
        tmp = tmp_path / where
        r, _ = runner(tmp)
        code = await r.run(Options("latency", profile="agent", part="blended", arm="rate=0.3", limit=1, yes=True,
                                   max_usd=cap))
        (run,) = [p for p in (tmp / "evals").iterdir() if p.is_dir()]
        report = (run / "agent" / "report.md").read_text(encoding="utf-8")
        f = run / "agent" / "turns.jsonl"
        for line in (f.read_text(encoding="utf-8").splitlines() if f.is_file() else []):
            json.loads(line)
        if where == "inside":
            assert code == 1 and "incomplete" in report
        else:
            assert "## Blended latency" in report and (code == 0) == ("incomplete" not in report.splitlines()[0])


# ── phase 7 (task 7.2): the key read once per reply ──
@_todo("7.2")
async def test_the_key_cleared_while_call_1_is_held_errors_the_reply(api: Api) -> None:
    raise NotImplementedError


@_todo("7.2")
async def test_the_key_cleared_while_the_output_check_is_held_mixes_no_profile(api: Api) -> None:
    raise NotImplementedError


@_todo("7.2")
async def test_the_key_cleared_during_a_pause_run_holds_the_line(api: Api) -> None:
    raise NotImplementedError
