"""System 1 rows on the trace (contract rev 1.4 `TurnTrace.system1`; system1-trace spec; docs/ai/13 W1 and §3 checks
2–3; ai-foundation design D24, D25; tasks 5.3–5.6)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from horizon.contract.validate import default_schema
from horizon.sessions.system1 import cut, merge_rows, route_row
from horizon.sessions.turn import merge_patch
from tests.conftest import Api
from tests.knowledge.test_naive_prompt import AMARA, TwoMemories, _naive_turn
from tests.sessions.kit import API, chars, command, create, events, messages

FACE = {"purpose": "face_check", "id": "face", "version": 1, "label": "face fits?", "answer": "yes", "p": 0.9,
        "compared": [{"name": "p_yes", "value": 0.9, "threshold": 0.6}], "result": "used", "action": "kept"}


def row(i: int, result: str = "used", **kw: Any) -> dict[str, Any]:
    return {"purpose": "deep_check", "id": f"q{i}", "version": 1, "label": "x?", "answer": "yes", "p": 0.5,
            "compared": [], "result": result, **kw}


async def stored(api: Api, mid: str) -> tuple[dict[str, Any], tuple[Any, ...]]:
    async with api.rt.db.read() as conn:
        r = (await conn.execute(text("SELECT trace, engine, engine_version, prompt_version, created_at FROM turn_traces "
                                     "WHERE message_id = :m"), {"m": mid})).one()
    trace = r[0] if isinstance(r[0], dict) else json.loads(r[0])
    return trace, tuple(r[1:])


def insights(evs: list[dict[str, Any]], mid: str) -> list[dict[str, Any]]:
    return [e for e in evs if e["type"] == "insight" and e["payload"]["messageId"] == mid]


def check_schema(trace: dict[str, Any]) -> None:
    errors = default_schema().errors("TurnTrace", trace)
    assert errors == [], errors


# ── 5.3: the runtime owns the section; a meta-less insight keeps the engine columns ──
def test_engine_patch_with_system1_is_dropped() -> None:
    out = merge_patch({"system1": {"questions": [FACE]}}, {"system1": {"questions": []}, "context": {"budget": 10}})
    assert out["system1"] == {"questions": [FACE]} and out["context"] == {"budget": 10}


async def test_append_keeps_the_engine_metadata_and_creation_time(api: Api) -> None:
    reply = await _naive_turn(api, ["<e:happy>Hello."], "Hi there")
    _, before = await stored(api, reply["id"])
    assert before[:3] == ("naive", "3", "naive-5")
    actor = api.rt.sessions.peek(reply["sessionId"])
    assert actor is not None
    call = {"purpose": "face_check", "model": "typesafe/jev-1.13", "costUsd": 1e-05, "latencyMs": 200}
    assert await actor.append_system1(reply["id"], None, [FACE], [call]) is True
    trace, after = await stored(api, reply["id"])
    assert after == before                               # engine, versions and created_at all kept
    assert trace["system1"]["questions"] == [FACE] and trace["calls"][-1] == call
    check_schema(trace)
    evs = insights(await events(api, reply["sessionId"]), reply["id"])
    assert len(evs) == 2 and evs[-1]["payload"]["trace"] == trace


# ── 5.4: merge, cut and the three guards ──
def test_merge_by_key_keeps_order_and_takes_the_later_row() -> None:
    a, b = row(1), row(2)
    assert merge_rows([a, b], [{**a, "answer": "no"}]) == [{**a, "answer": "no"}, b]
    assert len(merge_rows([row(1, about="chr_a")], [row(1, about="chr_b")])) == 2


def test_seventy_rows_cut_to_64_not_used_first() -> None:
    rows = [row(i, "not_used" if i % 7 == 0 else "used") for i in range(70)]   # 10 not_used (0, 7, …, 63)
    out = cut(rows)
    assert len(out) == 64 and sum(r["result"] == "not_used" for r in out) == 4
    assert [r["id"] for r in out if r["result"] == "not_used"] == ["q0", "q7", "q14", "q21"]   # latest dropped first


async def test_append_after_regenerate_writes_nothing(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Quick question about sleep."})
    await api.drive(12000)
    reply = chars(await messages(api, sid))[-1]
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(12000)
    before = await events(api, sid)
    trace_before, _ = await stored(api, reply["id"])
    actor = api.rt.sessions.peek(sid)
    assert actor is not None
    assert await actor.append_system1(reply["id"], None, [FACE], []) is False   # rows were for the first variant
    assert len(await events(api, sid)) == len(before)
    assert (await stored(api, reply["id"]))[0] == trace_before


async def test_append_queued_before_a_forget_commit_restores_nothing(api: Api) -> None:
    api.rt.ai.override("memory_retriever", TwoMemories())
    from horizon.ai.ports import Insert, MemoryDraft

    await api.rt.memory.apply(AMARA, "wld_seedMeridian", [Insert(MemoryDraft("fact", "Kai prefers green tea now.", 0.6))])
    reply = await _naive_turn(api, ["<e:neutral>I remember."], "Do you remember our talk?")
    recalled = reply["trace"]["memory"]["recalled"]
    gone = next(m for m in recalled if "green tea" in m["text"])
    # Forget commits (its transaction only): the actor's in-memory trace still holds the text, as it would for an
    # append that was queued before the commit and runs before the actor's scrub.
    from horizon.services.memory.forget import forget_chain

    async with api.rt.db.write() as tx:
        await forget_chain(api.rt, tx.conn, character_id=AMARA, world_id="wld_seedMeridian", chain={gone["memoryItemId"]})
    actor = api.rt.sessions.peek(reply["sessionId"])
    assert actor is not None
    actor.state["messages"][reply["id"]]["trace"]["memory"]["recalled"] = recalled   # the pre-Forget copy
    about = {**FACE, "purpose": "deep_check", "id": "memory_use", "about": gone["memoryItemId"]}
    assert await actor.append_system1(reply["id"], None, [about, FACE], []) is True
    trace, _ = await stored(api, reply["id"])
    assert all(m["memoryItemId"] != gone["memoryItemId"] for m in trace["memory"]["recalled"])
    assert "green tea" not in json.dumps(trace)
    assert [r["id"] for r in trace["system1"]["questions"]] == ["face"]
    last = insights(await events(api, reply["sessionId"]), reply["id"])[-1]["payload"]["trace"]
    assert last == trace
    async with api.rt.db.read() as conn:
        refs = set((await conn.execute(text("SELECT memory_item_id FROM trace_memory_refs WHERE message_id = :m"),
                                       {"m": reply["id"]})).scalars())
    assert gone["memoryItemId"] not in refs


async def test_append_during_streaming_lands_in_the_final_insight_only(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Tell me about sleep and night shifts, in detail."})
    actor = api.rt.sessions.peek(sid)
    assert actor is not None
    for _ in range(80):
        await api.drive(100)
        if actor.current is not None and actor.current.started and not actor.current.closed:
            break
    info = actor.current
    assert info is not None and not info.closed
    assert await actor.append_system1(info.message_id, info.variant_id, [FACE], []) is True
    assert insights(await events(api, sid), info.message_id) == []      # nothing emitted mid-stream
    await api.drive(20000)
    evs = insights(await events(api, sid), info.message_id)
    # the finish insight carries the row (beside M9's scripted emotion row); a later one can only be the face check's
    assert FACE in evs[0]["payload"]["trace"]["system1"]["questions"]
    assert all(q["purpose"] == "face_check" for e in evs[1:] for q in e["payload"]["trace"]["system1"]["questions"]
               if q not in evs[0]["payload"]["trace"]["system1"]["questions"])


def route_rows(m: dict[str, Any]) -> list[dict[str, Any]]:
    """The route rows only: M9's scripted face check can add its own row after a non-neutral reply."""
    return [q for q in m["trace"]["system1"]["questions"] if q["purpose"] == "route"]


