"""The demo world is a real run (D-110, U-41): a user continues it, presses Reset demo, continues again, any number of
times, and Delete all data gives the fresh demo back. At every step the shipped documents search by vector, the shipped
memories have theirs, the user's own rows survive with their vectors, and no trace reads "(forgotten)"."""

from __future__ import annotations

import base64
import json
from typing import Any

from sqlalchemy import text

from horizon.db import spaces
from tests.conftest import SEED_DIR, Api
from tests.sessions.kit import API, command, messages

ROWS = SEED_DIR / "rows"


def shipped() -> tuple[dict[str, int], int]:
    """Indexed shipped sources → their piece count, and the shipped memory count (both have a vector each)."""
    pieces: dict[str, int] = {}
    for p in sorted((ROWS / "knowledge").glob("*.json")):
        d = json.loads(p.read_text("utf-8"))["data"]
        if d["source"]["status"] == "indexed":
            pieces[p.stem] = len(d["chunks"])
    memories = len(json.loads((ROWS / "memory.json").read_text("utf-8"))["data"])
    return pieces, memories


async def state(api: Api) -> dict[str, Any]:
    async with api.rt.db.read() as conn:
        space = await spaces.active(conn)
        mem, kno = spaces.vec_tables(space.id)
        q = lambda s, **p: conn.execute(text(s), p)  # noqa: E731
        return {
            "space": space.id,
            "status": dict((await q("SELECT id, status FROM knowledge_sources WHERE is_seed = 1")).all()),
            "kno_vec": dict((await q(f"SELECT c.source_id, count(*) FROM {kno} v JOIN knowledge_chunks c ON c.rid = v.rid "
                                     "GROUP BY c.source_id")).all()),
            "seed_mem_vec": (await q(f"SELECT count(*) FROM {mem} v JOIN memory_items m ON m.rid = v.rid "
                                     "WHERE m.is_seed = 1")).scalar_one(),
            "user_mem_vec": (await q(f"SELECT count(*) FROM {mem} v JOIN memory_items m ON m.rid = v.rid "
                                     "WHERE m.id = 'mem_userCycle'")).scalar_one(),
            "orphans": (await q(f"SELECT count(*) FROM {kno} WHERE rid NOT IN (SELECT rid FROM knowledge_chunks)")
                        ).scalar_one() + (await q(f"SELECT count(*) FROM {mem} WHERE rid NOT IN "
                                                  "(SELECT rid FROM memory_items)")).scalar_one(),
            "forgotten": (await q("SELECT count(*) FROM turn_traces WHERE trace LIKE '%(forgotten)%'")).scalar_one(),
            "originals": sorted(p.parent.name for p in (api.data_dir / "knowledge").rglob("original.*")),
        }


def assert_fresh_demo(st: dict[str, Any]) -> None:
    pieces, memories = shipped()
    assert st["space"] == json.loads((ROWS / "space.json").read_text("utf-8"))["data"]["id"]
    assert {k: v for k, v in st["status"].items() if v == "indexed"} == {k: "indexed" for k in pieces}
    assert st["status"]["kno_seedMei1"] == "failed"   # the real password-protected PDF (U-44)
    assert st["kno_vec"] == pieces
    assert st["seed_mem_vec"] == memories
    assert st["orphans"] == 0 and st["forgotten"] == 0
    assert set(pieces) <= set(st["originals"])


async def earn_memory(api: Api, session_id: str) -> None:
    """What a memory run leaves in the user's continued session: a memory row and its vector."""
    async with api.rt.db.write() as tx:
        space = await spaces.active(tx.conn)
        await tx.conn.execute(text(
            "INSERT INTO memory_items(id, character_id, world_id, kind, text, importance, source_session_id, created_at, "
            "recall_count, is_seed) VALUES ('mem_userCycle', 'chr_seedAmara', 'wld_seedMeridian', 'about_user', "
            "'Kai''s headache came back after the coffee taper', 0.6, :s, :n, 0, 0)"), {"s": session_id, "n": api.rt.now_iso()})
        rid = (await tx.conn.execute(text("SELECT rid FROM memory_items WHERE id = 'mem_userCycle'"))).scalar_one()
        vec = base64.b64decode(json.loads((ROWS / "memory.json").read_text("utf-8"))["data"][0]["vector"])
        await tx.conn.execute(text(f"INSERT INTO {spaces.vec_tables(space.id)[0]}(rid, character_id, embedding) "
                                   "VALUES (:r, 'chr_seedAmara', :e)"), {"r": rid, "e": vec})


