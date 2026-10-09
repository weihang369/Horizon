"""Naive prompt v2 (knowledge-memory-storage task 7.6; retrieval "Cited passage", "Recalled memory in the trace";
"With nothing retrieved, its request SHALL be the same as before"; design D15, D-93). No network: the fake answers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from horizon.ai.contexts import (
    CharacterView,
    KnowledgeHit,
    LineHint,
    MemoryHit,
    MessageView,
    ParticipantView,
    SessionContext,
    TurnContext,
    WorldView,
)
from horizon.ai.naive.prompt import CITE_LINE, PROMPT_VERSION, retrieval_block, system_prompt, turn_cue
from horizon.ai.naive.turn import NaiveTurnEngine
from horizon.ai.naive.window import render_history
from horizon.ai.ports import Insert, MemoryDraft
from horizon.ai.retrieval import QueryBundle, ScopedIndex
from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, messages
from tests.sessions.test_naive import chat_bodies, sse

AMARA = "chr_seedAmara"


def ctx(**extra: Any) -> TurnContext:
    s = SessionContext(session_id="ses_x1", world=WorldView(id="wld_seedMeridian", name="Meridian Council"),
                       mode="one_on_one", title="Chat",
                       participants=[ParticipantView(character_id=AMARA, name="Amara Okafor", role="speaker",
                                                     energy={"current": 500, "max": 1000})],
                       recent=[MessageView(id="msg_u1", seq=1, author_type="user", name="You", kind="chat", content="Hi there.")],
                       history_tokens=12)
    return TurnContext(session=s, speaker=CharacterView(id=AMARA, name="Amara Okafor", profile={"name": "Amara"}),
                       message_id="msg_x1", prompt="Hi there.", line=LineHint(kind="chat"), turn_index=3, max_tokens=350,
                       **extra)


def hit(n: int, section: str) -> KnowledgeHit:
    return KnowledgeHit(chunk_id=f"kch_{n}", source_id="kno_1", title="Review", type="pdf", locator=f"p. {n}",
                        text=f"Passage {n}.", section_text=section, score=0.9 - n / 10)


def engine(api: Api) -> NaiveTurnEngine:
    eng: NaiveTurnEngine = api.rt.ai._build("turn", "naive")
    return eng


def test_prompt_version_is_v2() -> None:
    assert PROMPT_VERSION == "naive-2" and NaiveTurnEngine.prompt_version == "naive-2"


async def test_no_hits_request_is_the_v1_request(api: Api) -> None:
    c = ctx()
    req, prefix = engine(api).request(c)
    v1 = [{"role": "system", "content": system_prompt(c)}, *render_history(c.session.recent, AMARA, "User")]
    cue = turn_cue(c)
    if cue:
        v1.append({"role": "system", "content": cue})
    assert req.messages == v1 and prefix == v1[:1]


async def test_block_goes_after_the_history_one_passage_per_section(api: Api) -> None:
    c = ctx(knowledge=[hit(1, "Section A text."), hit(2, "Section A text."), hit(3, "Section B text.")],
            memory=[MemoryHit(id="mem_1", kind="fact", text="Amara runs at dawn.", source_session_id=None, score=0.9)],
            query="Hi there.")
    req, _ = engine(api).request(c, retrieval_block(c))
    last = req.messages[-1]
    assert last["role"] == "system" and req.messages[-2]["content"].endswith("Hi there.")
    body = last["content"]
    assert "[1] Review, p. 1: Section A text." in body and "[2] Review, p. 3: Section B text." in body
    assert "[3]" not in body and "- Amara runs at dawn." in body and body.endswith(CITE_LINE)


async def _naive_turn(api: Api, answer: list[str], prompt: str) -> dict[str, Any]:
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"turn": "naive"}})
    assert r.status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(answer))
    await command(api, sid, "send", {"text": prompt})
    await api.drive(10000)
    reply: dict[str, Any] = chars(await messages(api, sid))[-1]
    return reply


async def test_cited_passage(api: Api) -> None:
    reply = await _naive_turn(api, ["<e:happy>The review is clear: ", "burnout rose on nights.[2]"],
                              "What does the review say about burnout?")
    block = chat_bodies(api)[-1]["messages"][-1]["content"]
    assert "[1] " in block and "[2] " in block and CITE_LINE in block
    assert reply["content"].endswith("[2]") and [c["n"] for c in reply["citations"]] == [2]
    k = reply["trace"]["knowledge"]
    assert k["trigger"] == "always" and k["query"] == "What does the review say about burnout?"
    cited = [r for r in k["retrieved"] if r["cited"]]
    assert len(cited) == 1 and cited[0]["n"] == 2 and cited[0]["chunkId"] == reply["citations"][0]["chunkId"]
    assert any(not r["cited"] for r in k["retrieved"])
    assert reply["trace"]["context"]["used"]["knowledge"] > 0


class TwoMemories:
    async def recall(self, index: ScopedIndex, query: QueryBundle, k: int) -> list[MemoryHit]:
        return list(await index.memory_recent(2))


async def test_recalled_memory_in_the_trace(api: Api) -> None:
    api.rt.ai.override("memory_retriever", TwoMemories())
    await api.rt.memory.apply(AMARA, "wld_seedMeridian", [Insert(MemoryDraft("fact", "Kai prefers green tea now.", 0.6))])
    reply = await _naive_turn(api, ["<e:neutral>I remember."], "Do you remember our talk?")
    recalled = reply["trace"]["memory"]["recalled"]
    assert len(recalled) == 2 and all(m["memoryItemId"].startswith("mem_") and m["text"] for m in recalled)
    assert reply["trace"]["context"]["used"]["memory"] > 0
    block = chat_bodies(api)[-1]["messages"][-1]["content"]
    assert all(f"- {m['text']}" in block for m in recalled)
    async with api.rt.db.read() as conn:
        refs = set((await conn.execute(text("SELECT memory_item_id FROM trace_memory_refs WHERE message_id = :m"),
                                       {"m": reply["id"]})).scalars())
    assert refs == {m["memoryItemId"] for m in recalled}
