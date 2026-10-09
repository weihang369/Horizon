"""`MemoryStore.apply` (knowledge-memory-storage task 6.1; long-term-memory "Memory writes are applied together",
"Memory writes are serialised per character")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text

from horizon.ai.ports import Insert, MemoryDraft, Reinforce, Supersede, Touch
from horizon.db import spaces
from horizon.services.memory.store import MemoryOpError
from tests.conftest import Api
from tests.knowledge.kit import API, HANA, SUNNY, drain, embedding_rows

MERIDIAN = "wld_seedMeridian"
AMARA = "chr_seedAmara"


def draft(text_: str, **kw: Any) -> MemoryDraft:
    return MemoryDraft(kind=kw.pop("kind", "fact"), text=text_, importance=kw.pop("importance", 0.6), **kw)


async def listed(api: Api, character: str = HANA) -> list[dict[str, Any]]:
    return list((await api.client.get(f"{API}/characters/{character}/memory")).json())


async def fts(api: Api, word: str) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM memory_fts WHERE memory_fts MATCH :w"), {"w": word}))
                   .scalar_one())


async def test_insert_is_listed_searchable_and_announced(api: Api) -> None:
    sub = api.rt.bus.subscribe("global")
    [mid] = await api.rt.memory.apply(HANA, SUNNY, [Insert(draft("Hana prefers kelp broth.", kind="preference"))])
    assert mid.startswith("mem_")
    assert any(m["id"] == mid and m["text"] == "Hana prefers kelp broth." for m in await listed(api))
    assert await fts(api, "kelp") == 1
    events = [e for e in drain(sub) if e.get("kind") == "memory"]
    assert events == [{"type": "entity.changed", "kind": "memory", "id": HANA, "worldId": SUNNY}]
    api.rt.bus.unsubscribe(sub)


async def test_one_bad_operation_writes_nothing(api: Api) -> None:
    before = await listed(api)
    with pytest.raises(MemoryOpError):
        await api.rt.memory.apply(HANA, SUNNY, [Insert(draft("Hana keeps a zorblefax jar.")), Reinforce("mem_nope", 0.9)])
    assert await listed(api) == before and await fts(api, "zorblefax") == 0
    for bad in ([Insert(draft("x", importance=1.5))], [Insert(draft("  "))], [Insert(draft("x", kind="rumour"))]):
        with pytest.raises(MemoryOpError):
            await api.rt.memory.apply(HANA, SUNNY, bad)


async def test_supersede_lists_only_the_new_version(api: Api) -> None:
    [a] = await api.rt.memory.apply(HANA, SUNNY, [Insert(draft("Hana's shop opens at eight."))])
    [b] = await api.rt.memory.apply(HANA, SUNNY, [Supersede([a], draft("Hana's shop opens at seven now."))])
    ids = [m["id"] for m in await listed(api)]
    assert b in ids and a not in ids
    async with api.rt.db.read() as conn:
        assert (await conn.execute(text("SELECT superseded_by FROM memory_items WHERE id = :a"), {"a": a})).scalar_one() == b


async def test_another_worlds_memory_is_refused(api: Api) -> None:
    [theirs] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(draft("Amara takes the night shift."))])
    with pytest.raises(MemoryOpError):
        await api.rt.memory.apply(HANA, SUNNY, [Reinforce(theirs, 0.9)])
    with pytest.raises(MemoryOpError):
        await api.rt.memory.apply(HANA, MERIDIAN, [Insert(draft("wrong world"))])
    async with api.rt.db.read() as conn:
        imp = (await conn.execute(text("SELECT importance FROM memory_items WHERE id = :i"), {"i": theirs})).scalar_one()
    assert imp == pytest.approx(0.6)


async def test_reinforce_and_touch(api: Api) -> None:
    [a] = await api.rt.memory.apply(HANA, SUNNY, [Insert(draft("Hana hums while cooking."))])
    await api.rt.memory.apply(HANA, SUNNY, [Reinforce(a, 0.95), Touch([a]), Touch([a])])
    async with api.rt.db.read() as conn:
        r = (await conn.execute(text("SELECT importance, recall_count, last_recalled_at FROM memory_items WHERE id = :i"),
                                {"i": a})).mappings().one()
    assert r["importance"] == pytest.approx(0.95) and r["recall_count"] == 2 and r["last_recalled_at"]


async def test_two_sessions_at_once_apply_one_after_the_other(api: Api) -> None:
    [a] = await api.rt.memory.apply(HANA, SUNNY, [Insert(draft("Hana's favourite tea is sencha."))])
    results = await asyncio.gather(
        api.rt.memory.apply(HANA, SUNNY, [Supersede([a], draft("Hana's favourite tea is genmaicha."))]),
        api.rt.memory.apply(HANA, SUNNY, [Supersede([a], draft("Hana's favourite tea is hojicha."))]),
        return_exceptions=True)
    # Serialised in queue order: the first replaces `a`; the second was written from a stale view and fails whole.
    assert not isinstance(results[0], BaseException) and isinstance(results[1], MemoryOpError)
    current = [m for m in await listed(api) if "favourite tea" in m["text"]]
    assert [m["text"] for m in current] == ["Hana's favourite tea is genmaicha."]


async def test_vectors_with_a_key_and_none_without(api: Api) -> None:
    mem, _ = spaces.vec_tables(api.rt.space_id or "")
    [a] = await api.rt.memory.apply(HANA, SUNNY, [Insert(draft("No key, no vector."))])
    await api.set_key()
    [b] = await api.rt.memory.apply(HANA, SUNNY, [Insert(draft("With a key, a vector."))])
    async with api.rt.db.read() as conn:
        def count(mid: str) -> Any:
            return conn.execute(text(f"SELECT count(*) FROM {mem} WHERE rid = (SELECT rid FROM memory_items WHERE id = :i)"),
                                {"i": mid})
        assert (await count(a)).scalar_one() == 0
        assert (await count(b)).scalar_one() == 1
    rows = await embedding_rows(api, HANA)
    assert [r["purpose"] for r in rows] == ["embed_doc"]
