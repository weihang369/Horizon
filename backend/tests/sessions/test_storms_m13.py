"""Cancel storms on the paths M13 adds (memory design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed while it writes (`storm_during_write`) or cut while it waits on a held call. Afterwards
the writer is free, the clock settles and the log reduces, and the run wrote either everything or nothing.

Task 0.2 listed each path as a strict xfail naming the phase that builds it; each phase replaces its placeholders with
the real storm, so a path can't be forgotten and a placeholder can't pass by accident.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from horizon.ai.ports import Insert, MemoryDraft
from horizon.ai.profile import ProfileSpec
from horizon.services.memory.store import LostRace
from horizon.services.memory.stretch import WriterResult
from tests.conftest import Api
from tests.helpers.storm import after_storm, assert_writer_free, storm_during_write
from tests.sessions.kit import API, command, create

AMARA, MERIDIAN = "chr_seedAmara", "wld_seedMeridian"

PATHS = [
    ("Forget during a run", 4),
    ("a regenerate during a run, and the undo before it streams", 4),
    ("the window-drop indexing mid-write", 6),
    ("recall's search and Jev call 2 on Stop", 7),
    ("the memory block's refresh through the actor inbox", 5),
]


@pytest.mark.parametrize(("path", "phase"), PATHS, ids=[p for p, _ in PATHS])
@pytest.mark.xfail(strict=True, reason="placeholder: the phase that builds this cancel path replaces it")
async def test_storm_placeholder(api: Api, path: str, phase: int) -> None:
    pytest.fail(f"not built yet (phase {phase}): {path}")


class HeldWriter:
    """Holds every stretch until released; writes one memory for Amara when it lets go."""

    def __init__(self, hold: bool = True) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()
        self.calls = 0

    async def on_stretch(self, stretch: Any, ctx: Any) -> WriterResult:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return WriterResult(ops={AMARA: [Insert(MemoryDraft("fact", "Kai sleeps badly before exams.", 0.6))]})


def writing(api: Api, writer: Any) -> None:
    api.rt.set_profile(ProfileSpec(profile="naive", test_mode=True))
    api.rt.ai.override("memory_writer", writer)


async def a_chat(api: Api) -> str:
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    for i in range(2):
        await command(api, sid, "send", {"text": f"I can't sleep before exams, part {i}."})
        await api.drive(15_000)
    return str(sid)


async def run_memories(api: Api) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text(
            "SELECT count(*) FROM memory_items WHERE text = 'Kai sleeps badly before exams.'"))).scalar_one())


async def checkpoint(api: Api, sid: str) -> tuple[int, int]:
    async with api.rt.db.read() as conn:
        row = (await conn.execute(text("SELECT memory_seq, (SELECT MAX(seq) FROM messages WHERE session_id = :s) "
                                       "FROM sessions WHERE id = :s"), {"s": sid})).first()
    return (int(row[0]), int(row[1] or 0)) if row is not None else (-1, -1)


async def held_run(api: Api) -> tuple[str, HeldWriter]:
    writer = HeldWriter()
    writing(api, writer)
    sid = await a_chat(api)
    api.rt.memory_runs.request(sid)
    await asyncio.wait_for(writer.entered.wait(), 5)
    return sid, writer


async def test_a_run_cut_by_a_session_delete_during_its_call(api: Api) -> None:
    _sid, writer = await held_run(api)
    assert (await api.client.delete(f"{API}/sessions/{_sid}")).status_code == 204
    await api.rt.memory_runs.drain()
    writer.release.set()
    assert await run_memories(api) == 0
    await assert_writer_free(api.rt.db)


async def test_a_run_cut_by_a_character_delete_during_its_call(api: Api) -> None:
    _sid, writer = await held_run(api)
    r = await api.client.delete(f"{API}/characters/{AMARA}")   # Amara isn't generating: she can be deleted
    assert r.status_code in (200, 204), r.text
    await api.rt.memory_runs.drain()
    writer.release.set()
    assert await run_memories(api) == 0
    await assert_writer_free(api.rt.db)


async def test_a_run_cut_by_a_world_delete_during_its_call(api: Api) -> None:
    _sid, writer = await held_run(api)
    assert (await api.client.delete(f"{API}/worlds/{MERIDIAN}")).status_code == 204
    await api.rt.memory_runs.drain()
    writer.release.set()
    assert await run_memories(api) == 0
    await assert_writer_free(api.rt.db)


async def test_reset_demo_cancels_a_held_run(api: Api) -> None:
    sid, writer = await held_run(api)
    assert (await api.client.post("/api/v1/admin/reset-demo", json={"confirm": True})).status_code in (200, 204)
    await api.rt.memory_runs.drain()
    writer.release.set()
    assert await run_memories(api) == 0 and (await checkpoint(api, sid))[0] == 0
    await after_storm(api, sid)


async def test_apply_run_stormed_writes_everything_or_nothing(api: Api) -> None:
    writing(api, HeldWriter(hold=False))
    sid = await a_chat(api)
    _, top = await checkpoint(api, sid)
    store = api.rt.memory

    async def reset() -> None:   # each storm starts from the same checkpoint (a cut reset leaves the last state)
        async with api.rt.db.write() as tx:
            await tx.conn.execute(text("UPDATE sessions SET memory_seq = 0 WHERE id = :s"), {"s": sid})
            await tx.conn.execute(text("DELETE FROM memory_items WHERE text = 'Kai sleeps badly before exams.'"))

    async def commit() -> None:
        await reset()
        async with store.run_locks([AMARA]):
            with contextlib.suppress(LostRace):
                await store.apply_run(MERIDIAN, {AMARA: [Insert(MemoryDraft("fact", "Kai sleeps badly before exams.",
                                                                             0.6))]},
                                      session_id=sid, from_seq=0, upto_seq=top)

    cut = await storm_during_write(api, sid, commit, storms=20, seed=13)
    seq, _ = await checkpoint(api, sid)
    assert (seq, await run_memories(api)) in ((0, 0), (top, 1))   # all or nothing
    assert cut > 0


async def test_shutdown_leaves_the_checkpoint_and_the_next_start_reads_the_lines(make_api: Any,
                                                                                  tmp_path: Path) -> None:
    data = tmp_path / "restart"
    first: Api = await make_api(data_dir=data)
    sid, writer = await held_run(first)
    db = first.rt.cfg.db_path
    await first.rt.stop()                                       # never waits on DeepSeek
    writer.release.set()
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT memory_seq FROM sessions WHERE id = ?", (sid,)).fetchone() == (0,)
        mems = conn.execute("SELECT count(*) FROM memory_items WHERE text = 'Kai sleeps badly before exams.'")
        assert mems.fetchone() == (0,)
    finally:
        conn.close()
    second: Api = await make_api(data_dir=data)                 # trigger 6: the start-up sweep reads the lines again
    await second.rt.memory_runs.drain()
    seq, top = await checkpoint(second, sid)
    assert seq == top and any(e["sessionId"] == sid and e.get("upto") == top for e in second.rt.memory_runs.log)
