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


# ── 5.6 and 7.8: the deep path's cancel paths (rag D2) ──
async def _deep_one_on_one(api: Api) -> str:
    from tests.sessions.test_deep_m12 import nouls
    from tests.sessions.test_gates_m12 import AMARA, agent, gate, send

    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    await send(api, sid, "How much worse is fatigue after long shift blocks?")
    return sid


async def _until(api: Api, flag: asyncio.Event, limit_ms: float = 15000) -> None:
    t = 0.0
    while not flag.is_set() and t < limit_ms:
        await api.drive(50)
        t += 50
    assert flag.is_set()


async def _cancelled(api: Api, purpose: str) -> list[dict[str, Any]]:
    from tests.sessions.kit import ledger

    return [r for r in await ledger(api) if r["purpose"] == purpose and r["finish_reason"] == "cancelled"]


async def test_the_rewrite_cut_by_stop(api: Api) -> None:
    from tests.helpers.storm import after_storm
    from tests.sessions.kit import chars, command, messages

    sid = await _deep_one_on_one(api)
    release = park_next_chat(api.rt, "query_rewrite")
    n = len(chars(await messages(api, sid)))
    await command(api, sid, "send", {"text": "and nights?"})
    assert api.rt.fake is not None
    await _until(api, api.rt.fake.chat_parked)
    await command(api, sid, "stop")
    release.set()
    await api.drive(20000)
    await after_storm(api, sid)
    assert len(chars(await messages(api, sid))) == n            # no reply was written


async def test_the_rewrite_cut_by_a_new_group_message(api: Api) -> None:
    """In group a newer user message supersedes the first reply's deep work (G5); in 1:1 a message queues behind the
    reply instead, so Stop is 1:1's cut."""
    from tests.helpers.storm import after_storm
    from tests.sessions.kit import chars, command, messages
    from tests.sessions.test_deep_m12 import nouls
    from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, agent, gate

    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    assert api.rt.fake is not None
    api.rt.fake.answer_question("who_first", {"type": "choice", "choice": AMARA, "confidence": 0.9,
                                              "probabilities": {AMARA: 0.9}})
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    release = park_next_chat(api.rt, "query_rewrite")
    await command(api, sid, "send", {"text": "and nights?"})
    await _until(api, api.rt.fake.chat_parked)
    await command(api, sid, "send", {"text": "Actually, never mind."})
    release.set()
    await api.drive(25000)
    await after_storm(api, sid)
    first = [m for m in chars(await messages(api, sid))
             if m["seq"] < next(u["seq"] for u in await messages(api, sid)
                                if u["author"]["type"] == "user" and "never mind" in u["content"])]
    assert not first                                            # the superseded reply was never written


async def test_the_embedding_wait_cut_by_stop(api: Api) -> None:
    from tests.helpers.storm import after_storm
    from tests.sessions.kit import chars, command, messages
    from tests.sessions.test_deep_m12 import _indexed_source
    from tests.sessions.test_gates_m12 import HANA, SUNNY, agent, gate

    await api.set_key()
    await _indexed_source(api, HANA)
    sid = await agent(api, "one_on_one", [HANA], world=SUNNY)
    gate(api, HANA, 0.8)
    fake = api.rt.fake
    assert fake is not None
    release = fake.park_embedding(fake.counts["embeddings"] + 1)
    n = len(chars(await messages(api, sid)))
    await command(api, sid, "send", {"text": "How long should the rice soak?"})
    await _until(api, fake.embed_parked)
    await command(api, sid, "stop")
    release.set()
    await api.drive(5000)
    await after_storm(api, sid)
    assert len(chars(await messages(api, sid))) == n


async def test_the_rewrite_store_cut_mid_transaction(api: Api) -> None:
    from horizon.services.ai_meta import store_rewrite
    from tests.helpers.storm import storm_during_write
    from tests.sessions.kit import messages

    sid = await _deep_one_on_one(api)
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")

    async def write() -> None:
        await store_rewrite(api.rt, user["id"], "chr_seedAmara", "night shift fatigue")

    cut = await storm_during_write(api, sid, write, storms=15)
    assert 0 <= cut <= 15


@pytest.mark.parametrize("mode", ["one_on_one", "group", "watch", "debate"])
async def test_the_checks_cut_by_stop_in_each_mode(api: Api, mode: str) -> None:
    """The deep_check requests (and the set check) held, then Stop: no reply waits on them, every held request is
    recorded `cancelled`, and the writer is free (D2)."""
    from tests.helpers.storm import after_storm
    from tests.sessions.kit import command
    from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, agent, gate

    fake = api.rt.fake
    for cid in (AMARA, MEI, VICTOR):
        gate(api, cid, 0.9)
    if mode == "watch":
        from tests.sessions.test_watch_plan import agent_watch

        sid = await agent_watch(api, maxTurns=10, paceMs=1500)
        assert api.rt.fake is not None
        api.rt.fake.set_canned("reply", [{"content": "The four-day week pilots and long shift blocks, again."}])
    elif mode == "debate":
        from tests.sessions.test_debate_plan import debate

        sid = await debate(api, motion="Long shift blocks harm patient safety")
    else:
        sid = await agent(api, mode, [AMARA] if mode == "one_on_one" else [AMARA, MEI, VICTOR])
    assert api.rt.fake is not None
    held = api.rt.fake.park_questions("passage:", 8)
    if mode in ("one_on_one", "group"):
        await command(api, sid, "send", {"text": "What did the four-day week pilots and the fatigue review find?"})
    await _until(api, api.rt.fake.decision_parked, 60000)
    await command(api, sid, "stop")
    for ev in held:
        ev.set()
    await api.drive(3000)
    await after_storm(api, sid)
    assert await _cancelled(api, "deep_check")
    assert fake is not None


async def test_the_checks_cut_by_a_superseding_message(api: Api) -> None:
    from tests.helpers.storm import after_storm
    from tests.sessions.kit import command
    from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, agent, gate

    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    for cid in (AMARA, MEI, VICTOR):
        gate(api, cid, 0.9)
    assert api.rt.fake is not None
    held = api.rt.fake.park_questions("passage:", 8)
    await command(api, sid, "send", {"text": "What did the four-day week pilots and the fatigue review find?"})
    await _until(api, api.rt.fake.decision_parked)
    await command(api, sid, "send", {"text": "Never mind that."})
    for ev in held:
        ev.set()
    await api.drive(25000)
    await after_storm(api, sid)
