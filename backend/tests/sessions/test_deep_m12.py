"""The deep path through the runtime (rag design D10–D19; tasks 5.4, 5.5, 7.1, 7.3, 7.4, 8.1–8.4; deep-turn,
persona-prompt, provider-gateway, embedding-spaces and ai-ports specs). No network: the fake answers Jev call 2 with
"partly" (p 1.0) unless a test sets an answer, and every gate no unless a test sets it."""

from __future__ import annotations

import json
from typing import Any

import pytest

from horizon.ai.agent.docs_block import NOT_FOUND, STANDING
from horizon.ai.agent.rewrite import INSTRUCTION
from horizon.ai.contexts import DeepRequest
from horizon.gateway.fake import load_canned
from tests.conftest import Api
from tests.knowledge.kit import seed_before_d110
from tests.sessions.kit import API, chars, command, events, ledger, messages
from tests.sessions.test_gates_m12 import AMARA, HANA, RIN, SUNNY, agent, chat_caps, decisions, gate, rows, send

ANSWERS = {"type": "score", "score": 2.0, "confidence": 0.9, "probabilities": {"0": 0.05, "1": 0.05, "2": 0.9}}
NO_HELP = {"type": "score", "score": 0.0, "confidence": 0.95, "probabilities": {"0": 0.95, "1": 0.05, "2": 0.0}}
QUESTION = "What does the fatigue review say about long shift blocks?"


def chats(api: Api, purpose: str | None = None) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/chat/completions")
            and (purpose is None or r.headers.get("x-horizon-purpose") == purpose)]


def checks(api: Api) -> list[dict[str, Any]]:
    return [b for b in decisions(api) if any(k.startswith("passage:") for k in b["questions"])]


def purposes(rows_: list[dict[str, Any]]) -> list[str]:
    return [str(r["purpose"]) for r in rows_]


def nouls(api: Api, standalone: float, english: float = 0.95) -> None:
    assert api.rt.fake is not None
    api.rt.fake.answer_question("standalone", {"type": "noul", "noul": standalone})
    api.rt.fake.answer_question("english", {"type": "noul", "noul": english})


async def trace_version(api: Api, mid: str) -> str:
    from sqlalchemy import text

    async with api.rt.db.read() as conn:
        return str((await conn.execute(text("SELECT prompt_version FROM turn_traces WHERE message_id = :m"),
                                       {"m": mid})).scalar_one())


def measured_deadlines(api: Api) -> None:
    """U-45 made deep insight wait for every stage (`docsWaitAll`); these tests read the measured deadlines it replaces."""
    import dataclasses

    cfg = api.rt.runtime_cfg
    r = cfg.runtime.retrieval
    assert r.agent is not None
    r = dataclasses.replace(r, agent=dataclasses.replace(r.agent, docs_wait_all=False))
    api.rt.runtime_cfg = dataclasses.replace(cfg, runtime=dataclasses.replace(cfg.runtime, retrieval=r))


# ── 7.4 1:1 ──
async def test_a_deep_one_on_one_reply_carries_its_passages(api: Api) -> None:
    await seed_before_d110(api)   # the keyword-only documents this path was written against (set check aside)
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:kch_amaraFat02", ANSWERS)
    before = len(await ledger(api))
    [reply] = await send(api, sid, QUESTION)
    new = purposes((await ledger(api))[before:])
    assert new[0] == "turn_plan" and new.count("deep_check") == len(checks(api)) and "reply" in new
    assert new.index("reply") > max(i for i, p in enumerate(new) if p == "deep_check")
    body = chats(api, "reply")[-1]
    tail = body["messages"][-1]["content"]
    assert tail.startswith("# From your documents\n<passage>\n[1] Meridian Shift Fatigue Review 2025, p. 1\n")
    assert STANDING in tail and body["max_tokens"] == api.rt.runtime_cfg.runtime.reply_max_tokens.one_on_one_deep
    tr = reply["trace"]
    assert tr["graph"]["path"][-4:] == ["gather", "search", "check", "keep"]
    k = tr["knowledge"]
    assert k["trigger"] == "gated" and k["query"] == QUESTION and len(k["retrieved"]) == len(checks(api))
    assert next(r for r in k["retrieved"] if r["chunkId"] == "kch_amaraFat02")["n"] == 1
    assert await trace_version(api, reply["id"]) == "agent-1+docs-1"
    passages = rows(reply, "passage")
    assert len(passages) == len(checks(api)) and {r["result"] for r in passages} <= {"used", "below_threshold"}
    assert tr["context"]["used"]["knowledge"] > 0