# ── 5.5: naive route rows ──
async def _naive_router_group(api: Api, cast: list[str]) -> str:
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"router": "naive"}})
    assert r.status_code == 204
    sid: str = (await create(api, "group", cast, world="wld_seedSunnyHollow"))["session"]["id"]
    await api.drive(6000)
    return sid


async def test_one_decision_two_replies_share_the_route_row(api: Api) -> None:
    sid = await _naive_router_group(api, ["chr_seedHana", "chr_seedRin", "chr_seedTakeshi"])
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    await command(api, sid, "send", {"text": "Who's cooking tonight?"})
    await api.drive(40000)
    replies = chars(await messages(api, sid))
    assert len(replies) >= 2
    rows = [route_rows(m) for m in replies]
    assert all(r == rows[0] for r in rows) and len(rows[0]) == 1
    (r,) = rows[0]
    assert r["purpose"] == "route" and r["id"] == "route" and r["version"] == 2 and r["label"] == "who replies?"
    assert r["result"] == "used" and 0 <= r["p"] <= 1 and r["answer"] in {*(m["author"]["characterId"] for m in replies), "none"}
    for m in replies:
        check_schema(m["trace"])


async def test_parked_route_gives_a_fallback_row(api: Api) -> None:
    sid = await _naive_router_group(api, ["chr_seedHana", "chr_seedTakeshi"])
    assert (await api.post(f"{API}/_test/park", {"endpoint": "decisions", "n": 1})).status_code == 204
    await command(api, sid, "send", {"text": "Who's cooking?"})
    await api.drive(30000)
    reply = chars(await messages(api, sid))[0]
    (r,) = route_rows(reply)
    assert r["result"] == "fallback" and "p" not in r and r["answer"] == reply["author"]["characterId"]
    check_schema(reply["trace"])
    assert (await api.post(f"{API}/_test/park", {"endpoint": "decisions", "n": 1, "release": True})).status_code == 204
    await api.drive(1000)


def test_route_row_shape() -> None:
    fb = route_row(version=2, label="who replies?", answer="none", p=0.4, confidence=0.4, fallback=True, action="x")
    assert "p" not in fb and "confidence" not in fb and fb["result"] == "fallback"


# ── 5.6: scripted route rows come from the shared fixture ──
async def test_scripted_group_turn_has_a_fixture_route_row(api: Api) -> None:
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted"})
    assert r.status_code == 204
    sid = (await create(api, "group", ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Mei, is it worth it?"})
    await api.drive(30000)
    replies = chars(await messages(api, sid))
    assert replies
    fixture = json.loads((api.rt.cfg.seed_dir / "system1.fixture.json").read_text(encoding="utf-8"))["data"]["rows"]["route"]
    for m in replies:
        (row_,) = route_rows(m)
        assert {k: row_[k] for k in fixture} == fixture
        assert row_["answer"] == m["trace"]["routing"]["candidates"][0]["characterId"]
        check_schema(m["trace"])
