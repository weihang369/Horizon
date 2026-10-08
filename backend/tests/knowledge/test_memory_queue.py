"""The post-turn memory queue and the memory side of a blocked reply (knowledge-memory-storage task 6.6;
long-term-memory "Replies feed the memory writer after they end"; session-runtime "A blocked reply is scrubbed")."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy import text

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import GuardrailResult, Insert, MemoryDraft
from tests.conftest import Api
from tests.knowledge.kit import API
from tests.sessions.kit import chars, create, messages

AMARA = "chr_seedAmara"
MERIDIAN = "wld_seedMeridian"


class RememberEverything:
    """A memory writer that remembers every reply it is given."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def after_turn(self, ctx: TurnContext, perspective: str, message_id: str) -> list[Any]:
        self.calls.append(message_id)
        return [Insert(MemoryDraft(kind="event", text=f"Said something in {ctx.session.session_id}.", importance=0.4,
                                   source_session_id=ctx.session.session_id, source_message_id=message_id,
                                   source_mode=ctx.session.mode))]


class Broken:
    async def after_turn(self, ctx: TurnContext, perspective: str, message_id: str) -> list[Any]:
        raise RuntimeError("the writer broke")


async def memory_ids(api: Api) -> list[str]:
    return [m["id"] for m in (await api.client.get(f"{API}/characters/{AMARA}/memory")).json()]


async def one_reply(api: Api) -> str:
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    r = await api.post(f"{API}/sessions/{sid}/send", {"text": "How was the shift?"})
    assert r.status_code == 202
    await api.drive(12000)
    return sid


async def test_default_writer_remembers_nothing(api: Api) -> None:
    before = await memory_ids(api)
    sid = await one_reply(api)
    assert chars(await messages(api, sid))[-1]["status"] == "complete"
    assert await memory_ids(api) == before


async def test_a_writer_sees_complete_replies_and_its_memories_land(api: Api) -> None:
    w = RememberEverything()
    api.rt.ai.override("memory_writer", w)
    sid = await one_reply(api)
    replies = [m["id"] for m in chars(await messages(api, sid)) if m["status"] == "complete"]
    assert w.calls == replies
    async with api.rt.db.read() as conn:
        sources = set((await conn.execute(text("SELECT source_message_id FROM memory_items WHERE character_id = :c AND "
                                               "is_seed = 0"), {"c": AMARA})).scalars())
    assert sources == set(replies)


async def test_failing_writer_leaves_the_session_alone(api: Api, caplog: pytest.LogCaptureFixture) -> None:
    api.rt.ai.override("memory_writer", Broken())
    with caplog.at_level(logging.ERROR, logger="horizon.sessions"):
        sid = await one_reply(api)
    assert [m["status"] for m in chars(await messages(api, sid))] == ["complete", "complete"]
    assert any("memory writer failed" in r.getMessage() for r in caplog.records)


async def test_blocked_reply_leaves_no_memory(api: Api) -> None:
    w = RememberEverything()
    api.rt.ai.override("memory_writer", w)
    planted: list[str] = []

    class BlockAndPlant:
        """Blocks every reply; first plants a memory sourced from it (as if an early writer had already run)."""

        async def check(self, ctx: TurnContext, text_: str) -> GuardrailResult:
            if ctx.message_id:
                [mid] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft(
                    kind="fact", text="A thing the blocked reply said.", importance=0.5,
                    source_message_id=ctx.message_id))])
                planted.append(mid)
            return GuardrailResult("block", [{"name": "sfw", "verdict": "block", "p": 0.99}])

    api.rt.ai.override("guardrail", BlockAndPlant())
    sid = await one_reply(api)
    blocked = [m for m in chars(await messages(api, sid)) if m["status"] == "error"]
    assert blocked and w.calls == []
    async with api.rt.db.read() as conn:
        left = (await conn.execute(text("SELECT count(*) FROM memory_items WHERE source_message_id IN "
                                        f"({','.join(repr(m['id']) for m in blocked)})"))).scalar_one()
    assert planted and left == 0