async def test_a_confident_not_found_says_so_at_the_quick_length(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.9)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", NO_HELP)
    [reply] = await send(api, sid, "What does the review say about night-shift pay?")
    body = chats(api, "reply")[-1]
    assert body["messages"][-1]["content"].startswith(f"# Your documents\n{NOT_FOUND}")
    assert body["max_tokens"] == api.rt.runtime_cfg.runtime.reply_max_tokens.one_on_one
    assert not reply.get("citations") and await trace_version(api, reply["id"]) == "agent-1+nodocs-1"
    assert all(not r["cited"] for r in reply["trace"]["knowledge"]["retrieved"])


async def test_an_unsure_not_found_is_a_plain_quick_reply(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.5)                       # deep, but below t_confident: no abstaining
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", NO_HELP)
    [reply] = await send(api, sid, "What does the review say about night-shift pay?")
    tail = chats(api, "reply")[-1]["messages"][-1]["content"]
    assert "# Your documents" not in tail and "# From your documents" not in tail
    assert await trace_version(api, reply["id"]) == "agent-1"


async def test_a_deep_and_a_quick_turn_share_system_message_one(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    await send(api, sid, QUESTION)
    gate(api, AMARA, 0.1)
    await send(api, sid, "Thanks, that helps.")
    deep, quick = chats(api, "reply")[-2:]
    assert deep["messages"][0] == quick["messages"][0]
    assert "# From your documents" in deep["messages"][-1]["content"]
    assert all("# From your documents" not in str(m["content"]) for m in quick["messages"])


async def test_a_deep_turn_replays_from_json_with_no_call(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.ai.agent.turn import AgentTurnEngine
    from horizon.ai.contexts import TurnContext

    seen: list[TurnContext] = []
    run = AgentTurnEngine.run

    def capture(self: AgentTurnEngine, ctx: TurnContext) -> Any:
        seen.append(ctx)
        return run(self, ctx)

    monkeypatch.setattr(AgentTurnEngine, "run", capture)
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    await send(api, sid, QUESTION)
    ctx = seen[-1]
    assert ctx.knowledge and ctx.plan is not None and ctx.plan.knowledge_outcome is not None
    fake = api.rt.fake
    assert fake is not None
    counts = dict(fake.counts)
    again = TurnContext.model_validate_json(ctx.model_dump_json())
    engine = api.rt.ai.turn(True)
    assert engine.request(again)[0].messages == engine.request(ctx)[0].messages
    assert dict(fake.counts) == counts                    # no decision, embedding or chat request


# ── 5.4 the rewrite ──
async def test_the_rewrite_shares_the_reply_prefix(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    assert api.rt.fake is not None
    api.rt.fake.set_canned("query_rewrite", load_canned("query-rewrites")[1][:1])
    await send(api, sid, "How much worse is fatigue after long shift blocks?")
    [reply] = await send(api, sid, "and nights?")
    rewrite = chats(api, "query_rewrite")[-1]
    answer = chats(api, "reply")[-1]
    assert rewrite["messages"][:-1] == answer["messages"][:-1]   # the reply's prefix, byte for byte
    assert rewrite["messages"][-1] == {"role": "user", "content": INSTRUCTION}
    assert rewrite["temperature"] == 0.0 and rewrite["max_tokens"] == 60
    q = reply["trace"]["knowledge"]["query"]
    assert q == "how night shifts affect staff fatigue scores in the shift fatigue review"
    st = checks(api)[-1]["state"]["quoted_query"]
    assert st == {"message": "and nights?", "rewrite": q}
    row = rows(reply, "standalone")[0]
    assert (row["answer"], row["result"]) == ("no", "used")


async def test_a_short_message_starts_its_rewrite_with_the_plan_and_the_deep_path_joins_it(api: Api) -> None:
    """rag 11.9 (K15's trim 1, the user's choice): in 1:1 a short message to a speaker with documents has its rewrite
    started beside Jev call 1. A quick turn still pays for it; a deep turn joins it, so there is one call either way."""
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.1)
    await send(api, sid, "How much worse is fatigue after long shift blocks?")   # 9 words: no early rewrite
    assert chats(api, "query_rewrite") == []
    await send(api, sid, "and nights?")                                         # quick, but started early
    assert len(chats(api, "query_rewrite")) == 1
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    assert api.rt.fake is not None
    api.rt.fake.set_canned("query_rewrite", load_canned("query-rewrites")[1][:1])
    [reply] = await send(api, sid, "and weekends?")                             # deep: joins the early call
    assert len(chats(api, "query_rewrite")) == 2
    assert reply["trace"]["knowledge"]["query"] == "how night shifts affect staff fatigue scores in the shift fatigue review"


async def test_a_two_line_rewrite_is_rejected_for_the_fallback_query(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    assert api.rt.fake is not None
    api.rt.fake.set_canned("query_rewrite", [{"content": "night shift fatigue\nstaff rest days"}])
    await send(api, sid, "How much worse is fatigue after long shift blocks?")
    [reply] = await send(api, sid, "and nights?")
    st = checks(api)[-1]["state"]["quoted_query"]
    assert st["message"] == "and nights?" and len(st["earlier"]) == 2
    assert reply["trace"]["knowledge"]["query"] == "and nights?"


async def test_a_late_rewrite_falls_back_and_is_still_recorded(api: Api) -> None:
    measured_deadlines(api)
    from tests.helpers.storm import park_next_chat

    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    await send(api, sid, "How much worse is fatigue after long shift blocks?")
    release = park_next_chat(api.rt, "query_rewrite")
    await command(api, sid, "send", {"text": "and nights?"})
    await api.drive(15000)                     # past rewriteMs (1,500): the turn searched without it
    reply = chars(await messages(api, sid))[-1]
    assert reply["trace"]["knowledge"]["query"] == "and nights?"
    assert "earlier" in checks(api)[-1]["state"]["quoted_query"]
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "query_rewrite"]


async def test_regenerate_reuses_the_stored_rewrite(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    assert api.rt.fake is not None
    api.rt.fake.set_canned("query_rewrite", load_canned("query-rewrites")[1][:1])
    await send(api, sid, "How much worse is fatigue after long shift blocks?")
    [reply] = await send(api, sid, "and nights?")
    n = len(chats(api, "query_rewrite"))
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(15000)
    assert len(chats(api, "query_rewrite")) == n
    q = checks(api)[-1]["state"]["quoted_query"]
    assert q["rewrite"] == "how night shifts affect staff fatigue scores in the shift fatigue review"


async def test_a_usable_passage_that_lost_on_rank_says_not_in_top_k(api: Api) -> None:
    """U-35: every passage answers (all usable); a 1:1 keeps 3; the rest read "not in top 3", never "dropped"."""
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.9)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", ANSWERS)
    [reply] = await send(api, sid, QUESTION)
    actions = [r["action"] for r in rows(reply, "passage")]
    assert len(actions) > 3 and actions.count("kept") == 3
    assert set(actions) == {"kept", "not in top 3"}


async def test_each_passage_row_shows_the_found_line_after_the_usable_line(api: Api) -> None:
    """U-36: a row compares p_partly + p_answers with t_keep, then p_answers alone with t_found."""
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.9)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", ANSWERS)
    [reply] = await send(api, sid, QUESTION)
    for r in rows(reply, "passage"):
        assert [(c["name"], c["value"], c["threshold"]) for c in r["compared"]] == [
            ("t_keep", 0.95, 0.9), ("t_found", 0.9, 0.5)]


# ── 7.1 Jev call 2 ──
async def test_one_check_rate_limited_falls_back_for_that_passage(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", ANSWERS)
    api.rt.fake.refuse_question("passage:")
    [reply] = await send(api, sid, QUESTION)
    keys = [k for b in checks(api) for k in b["questions"]]
    assert len(keys) == len(set(keys))                                    # no retry for the refused one
    passages = rows(reply, "passage")
    assert [r["result"] for r in passages].count("fallback") == 1
    assert len(reply["trace"]["knowledge"]["retrieved"]) == len(passages)


async def test_two_late_and_none_found_is_the_fallback(api: Api) -> None:
    measured_deadlines(api)
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.9)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", NO_HELP)
    held = api.rt.fake.park_questions("passage:", 2)
    await command(api, sid, "send", {"text": QUESTION})
    await api.drive(15000)
    reply = chars(await messages(api, sid))[-1]
    for ev in held:
        ev.set()
    await api.drive(1000)
    assert "# Your documents" not in chats(api, "reply")[-1]["messages"][-1]["content"]   # never "not found"
    assert any(c.get("fallback") for c in reply["trace"]["calls"] if c["purpose"] == "deep_check")
    assert all("score" not in c for c in reply.get("citations") or [])


async def test_one_late_with_others_found_is_found(api: Api) -> None:
    measured_deadlines(api)
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", ANSWERS)
    [held] = api.rt.fake.park_questions("passage:", 1)
    await command(api, sid, "send", {"text": QUESTION})
    await api.drive(15000)
    held.set()
    await api.drive(1000)
    reply = chars(await messages(api, sid))[-1]
    assert "# From your documents" in chats(api, "reply")[-1]["messages"][-1]["content"]
    assert [r["result"] for r in rows(reply, "passage")].count("fallback") == 1
    assert not any(c.get("fallback") for c in reply["trace"]["calls"] if c["purpose"] == "deep_check")


@pytest.mark.parametrize(("p_set", "found"), [(0.9, True), (0.1, False)])
async def test_the_set_check(api: Api, p_set: float, found: bool) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.9)               # the fake's default check: "partly" at p 1.0, usable but never found
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage_set", {"type": "noul", "noul": p_set})
    [reply] = await send(api, sid, QUESTION)
    sets = [b for b in decisions(api) if "passage_set" in b["questions"]]
    assert len(sets) == 1 and len(sets[0]["state"]["quoted_passages"]) == 3
    [row] = rows(reply, "passage_set")
    assert row["answer"] == ("yes" if found else "no")
    tail = chats(api, "reply")[-1]["messages"][-1]["content"]
    assert ("These passages cover only part" in tail) is (not found)


