"""Recall's indexing at window drops (memory design D29; session-recall "A drop is indexed once", "Indexed lines follow
their messages"; session-lifecycle "Fork copies without paying"; data-storage "Message vectors live beside the
others")."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import GuardrailResult
from horizon.db import spaces
from horizon.services.memory.index import index_drop, rows_of
from tests.conftest import Api
from tests.helpers.storm import storm_during_write
from tests.sessions.kit import API, chars, command, messages
from tests.sessions.test_summary import Held, chat, rolling_rows, send, small_windows

AMARA = "chr_seedAmara"


async def index_rows(api: Api, sid: str) -> list[dict[str, Any]]:
    async with api.rt.db.read() as conn:
        rows = (await conn.execute(text("SELECT rid, message_id, seq, author, text FROM message_index "
                                        "WHERE session_id = :s ORDER BY seq"), {"s": sid})).mappings().all()
    return [dict(r) for r in rows]


async def vectors(api: Api, rids: list[int]) -> dict[int, bytes]:
    if not rids:
        return {}
    async with api.rt.db.read() as conn:
        space = await spaces.active(conn)
        table = spaces.message_vec_table(space.id)
        rows = (await conn.execute(text(f"SELECT rid, embedding FROM {table} WHERE rid IN "
                                        f"({','.join(str(r) for r in rids)})"))).all()
    return {int(r[0]): bytes(r[1]) for r in rows}


def embed_inputs(api: Api) -> list[list[str]]:
    import json

    assert api.rt.fake is not None
    return [list(json.loads(r.content).get("input") or []) for r in api.rt.fake.requests
            if r.url.path.endswith("/embeddings")]


async def dropped_chat(api: Api, n: int = 4, profile: str = "naive") -> str:
    sid = await chat(api, profile)
    small_windows(api)
    await send(api, sid, n)
    await api.drive(2000)
    assert await rolling_rows(api, sid)
    return sid


# ── 6.1 ──
async def test_a_drop_is_indexed_once_as_name_and_text(api: Api) -> None:
    sid = await dropped_chat(api)
    rows = await index_rows(api, sid)
    assert rows and {r["author"] for r in rows} <= {"user", "character"}
    upto = (await rolling_rows(api, sid))[-1]["upto_seq"]
    assert all(r["seq"] <= upto for r in rows)
    you = rows[[r["author"] for r in rows].index("user")]
    assert you["text"].startswith(("Kai: ", "You: ")) or ": Question number" in you["text"]
    await send(api, sid, 3, start=10)
    await api.drive(2000)
    again = await index_rows(api, sid)
    assert len({r["message_id"] for r in again}) == len(again) >= len(rows)


def test_only_heard_complete_lines_are_indexed() -> None:
    def m(mid: str, seq: int, author: str, kind: str = "chat", status: str = "complete", content: str = "hi") -> Any:
        return {"seq": seq, "author": {"type": author, **({"characterId": "c1"} if author == "character" else {})},
                "kind": kind, "status": status, "content": content, "activeVariantId": None}

    msgs = {"a": m("a", 1, "user"), "b": m("b", 2, "character"), "n": m("n", 3, "system", kind="note"),
            "d": m("d", 4, "user", kind="direction"), "x": m("x", 5, "character", status="error"),
            "i": m("i", 6, "character", status="interrupted"), "s": m("s", 7, "user", kind="steer")}
    got = rows_of(msgs, list(msgs), {"c1": "Amara"}, "Kai", "watch")
    assert [(r[0], r[3]) for r in got] == [("a", "Kai: hi"), ("b", "Amara: hi"), ("s", "Moderator (the user): hi")]


# ── 6.2 ──
async def test_one_embedding_call_per_drop_never_stored(api: Api) -> None:
    sid = await dropped_chat(api)
    rows = await index_rows(api, sid)
    texts = {r["text"] for r in rows}
    carrying = [x for x in embed_inputs(api) if texts & set(x)]
    assert all(sum(x.count(tx) for x in carrying) == 1 for tx in texts)          # each line embedded once
    assert 1 <= len(carrying) <= len(await rolling_rows(api, sid))               # at most one call per drop
    assert len(await vectors(api, [r["rid"] for r in rows])) == len(rows)
    assert getattr(api.rt, "store", None) is None or not api.rt.store   # test mode: no response store at all


async def test_without_a_key_the_lines_are_keyword_only(api: Api) -> None:
    sid = await dropped_chat(api, profile="scripted")
    rows = await index_rows(api, sid)
    assert rows
    from horizon.services.memory.index import embed_lines

    status = api.rt.keys.status

    def unset() -> str:
        return "unset"

    api.rt.keys.status = unset  # type: ignore[method-assign]
    try:
        assert await embed_lines(api.rt, sid, "wld_seedMeridian", [(rows[0]["rid"], rows[0]["text"])]) == 0
    finally:
        api.rt.keys.status = status  # type: ignore[method-assign]


async def test_stop_does_not_cancel_the_indexing_and_a_delete_does(api: Api) -> None:
    sid = await chat(api, "naive")
    small_windows(api)
    held = Held()
    api.rt.ai.override("summariser", held)
    await send(api, sid, 2)
    assert held.calls == 1
    await command(api, sid, "stop")
    held.release.set()
    await api.drive(1000)
    assert await index_rows(api, sid)
    other = await chat(api, "naive")
    held2 = Held()
    api.rt.ai.override("summariser", held2)
    await send(api, other, 2)
    assert (await api.client.delete(f"{API}/sessions/{other}")).status_code == 204
    held2.release.set()
    await api.drive(1000)
    assert await index_rows(api, other) == []


# ── 6.3 ──
async def test_a_regenerate_rewrites_and_reembeds_an_indexed_line(api: Api) -> None:
    sid = await dropped_chat(api)
    rows = await index_rows(api, sid)
    reply = next(r for r in rows if r["author"] == "character")
    before = (await vectors(api, [reply["rid"]]))[reply["rid"]]
    assert api.rt.fake is not None
    api.rt.fake.set_canned("reply", [{"content": "A brand new answer about rotas."}])
    await command(api, sid, "regenerate", {"messageId": reply["message_id"]})
    await api.drive(15_000)
    after = next(r for r in await index_rows(api, sid) if r["rid"] == reply["rid"])
    assert after["text"].endswith(": A brand new answer about rotas.") and after["text"].split(": ")[0] == \
        reply["text"].split(": ")[0]
    assert (await vectors(api, [reply["rid"]]))[reply["rid"]] != before


async def test_a_blocked_scrub_deletes_the_line(api: Api) -> None:
    sid = await dropped_chat(api)
    rows = await index_rows(api, sid)
    reply = next(r for r in rows if r["author"] == "character")

    class Block:
        async def check(self, ctx: TurnContext, text_: str) -> GuardrailResult:
            return GuardrailResult("block", [{"name": "sfw", "verdict": "block", "p": 0.99}])

    api.rt.ai.override("guardrail", Block())
    await command(api, sid, "regenerate", {"messageId": reply["message_id"]})
    await api.drive(15_000)
    assert reply["rid"] not in {r["rid"] for r in await index_rows(api, sid)}
    assert await vectors(api, [reply["rid"]]) == {}


async def test_a_session_delete_removes_its_lines_and_vectors(api: Api) -> None:
    sid = await dropped_chat(api)
    rids = [r["rid"] for r in await index_rows(api, sid)]
    assert await vectors(api, rids)
    assert (await api.client.delete(f"{API}/sessions/{sid}")).status_code == 204
    assert await index_rows(api, sid) == [] and await vectors(api, rids) == {}


async def test_a_fork_copies_rows_and_vectors_without_paying(api: Api) -> None:
    sid = await dropped_chat(api)
    rows = await index_rows(api, sid)
    n = len(embed_inputs(api))
    fork = (await api.post(f"{API}/sessions/{sid}/fork", {}, status=201)).json()
    fid = fork["session"]["id"]
    await api.drive(2000)
    copied = await index_rows(api, fid)
    assert [r["text"] for r in copied[:len(rows)]] == [r["text"] for r in rows]
    vs = await vectors(api, [r["rid"] for r in copied[:len(rows)]])
    assert len(vs) == len(rows)
    new_embeds = [x for x in embed_inputs(api)[n:] if {r["text"] for r in rows} & set(x)]
    assert new_embeds == []
    async with api.rt.db.read() as conn:
        seq = (await conn.execute(text("SELECT memory_seq FROM sessions WHERE id = :s"), {"s": fid})).scalar_one()
    assert seq == max(m["seq"] for m in await messages(api, fid) if m["author"]["type"] in ("user", "character")) \
        or seq == max(m["seq"] for m in await messages(api, fid))


# ── 6.4 the indexing storm ──
async def test_the_indexing_storm_leaves_no_partial_rows(api: Api) -> None:
    sid = await chat(api, "naive")
    await send(api, sid, 3)
    msgs = chars(await messages(api, sid)) + [m for m in await messages(api, sid) if m["author"]["type"] == "user"]
    rows = [(m["id"], int(m["seq"]), m["author"]["type"], f"X: {m['content']}") for m in msgs]

    async def run() -> None:
        async with api.rt.db.write() as tx:
            await tx.conn.execute(text("DELETE FROM message_index WHERE session_id = :s"), {"s": sid})
        await index_drop(api.rt, sid, "wld_seedMeridian", rows)

    cut = await storm_during_write(api, sid, run, storms=20, seed=29)
    got = await index_rows(api, sid)
    assert len(got) in (0, len(rows))
    assert cut > 0
