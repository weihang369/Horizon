"""The rolling summary's task (conversation-context "The window is cut after the reply", "One summary writer per
session", "Summary failures are bounded", "Forks start their summary at creation", "Summary spend"; session-runtime
"The summary check follows each turn"; persona-context D8–D13; tasks 4.4–4.8). Virtual clock, no network."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Sequence
from typing import Any

import pytest

from horizon.ai.contexts import SessionContext
from horizon.ai.naive import summary as naive_summary
from horizon.db import tables as t
from horizon.domain import vclock
from horizon.domain.runtime_config import WindowSizes
from horizon.gateway.errors import ProviderError
from horizon.gateway.fake import load_canned
from horizon.sessions import summary as summary_mod
from horizon.sessions.summary import fallback_summary, summary_task
from tests.conftest import Api
from tests.sessions.kit import API, command, create, ledger, messages
from tests.sessions.test_naive import chat_bodies

LONG = "Question number {i}: what about sleep, rotas, coffee and the long walk home after a night shift?"


class Held:
    """A summariser whose calls wait for `release`, so a test can act while one is in flight."""

    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.release = asyncio.Event()
        self.fail = fail

    async def episode(self, ctx: SessionContext) -> str:
        return "episode"

    async def rolling(self, ctx: SessionContext, previous: str | None, lines: Sequence[str]) -> str:
        self.calls += 1
        if self.fail:
            raise ProviderError("provider_error", "down")
        holder = vclock.current_holder()   # like a parked provider call: virtual time may advance meanwhile
        if holder is not None:
            holder.drop()
        try:
            await self.release.wait()
        finally:
            if holder is not None:
                holder.hold()
        return f"notes {self.calls}"


def small_windows(api: Api, n: int = 60) -> None:
    rt = api.rt
    rt.runtime_cfg = dataclasses.replace(rt.runtime_cfg, runtime=dataclasses.replace(
        rt.runtime_cfg.runtime, window_tokens=WindowSizes(n, n, n, n)))


async def chat(api: Api, profile: str = "scripted") -> str:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": profile})).status_code == 204
    sid: str = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    return sid


async def rolling_rows(api: Api, sid: str) -> list[dict[str, Any]]:
    async with api.rt.db.read() as conn:
        rows = (await conn.execute(t.session_summaries.select().where(t.session_summaries.c.session_id == sid)
                                   .order_by(t.session_summaries.c.id))).mappings().all()
    return [dict(r) for r in rows]


async def send(api: Api, sid: str, n: int, start: int = 0) -> None:
    for i in range(start, start + n):
        await command(api, sid, "send", {"text": LONG.format(i=i)})
        await api.drive(12000)


# ── 4.6 ──
async def test_summary_runs_after_turn_end_and_is_written_once(api: Api) -> None:
    sid = await chat(api)
    small_windows(api)
    held = Held()
    api.rt.ai.override("summariser", held)
    await send(api, sid, 2)
    assert held.calls == 1 and not await rolling_rows(api, sid)   # in flight: the turn didn't wait for it
    await send(api, sid, 2, start=2)                                # more turns end: single flight, no second call
    assert held.calls == 1
    held.release.set()
    await api.drive(1000)
    rows = await rolling_rows(api, sid)
    assert [r["text"] for r in rows] == ["notes 1"] and rows[0]["kind"] == "rolling"


async def test_stop_during_a_summary_still_writes_it(api: Api) -> None:
    sid = await chat(api)
    small_windows(api)
    held = Held()
    api.rt.ai.override("summariser", held)
    await send(api, sid, 2)
    assert held.calls == 1
    await command(api, sid, "stop")
    held.release.set()
    await api.drive(1000)
    assert [r["text"] for r in await rolling_rows(api, sid)] == ["notes 1"]


async def test_actor_stop_cancels_and_writes_nothing(api: Api) -> None:
    sid = await chat(api)
    small_windows(api)
    held = Held()
    api.rt.ai.override("summariser", held)
    await send(api, sid, 2)
    actor = await api.rt.sessions.get(sid)
    task = summary_task(actor)
    assert task.running
    await actor.stop()
    held.release.set()
    await api.drive(1000)
    assert not await rolling_rows(api, sid) and task.task is not None and task.task.cancelled()


async def test_two_failures_write_the_fallback_with_at_most_two_calls(api: Api, monkeypatch: Any) -> None:
    monkeypatch.setattr(summary_mod, "RETRY_GROWTH", 10**6)
    sid = await chat(api)
    small_windows(api)
    held = Held(fail=True)
    api.rt.ai.override("summariser", held)
    await send(api, sid, 4)
    assert held.calls == 1 and not await rolling_rows(api, sid)   # failed once; no retry until the window grows
    monkeypatch.setattr(summary_mod, "RETRY_GROWTH", 30)
    await send(api, sid, 1, start=4)                               # grew enough: the second, last attempt
    assert held.calls == 2
    rows = await rolling_rows(api, sid)
    assert len(rows) == 1 and "Question number" in rows[0]["text"]   # the free fallback: the last dropped lines


def test_fallback_keeps_the_newest_and_fits() -> None:
    old = "\n".join(f"old note {i} " + "x" * 300 for i in range(20))
    lines = [f"Kai: line {i}" for i in range(30)]
    out = fallback_summary(old, lines)
    assert out.endswith("Kai: line 29") and "Kai: line 18" in out and "Kai: line 17" not in out
    assert len(out.encode()) <= 1800 and "old note 0 " not in out


# ── 4.4, 4.5, 4.8: the summariser and its spend ──
async def test_naive_summary_call_is_summary_spend_with_the_canned_text(api: Api) -> None:
    sid = await chat(api, profile="naive")
    small_windows(api)
    assert api.rt.fake is not None
    purpose, items = load_canned("rolling-summaries")
    api.rt.fake.set_canned(purpose, items)
    await send(api, sid, 3)
    await api.drive(2000)
    rows = [r for r in await ledger(api) if r["purpose"] == "rolling_summary"]
    assert rows and rows[0]["category"] == "summary" and rows[0]["message_id"] is None
    body = next(b for b in chat_bodies(api) if "running notes" in b["messages"][0]["content"])
    assert body["max_tokens"] == 600 and body["temperature"] == 0.7 and body["reasoning"] == {"enabled": False}
    assert "Report requests as what someone asked" in body["messages"][0]["content"]
    assert "Kai: Question number 0" in body["messages"][1]["content"]
    first = items[0]["content"] if isinstance(items[0], dict) else items[0]
    assert (await rolling_rows(api, sid))[0]["text"] == naive_summary.cut_summary(str(first))
    assert all(r["character_id"] is None for r in rows)   # summary spend: no character is charged (OQ-AI-17)


async def test_scripted_drop_bills_a_simulated_rolling_summary(api: Api) -> None:
    sid = await chat(api)
    small_windows(api)
    await send(api, sid, 3)
    await api.drive(2000)
    rows = [r for r in await ledger(api) if r["purpose"] == "rolling_summary"]
    assert rows and rows[0]["provider"] == "scripted" and rows[0]["category"] == "summary"
    assert (await rolling_rows(api, sid))


def test_chunks_and_the_cut() -> None:
    lines = ["a" * 300] * 130                       # 100 tokens each
    parts = naive_summary.chunks(lines)
    assert len(parts) == 3 and all(sum(len(x) + 1 for x in p) <= 18000 for p in parts)
    cut = naive_summary.cut_summary("One fact here. " * 200)
    assert cut.endswith("here.") and len(cut.encode()) <= 1800


# ── 4.3 and 4.7 ──
async def test_ceiling_bounds_every_turn_and_a_fork_starts_its_summary(api: Api) -> None:
    sid = await chat(api)
    small_windows(api)
    held = Held(fail=True)
    api.rt.ai.override("summariser", held)
    await send(api, sid, 4)
    from horizon.domain.pricing import count_tokens
    from horizon.sessions.context import session_context
    actor = await api.rt.sessions.get(sid)
    sctx = await session_context(api.rt, actor)
    assert sum(count_tokens(m.content) for m in sctx.recent) <= 120 or len(sctx.recent) == 2
    held2 = Held()
    api.rt.ai.override("summariser", held2)
    await command(api, sid, "leave", status=204)
    r = await api.post(f"{API}/sessions/{sid}/fork", {})
    assert r.status_code in (200, 201), r.text
    fork = r.json()["session"]["id"]
    await api.drive(100)
    assert held2.calls == 1                        # no user message yet
    held2.release.set()
    await api.drive(500)
    assert [x["text"] for x in await rolling_rows(api, fork)] == ["notes 1"]


@pytest.mark.parametrize("n", [1])
async def test_messages_are_never_deleted_by_the_window(api: Api, n: int) -> None:
    sid = await chat(api)
    small_windows(api)
    await send(api, sid, 4)
    assert len([m for m in await messages(api, sid) if m["author"]["type"] == "user"]) == 4 * n
    assert json.dumps(await messages(api, sid))