# ── 7.3 the deep graph ──
async def test_a_bug_inside_the_deep_work_is_a_quick_reply(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.ai.agent.deep import DeepSteps

    async def boom(self: Any, req: Any, bundle: Any) -> Any:
        raise RuntimeError("a bug")

    monkeypatch.setattr(DeepSteps, "search", boom)
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    [reply] = await send(api, sid, QUESTION)
    assert reply["content"]
    assert chat_caps(api)[-1] == api.rt.runtime_cfg.runtime.reply_max_tokens.one_on_one
    assert any(c.get("fallback") for c in reply["trace"]["calls"] if c["purpose"] == "deep_check")
    assert [r["result"] for r in rows(reply, "passage")] == ["fallback"]


async def test_the_deep_graph_settles_the_same_twice(api: Api) -> None:
    """50 deep runs, run twice on the virtual clock, give identical results (D15's settle test)."""
    from horizon.ai.agent.deep import DeepSteps, build_deep_graph, run_deep
    from horizon.sessions.context import character_view, characters, session_context

    sid = await agent(api, "one_on_one", [AMARA])
    actor = await api.rt.sessions.get(sid)
    sctx = await session_context(api.rt, actor)
    view = character_view((await characters(api.rt, [AMARA]))[AMARA])
    planner = api.rt.ai.planner(True)
    graph = build_deep_graph(DeepSteps(planner.deps))
    words = ["fatigue", "burnout", "triage", "sleep", "rest", "chest pain", "long shifts", "nights", "October", "staff"]

    async def once() -> list[str]:
        out = []
        for i in range(50):
            req = DeepRequest(session=sctx, speaker=view, kind="reply", message=f"What about {words[i % 10]}? ({i})",
                              k=3, started_at=api.rt.clock.now())
            res = await run_deep(graph, req)
            out.append(res.model_dump_json(exclude={"calls"}))
        return out

    assert await once() == await once()


# ── 5.5 the embedding at the gate ──
async def _indexed_source(api: Api, cid: str) -> None:
    from tests.knowledge.kit import add_text, settle

    await add_text(api, "Kitchen notes", "# Rice\n\nWash the rice twice before you soak it for half an hour.",
                   character=cid)
    await settle(api, 2000)


async def test_the_embedding_starts_with_the_plan_even_when_the_gate_says_no(api: Api) -> None:
    """rag 11.5 (the user's choice, reversing D-100's "never before"): the message's embedding starts with Jev call 1,
    so a quick turn still has its one early embedding, linked to the message; the deep path adds none."""
    await api.set_key()
    await _indexed_source(api, HANA)
    sid = await agent(api, "one_on_one", [HANA], world=SUNNY)
    gate(api, HANA, 0.1)
    await send(api, sid, "How long should the rice soak?")
    embeds = [r for r in await ledger(api) if r["purpose"] == "query_embed"]
    assert len(embeds) == 1 and embeds[0]["message_id"] is not None


async def test_an_indexed_speaker_embeds_at_the_gate(api: Api) -> None:
    await api.set_key()
    await _indexed_source(api, HANA)
    sid = await agent(api, "one_on_one", [HANA], world=SUNNY)
    gate(api, HANA, 0.8)
    await send(api, sid, "How long should the rice soak?")
    embeds = [r for r in await ledger(api) if r["purpose"] == "query_embed"]
    assert len(embeds) == 1 and embeds[0]["message_id"] is not None


async def test_a_keyword_only_speaker_never_embeds(api: Api) -> None:
    await seed_before_d110(api)   # D-110 ships Amara's documents indexed
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    await send(api, sid, QUESTION)
    assert not [r for r in await ledger(api) if r["purpose"] == "query_embed"]


async def test_a_late_embedding_searches_by_keywords_and_is_still_recorded(api: Api) -> None:
    measured_deadlines(api)
    await api.set_key()
    await _indexed_source(api, HANA)
    sid = await agent(api, "one_on_one", [HANA], world=SUNNY)
    gate(api, HANA, 0.8)
    fake = api.rt.fake
    assert fake is not None
    release = fake.park_embedding(fake.counts["embeddings"] + 1)
    await command(api, sid, "send", {"text": "How long should the rice soak?"})
    await api.drive(15000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["trace"]["knowledge"]["trigger"] == "gated"      # searched by keywords
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "query_embed"]


async def test_a_documents_search_waits_for_its_vector(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """U-45 (the user's choice): the query vector arriving 3 s in (OpenRouter's 0.9-13 s, far past the old 200 ms) is
    waited for, so the documents search is hybrid."""
    from horizon.ai.agent import deep

    bundles: list[Any] = []
    real = deep.search

    async def spy(index: Any, bundle: Any, params: Any) -> Any:
        bundles.append(bundle)
        return await real(index, bundle, params)

    monkeypatch.setattr(deep, "search", spy)
    await api.set_key()
    await _indexed_source(api, HANA)
    sid = await agent(api, "one_on_one", [HANA], world=SUNNY)
    gate(api, HANA, 0.8)
    fake = api.rt.fake
    assert fake is not None
    release = fake.park_embedding(fake.counts["embeddings"] + 1)
    await command(api, sid, "send", {"text": "How long should the rice soak?"})
    await api.drive(3000)
    assert not bundles                       # still waiting for the vector, past the old 200 ms
    release.set()
    await api.drive(15000)
    assert bundles and any(bundles[0].dense.values())
    tr = chars(await messages(api, sid))[-1]["trace"]
    assert tr["knowledge"]["trigger"] == "gated"
    assert tr["search"]["vectorMs"] >= 3000   # U-58: Insight shows what the search waited for


async def test_both_group_repliers_share_one_embedding(api: Api) -> None:
    await api.set_key()
    await _indexed_source(api, HANA)
    await _indexed_source(api, RIN)
    sid = await agent(api, "group", [HANA, RIN], world=SUNNY)
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("who_first", {"type": "choice", "choice": HANA, "confidence": 0.9,
                                       "probabilities": {HANA: 0.9}})
    fake.answer_question("who_second", {"type": "choice", "choice": RIN, "confidence": 0.9,
                                        "probabilities": {RIN: 0.9}})
    gate(api, HANA, 0.8)
    gate(api, RIN, 0.8)
    replies = await send(api, sid, "How long should the rice soak?", 30000)
    assert [r["author"]["characterId"] for r in replies] == [HANA, RIN]
    embeds = [r for r in await ledger(api) if r["purpose"] == "query_embed"]
    assert len(embeds) == 1
    assert all(r["trace"]["knowledge"]["trigger"] == "gated" for r in replies)


async def test_a_groups_second_speaker_gets_its_own_rewrite(api: Api) -> None:
    from tests.sessions.test_gates_m12 import MEI

    sid = await agent(api, "group", [AMARA, MEI])
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("who_first", {"type": "choice", "choice": AMARA, "confidence": 0.9,
                                       "probabilities": {AMARA: 0.9}})
    fake.answer_question("who_second", {"type": "choice", "choice": MEI, "confidence": 0.9,
                                        "probabilities": {MEI: 0.9}})
    gate(api, AMARA, 0.8)
    gate(api, MEI, 0.8)
    nouls(api, standalone=0.06)
    fake.set_canned("query_rewrite", load_canned("query-rewrites")[1][:1])
    await send(api, sid, "and nights?", 30000)
    rewrites = [r for r in await ledger(api) if r["purpose"] == "query_rewrite"]
    assert len(rewrites) == 2 and len({r["character_id"] for r in rewrites}) == 2


async def test_unused_events_helper(api: Api) -> None:
    assert events is not None and API
