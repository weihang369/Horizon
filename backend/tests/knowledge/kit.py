"""Shared helpers for the knowledge tests (knowledge-memory-storage)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from tests.conftest import Api

API = "/api/v1"
HANA = "chr_seedHana"
SUNNY = "wld_seedSunnyHollow"


async def add_text(api: Api, title: str, body: str, character: str = HANA) -> dict[str, Any]:
    r = await api.client.post(f"{API}/characters/{character}/knowledge", json={"type": "text", "title": title, "text": body})
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def add_file(api: Api, name: str, data: bytes, mime: str = "", character: str = HANA) -> dict[str, Any]:
    files = {"file": (name, data, mime)} if mime else {"file": (name, data)}
    r = await api.client.post(f"{API}/characters/{character}/knowledge", files=files)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def settle(api: Api, ms: float = 1) -> None:
    """Let spawned ingestion finish (its tasks hold activity tokens, so an advance waits for them)."""
    await api.drive(ms)


async def source(api: Api, sid: str) -> dict[str, Any]:
    r = await api.client.get(f"{API}/knowledge/{sid}")
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


async def row(api: Api, sid: str) -> Any:
    async with api.rt.db.read() as conn:
        return (await conn.execute(text("SELECT * FROM knowledge_sources WHERE id = :i"), {"i": sid})).mappings().first()


async def embedding_rows(api: Api, character: str | None = None) -> list[Any]:
    sql = "SELECT * FROM usage_records WHERE is_seed = 0 AND category = 'embedding'"
    params: dict[str, Any] = {}
    if character:
        sql += " AND character_id = :c"
        params["c"] = character
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text(sql + " ORDER BY at, id"), params)).mappings())


async def vector_count(api: Api, sid: str, space_id: str | None = None) -> int:
    from horizon.db import spaces

    _, kno = spaces.vec_tables(space_id or api.rt.space_id or "")
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text(
            f"SELECT count(*) FROM {kno} WHERE rid IN (SELECT rid FROM knowledge_chunks WHERE source_id = :s)"),
            {"s": sid})).scalar_one())


def drain(sub: Any) -> list[dict[str, Any]]:
    out = []
    while not sub.queue.empty():
        out.append(sub.queue.get_nowait())
    return out


class RecordingEngine:
    """A test turn engine that keeps every `TurnContext` it is given and replies with a short simulated stream."""

    name = "recording"
    version = "t1"
    prompt_version = None

    def __init__(self, api: Api, reply: str = "Noted.") -> None:
        self.api = api
        self.reply = reply
        self.seen: list[Any] = []

    async def run(self, ctx: Any) -> Any:
        from horizon.ai.ports import Emotion, Token
        from horizon.gateway.pipeline import SimulatedReply

        self.seen.append(ctx)
        spec = SimulatedReply(chunks=[self.reply], first_token_ms=300, step_ms=50, tail_ms=20, total_ms=500,
                              model="deepseek/deepseek-v4.1-flash", tokens_in=500, tokens_cached=0, tokens_out=3,
                              cost_usd=0.0001)
        yield Emotion("happy")
        async for ch in self.api.rt.gateway.simulated_stream(ctx.call_ctx("reply"), spec, self.api.rt.clock.sleep):
            if ch.content:
                yield Token(ch.content)


async def owners(api: Api, ids: list[str], table: str) -> set[tuple[str, str]]:
    """(world_id, character_id) of each row id in `table` (knowledge_sources or memory_items)."""
    if not ids:
        return set()
    marks = ", ".join(f":i{n}" for n in range(len(ids)))
    async with api.rt.db.read() as conn:
        rows = (await conn.execute(text(f"SELECT world_id, character_id FROM {table} WHERE id IN ({marks})"),
                                   {f"i{n}": i for n, i in enumerate(ids)})).all()
    assert len(rows) == len(set(ids))
    return {(str(r[0]), str(r[1])) for r in rows}
