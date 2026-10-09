"""Scripted citations (knowledge-memory-storage task 7.5; retrieval "Live citations", "Unchanged without knowledge";
design D15).

`no_knowledge_replies.json` was recorded before the citation port (set `HORIZON_RECORD_SNAPSHOT=1` to re-record): a
character with no knowledge must reply exactly as before, because citations use their own RNG stream.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tests.conftest import Api
from tests.sessions.kit import chars, command, create, events, messages

SNAPSHOT = Path(__file__).parent / "fixtures" / "no_knowledge_replies.json"
RIN = "chr_seedRin"
PROMPTS = ["Morning! How was the market?", "What should I plant this spring?", "Tell me something that made you laugh."]


async def run_rin(api: Api) -> dict[str, Any]:
    await api.set_key()
    sid = (await create(api, "one_on_one", [RIN], world="wld_seedSunnyHollow"))["session"]["id"]
    await api.drive(6000)
    for p in PROMPTS:
        await command(api, sid, "send", {"text": p})
        await api.drive(15000)
    replies = chars(await messages(api, sid))
    emotions = [e["payload"]["emotion"] for e in await events(api, sid) if e["type"] == "emotion"]
    return {"contents": [m["content"] for m in replies], "emotions": emotions,
            "citations": [m.get("citations") or [] for m in replies]}


async def test_unchanged_without_knowledge(api: Api) -> None:
    got = await run_rin(api)
    if os.environ.get("HORIZON_RECORD_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    want = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert got == want


AMARA = "chr_seedAmara"
ASKS = ["What does the review say about burnout?", "How do night shifts affect burnout?",
        "What did the review recommend for staffing?", "Is burnout worse for new nurses?",
        "What does the evidence say about rest days?", "Summarise the review's main burnout findings."]


async def test_live_citations_cite_retrieved_passages(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    for p in ASKS:
        await command(api, sid, "send", {"text": p})
        await api.drive(15000)
    replies = chars(await messages(api, sid))[1:]
    cited = [m for m in replies if m.get("citations")]
    assert cited, "about half of the replies with hits cite"
    for m in cited:
        ns = [c["n"] for c in m["citations"]]
        assert ns == list(range(1, len(ns) + 1)) and len(ns) <= 2
        assert all(f"[{n}]" in m["content"] for n in ns)
        assert all(c["sourceId"].startswith("kno_") and c["quote"] and 0 <= c["score"] <= 1 for c in m["citations"])
        k = m["trace"]["knowledge"]
        assert k["trigger"] == "always" and k["query"]
        assert {r["chunkId"] for r in k["retrieved"] if r["cited"]} == {c["chunkId"] for c in m["citations"]}
        assert any(not r["cited"] for r in k["retrieved"])
        assert m["trace"]["context"]["used"]["knowledge"] > 0
        assert m["trace"]["context"]["used"]["memory"] == 0      # the scripted engine never uses memory (parity)
    for m in replies:
        if not m.get("citations"):
            assert "knowledge" not in m["trace"] and m["trace"]["context"]["used"]["knowledge"] == 0
    ends = [e for e in await events(api, sid) if e["type"] == "turn.end" and e["payload"].get("citations")]
    assert len(ends) == len(cited)


class PartialMarkers:
    """Maps three passages but only writes `[1]` and `[3]`."""

    name = "partial"
    version = "t1"
    prompt_version = None

    def __init__(self, api: Api) -> None:
        self.api = api

    async def run(self, ctx: Any) -> Any:
        from horizon.ai.ports import CitationMap, Emotion, Token
        from horizon.gateway.pipeline import SimulatedReply

        cites = [{"n": n, "sourceId": "kno_x", "title": "T", "type": "text", "chunkId": f"kch_{n}", "quote": "q",
                  "score": 0.8} for n in (1, 2, 3)]
        yield CitationMap(cites)
        spec = SimulatedReply(chunks=["One fact.[1] ", "Another.[3]"], first_token_ms=300, step_ms=50, tail_ms=20,
                              total_ms=500, model="deepseek/deepseek-v4.1-flash", tokens_in=500, tokens_cached=0,
                              tokens_out=6, cost_usd=0.0001)
        yield Emotion("happy")
        async for ch in self.api.rt.gateway.simulated_stream(ctx.call_ctx("reply"), spec, self.api.rt.clock.sleep):
            if ch.content:
                yield Token(ch.content)


async def test_turn_end_keeps_only_markers_present(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    api.rt.ai.override("turn", PartialMarkers(api))
    await command(api, sid, "send", {"text": "Facts please."})
    await api.drive(8000)
    reply = chars(await messages(api, sid))[-1]
    assert [c["n"] for c in reply["citations"]] == [1, 3]
    end = [e for e in await events(api, sid) if e["type"] == "turn.end"][-1]
    assert [c["n"] for c in end["payload"]["citations"]] == [1, 3]
