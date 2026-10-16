"""Recall in live `agent` sessions (memory design D26–D35; session-recall "Recall only", "Two kept", "Every answer
late", "No vector", "Overflow memory used", "Recall stays in its scope"; deep-turn "Recall-only speaker", "Both in
parallel", "Stop during both"; system1-trace's earlier and recall rows)."""

from __future__ import annotations

import dataclasses
from typing import Any

from sqlalchemy import text

from horizon.ai.agent.recall import LINES_HEADING, MEMORIES_HEADING
from horizon.ai.ports import Insert, MemoryDraft
from horizon.services.memory.corpora import Overflow, SessionLines
from tests.conftest import Api
from tests.helpers.storm import after_storm
from tests.sessions.kit import command, ledger
from tests.sessions.test_deep_m12 import ANSWERS, chats
from tests.sessions.test_gates_m12 import AMARA, MERIDIAN, agent, gate, send
from tests.sessions.test_summary import small_windows

LONG = "Question number {i}: about sleep, rotas, coffee and the long walk home after a night shift with Mia?"
YES = {"type": "noul", "noul": 0.85}


def recall_yes(api: Api, cid: str = AMARA, p: float = 0.9) -> None:
    assert api.rt.fake is not None
    api.rt.fake.answer_question(f"earlier:{cid}", {"type": "noul", "noul": p})


def checks_say(api: Api, raw: dict[str, Any] | None = YES) -> None:
    assert api.rt.fake is not None
    api.rt.fake.answer_question("recall:*", raw)


async def indexed_session(api: Api, n: int = 4) -> str:
    sid = await agent(api, "one_on_one", [AMARA])
    small_windows(api)
    for i in range(n):
        await send(api, sid, LONG.format(i=i))
    await api.drive(2000)
    async with api.rt.db.read() as conn:
        rows = (await conn.execute(text("SELECT count(*) FROM message_index WHERE session_id = :s"), {"s": sid})
                ).scalar_one()
    assert rows > 0
    return sid


def rows_of(reply: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    return [r for r in (reply.get("trace") or {}).get("system1", {}).get("questions", []) if r["id"] == qid]


def decisions(api: Api) -> list[dict[str, Any]]:
    import json

    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/alpha/decisions")]


# ── 7.3 scope ──
async def test_recall_stays_in_its_scope(api: Api) -> None:
    sid = await indexed_session(api)
    other = await indexed_session(api, n=3)
    space = api.rt.space_id or ""
    lines = SessionLines(api.rt, MERIDIAN, sid, 10_000, space)
    mine = await lines.fts('"sleep" OR "rotas"', 50)
    async with api.rt.db.read() as conn:
        theirs = set((await conn.execute(text("SELECT rid FROM message_index WHERE session_id = :s"), {"s": other}))
                     .scalars())
    assert mine and not {c.rid for c in mine} & theirs
    assert await SessionLines(api.rt, "wld_seedSunnyHollow", sid, 10_000, space).fts('"sleep"', 50) == []
    [m1] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft("fact", "Kai plays the cello.", 0.5))])
    over = Overflow(api.rt, MERIDIAN, AMARA, [m1], space)
    assert await over.fts('"cello"', 10) == []                         # a listed memory is never a candidate
    assert await Overflow(api.rt, "wld_seedSunnyHollow", AMARA, [], space).fts('"cello"', 10) == []
    assert [r.id for r in (await Overflow(api.rt, MERIDIAN, AMARA, [], space).rows(
        [c.rid for c in await Overflow(api.rt, MERIDIAN, AMARA, [], space).fts('"cello"', 10)])).values()] == [m1]


# ── 7.4 / 7.5 / 7.8 / 7.9: a recall-only turn ──
async def test_a_recall_only_turn_searches_lines_with_no_rewrite_and_is_traced(api: Api) -> None:
    sid = await indexed_session(api)
    recall_yes(api)
    checks_say(api)
    n_rw = len(chats(api, "query_rewrite"))
    [reply] = await send(api, sid, "What did I say about Mia and the walk home?")
    tr = reply["trace"]
    assert tr["graph"]["path"][-1] == "recall" or "recall" in tr["graph"]["path"]
    assert len(chats(api, "query_rewrite")) == n_rw                     # a recall-only turn never rewrites
    assert not [d for d in decisions(api) if any(k.startswith("passage:") for k in d["questions"])]
    [earlier] = rows_of(reply, "earlier")
    assert earlier["result"] == "used" and earlier["answer"] == "yes" and earlier["about"] == AMARA
    recall = rows_of(reply, "recall")
    assert recall and all(r["about"].startswith(("msg_", "mem_")) for r in recall)
    assert sum(r["result"] == "used" for r in recall) <= 3
    ctx = tr.get("contextInSession") or []
    assert ctx and all(c["messageId"].startswith("msg_") for c in ctx)
    tail = str(chats(api, "reply")[-1]["messages"][-1]["content"])
    assert LINES_HEADING in tail
    assert tr["context"]["used"]["history"] > 0


