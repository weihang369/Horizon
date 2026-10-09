"""Forget (knowledge-memory-storage tasks 6.2–6.3, 6.5; long-term-memory "Forget removes a memory and all its
versions", "Forget scrubs the memory from past insights", "Forget notifies the AI layer"; design D14, D16)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import Emotion, Insert, MemoryDraft, Supersede, Token, TracePatch, TurnEvent
from horizon.gateway.pipeline import SimulatedReply
from tests.conftest import Api
from tests.knowledge.kit import API, HANA, SUNNY, drain
from tests.sessions.kit import chars, create, messages

MERIDIAN = "wld_seedMeridian"
AMARA = "chr_seedAmara"


class RecallEngine:
    """A test engine whose reply recalls the given memories in its trace (what a naive reply with memory does)."""

    name = "recall"
    version = "t1"
    prompt_version = None

    def __init__(self, api: Api, recalled: list[dict[str, Any]], reply: str = "I remember that.") -> None:
        self.api = api
        self.recalled = recalled
        self.reply = reply

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        spec = SimulatedReply(chunks=[self.reply], first_token_ms=300, step_ms=50, tail_ms=20, total_ms=500,
                              model="deepseek/deepseek-v4.1-flash", tokens_in=500, tokens_cached=0, tokens_out=5,
                              cost_usd=0.0001)
        yield Emotion("happy")
        async for ch in self.api.rt.gateway.simulated_stream(ctx.call_ctx("reply"), spec, self.api.rt.clock.sleep):
            if ch.content:
                yield Token(ch.content)
        yield TracePatch({"memory": {"recalled": self.recalled}})


async def remember(api: Api, text_: str, character: str = AMARA, world: str = MERIDIAN) -> str:
    [mid] = await api.rt.memory.apply(character, world, [Insert(MemoryDraft(kind="fact", text=text_, importance=0.7))])
    return mid


async def recall_in_session(api: Api, mid: str, text_: str) -> tuple[str, str]:
    """A live 1:1 with Amara whose reply recalls `mid`; returns (session id, the reply's message id)."""
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    api.rt.ai.override("turn", RecallEngine(api, [{"memoryItemId": mid, "text": text_}]))
    r = await api.post(f"{API}/sessions/{sid}/send", {"text": "Do you remember?"})
    assert r.status_code == 202, r.text
    await api.drive(8000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["trace"]["memory"]["recalled"][0]["text"] == text_
    return sid, reply["id"]


async def refs(api: Api, mid: str) -> set[str]:
    async with api.rt.db.read() as conn:
        return set((await conn.execute(text("SELECT message_id FROM trace_memory_refs WHERE memory_item_id = :m"),
                                       {"m": mid})).scalars())


async def test_forget_the_current_version_takes_the_chain(api: Api) -> None:
    [a] = await api.rt.memory.apply(HANA, SUNNY, [Insert(MemoryDraft("fact", "Hana's cat is called Mochi.", 0.5))])
    [b] = await api.rt.memory.apply(HANA, SUNNY, [Supersede([a], MemoryDraft("fact", "Hana's cat is called Daifuku.", 0.6))])
    sub = api.rt.bus.subscribe("global")
    r = await api.client.delete(f"{API}/memory/{b}")
    assert r.status_code == 204
    async with api.rt.db.read() as conn:
        left = (await conn.execute(text("SELECT count(*) FROM memory_items WHERE id IN (:a, :b)"), {"a": a, "b": b})).scalar_one()
        hits = (await conn.execute(text("SELECT count(*) FROM memory_fts WHERE memory_fts MATCH 'mochi OR daifuku'"))).scalar_one()
    assert left == 0 and hits == 0
    assert [e for e in drain(sub) if e.get("kind") == "memory"] == [
        {"type": "entity.changed", "kind": "memory", "id": HANA, "worldId": SUNNY}]
    api.rt.bus.unsubscribe(sub)


async def test_unknown_memory_is_404(api: Api) -> None:
    r = await api.client.delete(f"{API}/memory/mem_nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


async def test_live_insight_writes_refs_and_fork_copies_them(api: Api) -> None:
    mid = await remember(api, "Amara's sister lives in Ipoh.")
    sid, msg = await recall_in_session(api, mid, "Amara's sister lives in Ipoh.")
    assert await refs(api, mid) == {msg}
    r = await api.post(f"{API}/sessions/{sid}/fork", {})
    assert r.status_code == 201, r.text
    fork = r.json()["session"]["id"]
    forked = chars(await messages(api, fork))[-1]
    assert forked["id"] != msg
    assert await refs(api, mid) == {msg, forked["id"]}


async def test_forget_scrubs_live_and_forked_insights_but_not_messages(api: Api) -> None:
    secret = "Amara's locker code is 4721."
    mid = await remember(api, secret)
    sid, msg = await recall_in_session(api, mid, secret)
    assert await refs(api, mid) == {msg} | (await refs(api, mid))
    fork = (await api.post(f"{API}/sessions/{sid}/fork", {})).json()["session"]["id"]
    before = {s: [m["content"] for m in await messages(api, s)] for s in (sid, fork)}
    sub = api.rt.bus.subscribe("global")
    assert (await api.client.delete(f"{API}/memory/{mid}")).status_code == 204
    await api.drive(1)  # the live actors' scrub messages run
    for s in (sid, fork):
        msgs = await messages(api, s)
        assert [m["content"] for m in msgs] == before[s]
        recalled = chars(msgs)[-1]["trace"]["memory"]["recalled"]
        assert recalled == [{"memoryItemId": mid, "text": "(forgotten)"}]
        evs = (await api.json(f"{API}/sessions/{s}/events?limit=1000"))["items"]
        assert all(secret not in str(e["payload"]) for e in evs)
    assert await refs(api, mid) == set()
    async with api.rt.db.read() as conn:
        purge = [json.loads(x) for x in (await conn.execute(text("SELECT ids FROM ai_purge_queue WHERE scope = 'memory'")))
                 .scalars().all()]
    assert purge and purge[-1]["memoryItemIds"] == [mid] and purge[-1]["characterId"] == AMARA
    assert msg in purge[-1]["messageIds"]
    api.rt.bus.unsubscribe(sub)


async def test_forget_reaches_the_forget_hook(api: Api) -> None:
    calls: list[tuple[list[str], str, list[str]]] = []

    class Hooks:
        async def on_delete(self, scope: str, ids: Any) -> None:
            return None

        async def on_forget(self, memory_item_ids: list[str], character_id: str, message_ids: list[str]) -> None:
            calls.append((list(memory_item_ids), character_id, list(message_ids)))

    api.rt.purge.hooks = Hooks()
    mid = await remember(api, "Amara once lived in Penang.")
    _, msg = await recall_in_session(api, mid, "Amara once lived in Penang.")
    assert (await api.client.delete(f"{API}/memory/{mid}")).status_code == 204
    await api.rt.purge.idle.wait()
    assert calls == [([mid], AMARA, [msg])]


async def test_forget_retried_after_a_crash(api: Api) -> None:
    import asyncio

    from horizon.services.purge import PurgeWorker

    mid = await remember(api, "Amara collects stamps.")
    await api.rt.purge.stop()                   # the backend "crashes" before the hook runs
    assert (await api.client.delete(f"{API}/memory/{mid}")).status_code == 204
    calls: list[tuple[list[str], str]] = []

    class Hooks:
        async def on_delete(self, scope: str, ids: Any) -> None:
            return None

        async def on_forget(self, memory_item_ids: list[str], character_id: str, message_ids: list[str]) -> None:
            calls.append((list(memory_item_ids), character_id))

    worker = PurgeWorker(api.rt.db, Hooks(), api.rt.now_iso)
    worker.start()                              # the restart drains pending entries
    await asyncio.wait_for(worker.idle.wait(), 5)
    await worker.stop()
    assert calls == [([mid], AMARA)]
    async with api.rt.db.read() as conn:
        done = (await conn.execute(text("SELECT done_at FROM ai_purge_queue WHERE scope = 'memory'"))).scalar_one()
    assert done is not None