async def say(api: Api, sid: str, line: str) -> int:
    before = len(await messages(api, sid))
    await command(api, sid, "send", {"text": line})
    await api.drive(30000)
    after = await messages(api, sid)
    assert len(after) > before and after[-1]["author"]["type"] == "character", after[-1]
    return len(after)


async def test_continue_reset_continue_then_delete_all(api: Api) -> None:
    await api.set_key()
    assert_fresh_demo(await state(api))

    # continue the shipped headache chat: the fork carries the conversation and what the AI stored for it
    r = await api.post(f"{API}/sessions/ses_seedAmaraHeadache/fork", {})
    assert r.status_code == 201, r.text
    fork = r.json()["session"]["id"]
    assert r.json()["session"]["continuedFrom"] == "ses_seedAmaraHeadache"
    async with api.rt.db.read() as conn:
        meta = (await conn.execute(text(
            "SELECT count(*) FROM message_ai_meta a JOIN messages m ON m.id = a.message_id WHERE m.session_id = :s"),
            {"s": fork})).scalar_one()
    assert meta > 0
    n = await say(api, fork, "The headache is back today.")
    await earn_memory(api, fork)
    assert (await state(api))["user_mem_vec"] == 1

    for _ in range(2):   # Reset demo, then continue again: twice, as a user might
        r = await api.client.post("/api/v1/admin/reset-demo", json={"confirm": True})
        assert r.status_code == 204
        st = await state(api)
        assert_fresh_demo(st)
        assert st["user_mem_vec"] == 1   # the user's own memory and its vector survive
        assert len(await messages(api, fork)) == n
        n = await say(api, fork, "Still there, a little better.")
        again = await api.post(f"{API}/sessions/ses_seedAmaraHeadache/fork", {})
        assert again.status_code == 201
        await say(api, again.json()["session"]["id"], "Hi again, Amara.")
        assert any(m["id"] == "mem_userCycle" for m in await api.json(f"{API}/characters/chr_seedAmara/memory"))

    r = await api.client.post("/api/v1/admin/factory-reset", json={"confirm": "DELETE EVERYTHING"})
    assert r.status_code == 204
    st = await state(api)
    assert_fresh_demo(st)
    assert st["user_mem_vec"] == 0
    assert (await api.get(f"{API}/sessions/{fork}")).status_code == 404


async def test_on_another_space_the_shipped_vectors_stay_out(api: Api) -> None:
    data = await api.rt.load_seed()
    assert data.rows is not None
    data.rows.space = "another-embedder@512"   # as if the install had switched spaces (`horizon space build`)
    r = await api.client.post("/api/v1/admin/reset-demo", json={"confirm": True})
    assert r.status_code == 204
    st = await state(api)
    pieces, _ = shipped()
    assert {k: st["status"][k] for k in pieces} == {k: "keyword_only" for k in pieces}
    assert st["kno_vec"] == {} and st["seed_mem_vec"] == 0
    body = await api.json(f"{API}/knowledge/kno_seedAmara2")
    assert body["source"]["status"] == "keyword_only" and len(body["chunks"]) == pieces["kno_seedAmara2"]


async def test_delete_all_stays_deleted_after_a_restart(make_api: Any, tmp_path: Any) -> None:
    """Pass 2 J6-02 (the user's choice): the demo is imported once, into a fresh install. Deleting every world, as the
    Delete all data dialog does, then restarting leaves it empty; Restore demo data brings it back."""
    data = tmp_path / "wiped"
    a: Api = await make_api(data_dir=data)
    for w in await a.json(f"{API}/worlds"):
        assert (await a.client.delete(f"{API}/worlds/{w['id']}")).status_code == 204
    await a.rt.stop()
    b: Api = await make_api(data_dir=data)
    assert await b.json(f"{API}/worlds") == []
    assert (await b.client.post("/api/v1/admin/reset-demo", json={"confirm": True})).status_code == 204
    assert {w["id"] for w in await b.json(f"{API}/worlds")} == {"wld_seedMeridian", "wld_seedSunnyHollow"}