async def test_every_answer_late_keeps_the_top_two_unscored(api: Api) -> None:
    sid = await indexed_session(api)
    recall_yes(api)
    assert api.rt.fake is not None
    held = api.rt.fake.park_questions("recall:", 6)
    await command(api, sid, "send", {"text": "What did I say about Mia and the walk home?"})
    await api.drive(20_000)
    for ev in held:
        ev.set()
    await api.drive(2000)
    from tests.sessions.kit import chars, messages

    reply = chars(await messages(api, sid))[-1]
    recall = rows_of(reply, "recall")
    assert recall and all(r["result"] == "fallback" for r in recall)
    assert sum(r["action"] == "kept by search order" for r in recall) == min(2, len(recall))
    ctx = reply["trace"].get("contextInSession") or []
    assert 0 < len(ctx) <= 2


async def test_without_earlier_lines_or_overflow_nothing_is_asked(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    await send(api, sid, "Hello, how are you?")
    assert not [d for d in decisions(api) if any(k.startswith("earlier:") for k in d["questions"])]


async def test_a_late_earlier_gate_is_no_recall(api: Api) -> None:
    sid = await indexed_session(api)
    [reply] = await send(api, sid, "Anything new?")   # the fake answers `earlier:` no by default
    [row] = rows_of(reply, "earlier")
    assert row["answer"] == "no" and not rows_of(reply, "recall")


# ── both branches ──
async def test_documents_and_recall_run_in_parallel(api: Api) -> None:
    sid = await indexed_session(api)
    gate(api, AMARA, 0.8)
    recall_yes(api)
    checks_say(api)
    assert api.rt.fake is not None
    api.rt.fake.answer_question("passage:*", ANSWERS)
    [reply] = await send(api, sid, "What does the fatigue review say about the walk home after nights?")
    path = reply["trace"]["graph"]["path"]
    assert "recall" in path and "check" in path
    assert rows_of(reply, "passage") and rows_of(reply, "recall")
    tail = str(chats(api, "reply")[-1]["messages"][-1]["content"])
    assert tail.index(LINES_HEADING) > 0   # after the documents block


async def test_stop_during_both_cancels_every_check(api: Api) -> None:
    sid = await indexed_session(api)
    gate(api, AMARA, 0.9)
    recall_yes(api)
    assert api.rt.fake is not None
    held = [*api.rt.fake.park_questions("passage:", 8), *api.rt.fake.park_questions("recall:", 6)]
    api.rt.fake.decision_parked.clear()
    from tests.sessions.kit import chars, messages

    n = len(chars(await messages(api, sid)))
    await command(api, sid, "send", {"text": "What did the review and I say about the walk home after nights?"})
    t = 0
    while not api.rt.fake.decision_parked.is_set() and t < 60_000:
        await api.drive(50)
        t += 50
    await command(api, sid, "stop")
    for ev in held:
        ev.set()
    await api.drive(3000)
    await after_storm(api, sid)
    assert len(chars(await messages(api, sid))) == n                  # no reply
    assert [r for r in await ledger(api) if r["purpose"] == "deep_check" and r["finish_reason"] == "cancelled"]


# ── 7.10 the overflow, and Touch at the next pause ──
async def test_an_overflow_memory_used_is_touched_at_the_next_pause(api: Api) -> None:
    rt = api.rt
    rt.runtime_cfg = dataclasses.replace(rt.runtime_cfg, runtime=dataclasses.replace(
        rt.runtime_cfg.runtime, memory=dataclasses.replace(rt.runtime_cfg.runtime.memory, block_tokens=40)))
    await api.set_key()
    for i in range(8):
        await rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft("fact", f"Filler memory number {i} about tea.",
                                                                   0.9))])
    [cello] = await rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft(
        "fact", "Kai plays the cello every Sunday morning.", 0.3, source_mode="one_on_one"))])
    sid = await agent(api, "one_on_one", [AMARA])
    recall_yes(api)
    checks_say(api)
    [reply] = await send(api, sid, "Do you remember which instrument I play on Sundays? The cello?")
    rec = (reply["trace"].get("memory") or {}).get("recalled") or []
    used = [r for r in rec if r["memoryItemId"] == cello]
    assert used and used[0].get("score") is not None
    tail = str(chats(api, "reply")[-1]["messages"][-1]["content"])
    assert MEMORIES_HEADING in tail and "cello" in tail
    async with rt.db.read() as conn:
        before = (await conn.execute(text("SELECT last_recalled_at FROM memory_items WHERE id = :m"), {"m": cello})
                  ).scalar_one()
    rt.memory_runs.request(sid)
    await rt.memory_runs.drain()
    async with rt.db.read() as conn:
        after = (await conn.execute(text("SELECT last_recalled_at, recall_count FROM memory_items WHERE id = :m"),
                                    {"m": cello})).one()
    assert before is None and after[0] is not None and int(after[1]) == 1




async def test_the_cast_plan_asks_earlier_per_candidate_in_a_group(api: Api) -> None:
    from tests.sessions.test_gates_m12 import MEI, VICTOR

    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    small_windows(api)
    for i in range(4):
        await send(api, sid, LONG.format(i=i))
    await api.drive(2000)
    recall_yes(api, MEI)
    checks_say(api)
    n = len(decisions(api))
    await send(api, sid, "Remember what I said about Mia and the walk home?", mentions=[MEI])
    asked = [k for d in decisions(api)[n:] for k in d["questions"] if k.startswith("earlier:")]
    assert {f"earlier:{c}" for c in (AMARA, MEI, VICTOR)} <= set(asked)
