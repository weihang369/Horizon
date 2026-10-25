"""After Forget, the text appears nowhere in the database files (knowledge-memory-storage task 6.4; doc 06 M5
acceptance; long-term-memory "Forgotten text leaves the database files"; design D16).

A memory whose text holds a word used nowhere else is written with a key (so it has vectors), recalled in a live turn,
copied by a fork, then forgotten. With no read in progress, a byte search of `horizon.db`, its WAL and `graph.db` (if
present) finds neither the text nor the word. The same runs with FTS5 secure-delete switched off, which exercises the
`optimize` fallback for older SQLite libraries.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.conftest import Api
from tests.knowledge.kit import API
from tests.knowledge.test_forget import recall_in_session, remember

WORD = "zorbleflaxion"
SECRET = f"Amara keeps a spare key under the {WORD} pot."


def file_bytes(data_dir: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for name in ("horizon.db", "horizon.db-wal", "graph.db"):
        p = data_dir / name
        if p.is_file():
            out[name] = p.read_bytes()
    return out


async def run_forget(api: Api, capture: bool = False) -> dict[str, bytes]:
    if capture:   # ai-foundation D28: with capture on, the text is in neither the table nor the queue after Forget
        from tests.integration.test_capture import enable_capture

        enable_capture(api.rt)
    await api.set_key()
    mid = await remember(api, SECRET)
    sid, _ = await recall_in_session(api, mid, SECRET)
    fork = await api.post(f"{API}/sessions/{sid}/fork", {})
    assert fork.status_code == 201
    await api.drive(1)
    before = file_bytes(api.data_dir)
    assert any(WORD.encode() in b for b in before.values())   # the text really was written to the files
    if capture:
        assert any(SECRET in json.dumps(r) for r in api.rt.capture.queue) or await _captured(api)
    assert (await api.client.delete(f"{API}/memory/{mid}")).status_code == 204
    await api.drive(1)
    if capture:
        assert not any(WORD in json.dumps(r) for r in api.rt.capture.queue)
        await api.rt.capture.flush()
    await api.rt.db.checkpoint_truncate()                      # no read is in progress now
    return file_bytes(api.data_dir)


async def _captured(api: Api) -> bool:
    async with api.rt.db.read() as conn:
        return bool((await conn.execute(text("SELECT COUNT(*) FROM ai_calls WHERE request LIKE :w"),
                                        {"w": f"%{WORD}%"})).scalar_one())


@pytest.mark.parametrize(("fts_secure_delete", "capture"), [(True, False), (False, False), (True, True)],
                         ids=["fts-secure-delete", "optimize-fallback", "capture-on"])
async def test_forgotten_text_leaves_the_files(api: Api, fts_secure_delete: bool, capture: bool) -> None:
    if not fts_secure_delete:
        async with api.rt.db.write() as tx:
            await tx.conn.execute(text("INSERT INTO memory_fts(memory_fts, rank) VALUES ('secure-delete', 0)"))
        api.rt.fts_secure_delete = False
    after = await run_forget(api, capture)
    assert "horizon.db" in after
    for name, data in after.items():
        assert SECRET.encode() not in data, name
        assert WORD.encode() not in data, name
    wal = api.data_dir / "horizon.db-wal"
    assert not wal.exists() or wal.stat().st_size == 0
