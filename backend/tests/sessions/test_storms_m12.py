"""Cancel storms on the paths M12 adds (rag design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed twice: while it writes (`storm_during_write`) and while it waits on a parked Jev or
DeepSeek call (`storm_during_call`). Afterwards the writer is free, the clock settles and the log reduces. Phase 0
proves the holding shapes a deep turn needs: several Jev requests held at once and released in any order, a request
refused with a 429, and a held chat response."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import pytest

from horizon.ai.decider import DecisionUnavailable, Noul, Score
from horizon.gateway.chat import ChatRequest
from horizon.gateway.context import call_ctx
from tests.conftest import Api
from tests.helpers.storm import park_next_chat
from tests.sessions.kit import ledger

LEVELS = ("Doesn't help.", "Partly.", "Answers it.")


def _passage(n: int) -> dict[str, Any]:
    return {f"passage:kch_{n:02d}": Score(instructions="How much does the passage help?", levels=LEVELS)}


async def test_eight_held_decisions_release_in_any_order(api: Api) -> None:
    """Task 0.2: a deep turn's 8 `deep_check` requests, each held on its own event, settle whatever order they are
    released in, on the virtual clock; a read with a deadline falls back for the ones still held."""
    await api.set_key()
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_questions("passage:", 8)
    d = api.rt.decider
    ctx = call_ctx("deep_check", category="decision", world_id="wld_seedMeridian")
    calls = [d.start({}, _passage(i), ctx, purpose="deep_check") for i in range(8)]
    await api.drive(50)
    assert fake.counts["decisions"] == 8 and fake.decision_parked.is_set()
    order = list(range(8))
    random.Random(12).shuffle(order)
    for i in order[:5]:
        held[i].set()
    await api.drive(50)
    assert [c.landed for c in calls].count(True) == 5
    late = [c for i, c in enumerate(calls) if i in order[5:]]
    reads = [asyncio.ensure_future(c.by(d.now())) for c in late]
    for i in order[5:]:
        held[i].set()
    await api.drive(50)
    assert all(c.landed for c in calls)
    for r in reads:
        assert r.done()
    rows = [r for r in await ledger(api) if r["purpose"] == "deep_check"]
    assert len(rows) == 8


async def test_set_answers_and_a_refused_request(api: Api) -> None:
    """Task 0.2: a question key (or a `prefix*`) gets a set answer, and the next request asking a prefix is refused
    with HTTP 429 once, so Jev call 2's "one 429" case can be built."""
    await api.set_key()
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("passage:kch_01", {"type": "score", "score": 2.0, "confidence": 0.9,
                                            "probabilities": {"0": 0.05, "1": 0.05, "2": 0.9}})
    fake.answer_question("docs:*", {"type": "noul", "noul": 0.8})
    fake.refuse_question("passage:kch_02")
    d = api.rt.decider
    ctx = call_ctx("deep_check", category="decision", world_id="wld_seedMeridian")
    a1 = d.start({}, _passage(1), ctx, purpose="deep_check")
    a2 = d.start({}, _passage(2), ctx, purpose="deep_check")
    a3 = d.start({}, _passage(2), ctx, purpose="deep_check")   # the refusal is spent: answered as usual
    await api.drive(50)
    r1 = await a1.final()
    assert r1.answers["passage:kch_01"].score == 2.0  # type: ignore[union-attr]
    with pytest.raises(DecisionUnavailable, match="rate_limited"):
        await a2.final()
    r3 = await a3.final()
    assert r3.answers["passage:kch_02"].score == 1.0  # type: ignore[union-attr]
    gctx = call_ctx("turn_plan", world_id="wld_seedMeridian")
    g = d.start({}, {"docs:chr_seedAmara": Noul(instructions="Needs documents?", true="Yes.", false="No.")}, gctx,
                purpose="turn_plan")
    await api.drive(50)
    assert (await g.final()).answers["docs:chr_seedAmara"].p == 0.8  # type: ignore[union-attr]


async def test_a_held_chat_response_settles_on_release(api: Api) -> None:
    """Task 0.2: a chat call held by purpose (the rewrite's shape) stays out until released, while virtual time runs
    past any deadline, then lands with its ledger row."""
    await api.set_key()
    release = park_next_chat(api.rt, "query_rewrite")
    gw = api.rt.gateway
    ctx = call_ctx("query_rewrite", category="chat", world_id="wld_seedMeridian")
    req = ChatRequest(model="deepseek/deepseek-v3.2", messages=[{"role": "user", "content": "hi"}], max_tokens=60)
    task = asyncio.ensure_future(gw.chat_complete(req, ctx))
    await api.drive(3000)
    assert api.rt.fake is not None and api.rt.fake.chat_parked.is_set()
    assert not task.done()
    release.set()
    await api.drive(100)
    await task
    assert [r for r in await ledger(api) if r["purpose"] == "query_rewrite"]
