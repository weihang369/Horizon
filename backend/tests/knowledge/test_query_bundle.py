"""The query bundle (knowledge-memory-storage task 7.4; retrieval "One query embedding per user message", "Nobody has
vectors", "Scripted profile", "Slow embedding", "Cap reached"; design D12)."""

from __future__ import annotations

from typing import Any

from horizon.ai.embedder import Embedded
from horizon.gateway.errors import ProviderError
from tests.conftest import Api
from tests.knowledge.kit import API, add_text, settle
from tests.sessions.kit import chars, command, create, events, messages

AMARA = "chr_seedAmara"
TRIO = ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]
NOTE = "Amara's clinic notes: burnout in night-shift nurses rises after the third consecutive week of nights."


async def naive_retrieval(api: Api) -> None:
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted",
                                                    "overrides": {"knowledge_retriever": "naive", "embedder": "naive"}})
    assert r.status_code == 204, r.text


async def indexed_note(api: Api) -> None:
    src = await add_text(api, "Clinic notes", NOTE, character=AMARA)
    await settle(api)
    got = await api.json(f"{API}/knowledge/{src['id']}")
    assert got["source"]["status"] == "indexed", got


async def query_rows(api: Api) -> list[dict[str, Any]]:
    from tests.sessions.kit import ledger

    return [r for r in await ledger(api) if r["purpose"] == "query_embed"]


async def group_send(api: Api, text: str) -> tuple[str, list[dict[str, Any]]]:
    sid = (await create(api, "group", TRIO))["session"]["id"]
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    await command(api, sid, "send", {"text": text})
    await api.drive(40000)
    return sid, chars(await messages(api, sid))


async def test_group_message_to_three_characters_embeds_once(api: Api) -> None:
    await api.set_key()
    await naive_retrieval(api)
    await indexed_note(api)
    _, replies = await group_send(api, "What happens to burnout on night shifts?")
    assert len(replies) == 3
    rows = await query_rows(api)
    assert len(rows) == 1 and rows[0]["category"] == "embedding"
    listed = [[c for c in m["trace"]["calls"] if c["purpose"] == "query_embed"] for m in replies]
    assert [len(x) for x in listed] == [1, 0, 0]
    assert listed[0][0]["costUsd"] == round(float(rows[0]["cost_usd"]), 6)


async def test_nobody_has_vectors_embeds_nothing(api: Api) -> None:
    await api.set_key()
    await naive_retrieval(api)
    _, replies = await group_send(api, "What happens to burnout on night shifts?")
    assert len(replies) == 3
    assert await query_rows(api) == []


async def test_scripted_profile_embeds_nothing(api: Api) -> None:
    await api.set_key()
    await indexed_note(api)
    _, replies = await group_send(api, "What happens to burnout on night shifts?")
    assert len(replies) == 3
    assert await query_rows(api) == []


class SlowQueries:
    """Wraps the active embedder: query embeddings take `ms` of clock time first (a slow provider)."""

    def __init__(self, api: Api, inner: Any, ms: float) -> None:
        self.api, self.inner, self.ms = api, inner, ms
        self.name = inner.name

    async def embed(self, texts: list[str], *, kind: str, space: Any, ctx: Any, hooks: Any = None) -> Embedded:
        if kind == "query":
            await self.api.rt.clock.sleep(self.ms / 1000)
        out: Embedded = await self.inner.embed(texts, kind=kind, space=space, ctx=ctx, hooks=hooks)
        return out

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


async def test_slow_embedding_replies_with_keywords_and_still_records_the_call(api: Api) -> None:
    await api.set_key()
    await naive_retrieval(api)
    await indexed_note(api)
    api.rt.ai.override("embedder", SlowQueries(api, api.rt.ai.embedder(True), ms=3000))
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "What happens to burnout on night shifts?"})
    await api.drive(12000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "complete"
    assert not [c for c in reply["trace"]["calls"] if c["purpose"] == "query_embed"]
    assert len(await query_rows(api)) == 1          # the late call is still billed and recorded


class CapRefusesQueries(SlowQueries):
    """Today's cap refuses query embeddings (the gateway's own refusal, raised before any request)."""

    async def embed(self, texts: list[str], *, kind: str, space: Any, ctx: Any, hooks: Any = None) -> Embedded:
        if kind == "query":
            raise ProviderError("daily_budget_exceeded", "Today's spending cap is reached.")
        return await super().embed(texts, kind=kind, space=space, ctx=ctx, hooks=hooks)


async def test_cap_refusing_the_query_embedding_means_keywords_and_no_error_event(api: Api) -> None:
    await api.set_key()
    await naive_retrieval(api)
    await indexed_note(api)
    api.rt.ai.override("embedder", CapRefusesQueries(api, api.rt.ai.embedder(True), ms=0))
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    before = len(await events(api, sid))
    await command(api, sid, "send", {"text": "What happens to burnout on night shifts?"})
    await api.drive(12000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "complete" and reply["content"]
    assert await query_rows(api) == []
    assert not [e for e in (await events(api, sid))[before:] if e["type"] == "error"]
