"""The memory list in system message 1 and the greeting (memory design D22–D25; persona-prompt "The memory list",
"Second chat"; long-term-memory "The list is frozen per sitting")."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from horizon.ai.agent.budget import planned_input
from horizon.ai.agent.persona import MEMORY_HEADER
from horizon.ai.ports import Insert, MemoryDraft
from horizon.domain.runtime_config import MemoryKnobs
from horizon.services.memory import block as blk
from horizon.services.memory.block import MemoryRow, fill, one_line, rank
from tests.conftest import Api
from tests.sessions.kit import API, chars, create, messages
from tests.sessions.test_deep_m12 import chats
from tests.sessions.test_gates_m12 import agent, send

AMARA, MERIDIAN = "chr_seedAmara", "wld_seedMeridian"
NOW = datetime(2026, 10, 16, tzinfo=UTC)
KNOBS = MemoryKnobs()


def _row(i: str, importance: float, *, days: float = 0, mode: str | None = "one_on_one", text_: str = "",
         recalled_days: float | None = None) -> MemoryRow:
    at = (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    rec = (NOW - timedelta(days=recalled_days)).isoformat().replace("+00:00", "Z") if recalled_days is not None else None
    return MemoryRow(id=i, kind="fact", text=text_ or f"memory {i}", importance=importance, source_mode=mode,
                     created_at=at, last_recalled_at=rec)


# ── 5.1 the block reader ──
def test_ranking_is_importance_times_recency_times_mode_weight() -> None:
    rows = [_row("a", 0.9, days=60), _row("b", 0.6), _row("c", 0.9, mode="watch"), _row("d", 0.9, days=60,
                                                                                         recalled_days=0)]
    got = [r.id for r in rank(rows, NOW, KNOBS)]
    # d (0.9, recalled today) > c (0.9 × 0.7) > b (0.6) > a (0.9 × 0.25 → floored 0.5 = 0.45)
    assert got == ["d", "c", "b", "a"]


def test_old_memories_sink_to_the_floor_but_never_vanish() -> None:
    assert blk.recency(_row("x", 1.0, days=3650), NOW, KNOBS) == KNOBS.recency_floor


def test_ties_go_to_the_newer_then_the_id() -> None:
    knobs = MemoryKnobs(half_life_days=1e9)   # recency ≈ 1, so only importance and mode count
    rows = [_row("a", 0.5, days=1), _row("b", 0.5, days=1), _row("c", 0.5, days=0)]
    assert [r.id for r in rank(rows, NOW, knobs)] == ["c", "b", "a"]


def test_the_budget_stops_at_block_tokens_and_lines_are_collapsed_and_cut() -> None:
    long = " ".join(f"w{i}" for i in range(60))
    rows = [_row(f"m{i}", 0.9 - i / 1000, text_=f"line {i}\nwith a break " + long) for i in range(100)]
    got = fill(rank(rows, NOW, KNOBS), 1000)
    used = sum(blk.count_tokens(f"- {m.text}\n") for m in got)
    assert 0 < len(got) < 100 and used <= 1000
    assert all("\n" not in m.text and m.text.endswith(" …") and len(m.text.split()) == 41 for m in got)
    assert [m.label for m in got[:3]] == ["m1", "m2", "m3"]
    assert one_line("a\n\n# heading\tb") == "a # heading b"


def test_the_planned_budget_follows_block_tokens() -> None:
    assert planned_input("one_on_one") == 11680 and planned_input("one_on_one", block_tokens=500) == 11180


# ── 5.2–5.4 the block in a live agent session ──
def _system1(api: Api) -> list[str]:
    return [str(r["messages"][0]["content"]) for r in chats(api, "reply")]


async def _plant(api: Api, text_: str, importance: float = 0.9) -> str:
    [mid] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft("fact", text_, importance,
                                                                           source_mode="one_on_one"))])
    return mid


async def test_the_block_is_frozen_per_sitting_and_a_forget_refreshes_it_once(api: Api) -> None:
    await api.set_key()
    m1 = await _plant(api, "Kai quit coffee last month.")
    await _plant(api, "Kai's favourite cake is yuzu.")
    sid = await agent(api, "one_on_one", [AMARA])
    for i in range(5):
        await send(api, sid, f"Tell me about your shift, part {i}.")
    first = _system1(api)
    assert len(first) >= 5 and len(set(first[-5:])) == 1
    assert MEMORY_HEADER in first[-1] and "- Kai quit coffee last month." in first[-1]
    assert (await api.client.delete(f"{API}/memory/{m1}")).status_code == 204
    await send(api, sid, "And today?")
    await send(api, sid, "And tomorrow?")
    after = _system1(api)
    assert "Kai quit coffee last month." not in after[-2] and "Kai's favourite cake is yuzu." in after[-2]
    assert after[-1] == after[-2]


async def test_the_reply_trace_lists_the_block_without_scores_and_forget_scrubs_it(api: Api) -> None:
    await api.set_key()
    m1 = await _plant(api, "Kai's sister Mia works nights in Ipoh.")
    sid = await agent(api, "one_on_one", [AMARA])
    [reply] = await send(api, sid, "How are you?")
    recalled = (reply["trace"].get("memory") or {}).get("recalled") or []
    mine = [r for r in recalled if r["memoryItemId"] == m1]
    assert mine == [{"memoryItemId": m1, "text": "Kai's sister Mia works nights in Ipoh.", "via": "block"}]   # U-58
    used = reply["trace"]["context"]["used"]
    assert used["memory"] > 0
    async with api.rt.db.read() as conn:
        refs = (await conn.execute(text("SELECT count(*) FROM trace_memory_refs WHERE memory_item_id = :m"),
                                   {"m": m1})).scalar_one()
    assert refs == 1
    assert (await api.client.delete(f"{API}/memory/{m1}")).status_code == 204
    stored = next(m for m in await messages(api, sid) if m["id"] == reply["id"])
    assert "Mia works nights" not in str(stored["trace"])


async def test_a_commit_in_one_tab_refreshes_the_other_tabs_block(api: Api) -> None:
    await api.set_key()
    sid = await agent(api, "one_on_one", [AMARA])
    await send(api, sid, "Hello.")
    actor = api.rt.sessions.peek(sid)
    assert actor is not None and AMARA in actor.memory_blocks
    api.rt.memory_runs.after_commit(MERIDIAN, [AMARA])
    await api.drive(10)
    assert AMARA not in actor.memory_blocks and actor.memory_gen[AMARA] == 1


async def test_naive_replies_get_no_block(api: Api) -> None:
    await api.set_key()
    await _plant(api, "Kai quit coffee last month.")
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await send(api, sid, "Hi.")
    assert all(MEMORY_HEADER not in s for s in _system1(api))


# ── 5.5 the greeting ──
async def test_a_second_chats_greeting_mentions_last_time_and_the_first_is_unchanged(api: Api) -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    first = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    [greet] = chars(await messages(api, first))
    stored = (await api.json(f"{API}/characters/{AMARA}"))["profile"]["greeting"]
    assert greet["content"] == stored                                  # P9: word for word, even with memories
    await send(api, first, "My finals start Monday.")
    for i, t in enumerate(["Kai's finals start Monday.", "Kai is off coffee.", "Kai likes yuzu cake."]):
        await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft(
            "fact", t, 0.7, source_session_id=first, source_mode="one_on_one"))])
        await api.drive(1000 * (i + 1))
    n = len(chats(api, "reply"))
    second = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    req = chats(api, "reply")[n]
    tail = str(req["messages"][-1]["content"])
    assert "If something from last time fits, you may mention it in a short phrase." in tail
    assert "- Kai likes yuzu cake." in tail and "- Kai is off coffee." in tail and "finals" not in tail
    assert chars(await messages(api, second))


# ── 5.6 the refresh storm ──
async def test_a_drop_during_the_read_is_never_cached(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    m1 = await _plant(api, "Kai quit coffee last month.")
    sid = await agent(api, "one_on_one", [AMARA])
    actor = api.rt.sessions.peek(sid)
    assert actor is not None
    actor.memory_blocks.pop(AMARA, None)
    real = blk.memory_list
    calls: list[int] = []
    gate_ = asyncio.Event()

    async def slow(*a: Any, **kw: Any) -> Any:
        calls.append(1)
        out = await real(*a, **kw)
        if len(calls) == 1:
            await gate_.wait()
        return out

    monkeypatch.setattr(blk, "memory_list", slow)
    from horizon.sessions.context import characters, speaker_view

    crow = (await characters(api.rt, [AMARA]))[AMARA]
    task = asyncio.ensure_future(speaker_view(api.rt, actor, crow))
    for _ in range(50):
        await asyncio.sleep(0)
        if calls:
            break
    async with api.rt.db.write() as tx:   # the Forget lands while the view is half-built
        await tx.conn.execute(text("UPDATE memory_items SET superseded_by = 'x' WHERE id = :m"), {"m": m1})
    from horizon.services.memory.forget import drop_blocks

    drop_blocks(api.rt, [AMARA])
    await api.drive(10)
    gate_.set()
    view = await task
    assert len(calls) == 2 and all(m.id != m1 for m in view.memories)
    assert all(m.id != m1 for m in actor.memory_blocks[AMARA])
