"""Cancel storms on the paths M15 adds (images-music design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed while it writes (`storm_during_write`) or cut while it waits on a held call
(`storm_during_call`). Afterwards the writer is free, the clock settles and the log reduces.

Task 0.2 lists each path of D2's list as a strict xfail naming the phase that builds it. Each phase replaces its
placeholder with the real storm, so no path is forgotten.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


# ── phase 7 (task 7.2; design D4): the key read once per reply ──
def _simulated(row: dict) -> bool:
    """A scripted port's priced row (`simulated_call`): the scripted provider, no generation id."""
    from horizon.gateway.pipeline import SCRIPTED_PROVIDER

    return bool(row["provider"] == SCRIPTED_PROVIDER and row["generation_id"] is None)


async def _clear_key(api: Api) -> None:
    assert (await api.client.put(f"{API}/settings/key", json={"key": None})).status_code == 200


async def test_the_key_cleared_while_call_1_is_held_errors_the_reply(api: Api) -> None:
    """Jev call 1 parked, the key cleared, released: the reply ends on `missing_key` and no scripted text is stored
    (before D4 the reply engine resolved `scripted` after an `agent` plan)."""
    from tests.helpers.storm import park_next_decision
    from tests.sessions.kit import command, events, messages
    from tests.sessions.test_gates_m12 import AMARA, agent

    sid = await agent(api, "one_on_one", [AMARA])
    fake = api.rt.fake
    assert fake is not None
    held = park_next_decision(api.rt)
    before = len(await messages(api, sid))
    await command(api, sid, "send", {"text": "How was your shift?"})
    for _ in range(400):
        await api.drive(10)
        if fake.decision_parked.is_set():
            break
    assert fake.decision_parked.is_set()
    await _clear_key(api)
    held.set()
    await api.drive(20000)
    new = (await messages(api, sid))[before:]
    assert [m["author"]["type"] for m in new] == ["user"]           # no character line, scripted or other
    errors = [e for e in await events(api, sid) if e["type"] == "error"]
    assert errors and errors[-1]["payload"]["code"] == "missing_key"
    await assert_writer_free(api.rt.db)


async def test_the_key_cleared_while_the_output_check_is_held_mixes_no_profile(api: Api) -> None:
    """The output check parked, the key cleared, released: the reply keeps its `agent` rows only. The face check
    after it is `agent` too (its call fails on the missing key), never a scripted stand-in recording simulated spend."""
    from tests.sessions.kit import ledger
    from tests.sessions.test_storms_m14 import checking, reply_of

    sid, held = await checking(api)
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("output_rules", {"type": "noul", "noul": 0.02})
    sent = len(await ledger(api))
    asked: list[tuple[str, bool]] = []   # each port the rest of the reply resolves, with the key value it used
    for port in ("guardrail", "face_check", "reactions", "turn", "planner"):
        real = getattr(api.rt.ai, port)

        def spy(key_set: bool, port: str = port, real: Any = real) -> Any:
            asked.append((port, key_set))
            return real(key_set)

        setattr(api.rt.ai, port, spy)
    await _clear_key(api)
    held.set()
    await api.drive(20000)
    assert ("face_check", True) in asked and all(k for _, k in asked)     # the key read at the reply's start, not now
    reply = await reply_of(api, sid)
    assert reply["status"] == "complete"
    trace = reply["trace"]
    assert [c["purpose"] for c in trace["calls"]] == ["query_rewrite", "turn_plan", "reply", "guardrail"]
    assert {"name": "output", "verdict": "pass", "p": 0.02} in trace["guardrail"]["checks"]   # Jev's answer, not 'pass' with no p
    later = (await ledger(api))[sent:]
    assert later and not any(_simulated(r) for r in later)                # no scripted stand-in after the key went
    await assert_writer_free(api.rt.db)


async def test_a_key_set_mid_reply_leaves_that_reply_scripted_and_the_next_one_agent(
        api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """`agent` with no key resolves `scripted`; the key arrives while that reply streams. A send is refused without
    a key, so the command's key guard is waved through here to start a reply with none. The reply finishes scripted
    (no Jev output check joins it), and the next reply is `agent`."""
    from horizon.sessions import commands
    from tests.sessions.kit import command, ledger, messages
    from tests.sessions.test_gates_m12 import AMARA, agent

    sid = await agent(api, "one_on_one", [AMARA])
    sent = len(await ledger(api))
    status = api.rt.keys.status

    async def live(manager: object, status: str) -> None:
        return None

    monkeypatch.setattr(commands, "key_problem", lambda status: None)
    monkeypatch.setattr(commands, "check_generating", live)
    monkeypatch.setattr(api.rt.keys, "status", lambda: "missing")
    await command(api, sid, "send", {"text": "How was your shift?"})
    for _ in range(400):
        await api.drive(5)
        if any(m["author"]["type"] == "character" and m.get("status") == "streaming" for m in await messages(api, sid)):
            break
    monkeypatch.setattr(api.rt.keys, "status", status)                   # the key is back while the reply streams
    await api.drive(15000)
    rows = (await ledger(api))[sent:]
    assert rows and all(_simulated(r) for r in rows)                      # the whole reply is scripted: no real call
    assert [m for m in await messages(api, sid) if m["author"]["type"] == "character"][-1]["status"] == "complete"
    sent = len(await ledger(api))
    await command(api, sid, "send", {"text": "And the night before?"})
    await api.drive(15000)
    real = {r["purpose"] for r in (await ledger(api))[sent:] if not _simulated(r)}
    assert {"turn_plan", "reply", "guardrail"} <= real
    await assert_writer_free(api.rt.db)


async def test_the_key_cleared_during_a_pause_run_holds_the_line(api: Api) -> None:
    """A pause run reads the key at its own start (D4). The rewrite call parked, the key cleared, released: Jev's
    importance call fails on the missing key, so the piece writes nothing, keeps its checkpoint and counts a try."""
    from sqlalchemy import text

    from horizon.ai.profile import ProfileSpec
    from tests.helpers.storm import park_next_chat
    from tests.sessions.kit import command, create

    await api.set_key()
    api.rt.set_profile(ProfileSpec(profile="agent", test_mode=True))
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    for i in range(2):
        await command(api, sid, "send", {"text": f"I can't sleep before exams, part {i}."})
        await api.drive(15_000)
    assert (await api.post(f"{API}/_test/canned", {"purpose": "memory", "set": "memory-writes"})).status_code == 204
    fake = api.rt.fake
    assert fake is not None
    held = park_next_chat(api.rt, "memory")
    api.rt.memory_runs.request(sid)
    for _ in range(400):
        await api.drive(10)
        if fake.chat_parked.is_set():
            break
    assert fake.chat_parked.is_set()
    await _clear_key(api)
    held.set()
    await api.rt.memory_runs.drain()
    async with api.rt.db.read() as conn:
        row = (await conn.execute(text("SELECT memory_seq, memory_tries FROM sessions WHERE id = :s"), {"s": sid})).first()
        n = (await conn.execute(text("SELECT count(*) FROM memory_items WHERE source_session_id = :s"),
                                {"s": sid})).scalar_one()
    assert row is not None and tuple(row) == (0, 1) and n == 0
    assert api.rt.memory_runs.log[-1]["outcome"] == "failed"
    await assert_writer_free(api.rt.db)
