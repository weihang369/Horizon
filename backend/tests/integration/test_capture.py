"""Opt-in AI call capture, its Forget guard and the first real AiStateHooks (ai-call-capture spec; docs/ai/02 B10;
ai-foundation design D27–D29; tasks 6.1–6.4)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from horizon.ai.contexts import TurnContext
from horizon.gateway.context import call_ctx
from horizon.runtime import Runtime
from horizon.services.capture import MAX_QUEUE
from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, messages


def enable_capture(rt: Runtime) -> None:
    """What HORIZON_CAPTURE_AI_CALLS=1 does at start-up, applied to a running test runtime."""
    rt.capture.enabled = True
    rt.gateway.capture_bodies = True
    rt.gateway.on_call = rt.capture.on_call


async def rows(api: Api, where: str = "1 = 1", **params: Any) -> list[dict[str, Any]]:
    await api.rt.capture.flush()
    async with api.rt.db.read() as conn:
        out = [dict(r) for r in (await conn.execute(text(f"SELECT * FROM ai_calls WHERE {where} ORDER BY created_at, id"),
                                                    params)).mappings()]
    for r in out:
        for k in ("request", "response"):
            if isinstance(r[k], str):
                r[k] = json.loads(r[k])
    return out


async def naive_group_turn(api: Api) -> tuple[str, dict[str, Any]]:
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"router": "naive", "turn": "naive"}})
    assert r.status_code == 204
    sid = (await create(api, "group", ["chr_seedHana", "chr_seedTakeshi"], world="wld_seedSunnyHollow"))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Who's cooking tonight?"})
    await api.drive(30000)
    return sid, chars(await messages(api, sid))[0]


# ── 6.1 ──
async def test_capture_off_builds_nothing_and_writes_nothing(api: Api) -> None:
    assert api.rt.capture.enabled is False and api.rt.gateway.capture_bodies is False
    seen: list[Any] = []
    api.rt.gateway.on_call = lambda ctx, summary, outcome: seen.append(summary)   # type: ignore[assignment,misc]
    await naive_group_turn(api)
    assert seen and all("body" not in s for s in seen)
    assert await rows(api) == []


async def test_capture_on_route_reply_and_turn_rows(api: Api) -> None:
    enable_capture(api.rt)
    sid, reply = await naive_group_turn(api)
    mine = await rows(api, "message_id = :m", m=reply["id"])
    kinds = {(r["kind"], r["purpose"]) for r in mine}
    assert {("call", "route"), ("call", "reply"), ("turn", "turn")} <= kinds
    reply_row = next(r for r in mine if r["purpose"] == "reply")
    assert reply_row["request"]["messages"] and reply["content"] in reply_row["response"]["text"]   # raw stream: tag kept
    assert reply_row["usage_record_id"] and reply_row["session_id"] == sid
    route = next(r for r in mine if r["purpose"] == "route")
    assert route["request"]["state"]["quoted_message"] == "Who's cooking tonight?" and route["response"]["answers"]


async def test_turn_row_round_trips_into_a_turn_context(api: Api) -> None:
    enable_capture(api.rt)
    _, reply = await naive_group_turn(api)
    (turn,) = [r for r in await rows(api, "message_id = :m AND kind = 'turn'", m=reply["id"])]
    ctx = TurnContext.model_validate(turn["request"])
    assert ctx.message_id == reply["id"] and ctx.speaker.id == reply["author"]["characterId"]
    assert turn["response"]["plan"] is None and turn["response"]["routingFallback"] is False


async def test_a_full_queue_drops_and_records_the_count(api: Api) -> None:
    cap = api.rt.capture
    cap.enabled = True
    ctx = call_ctx("reply", world_id="wld_seedMeridian", character_id="chr_seedAmara")
    cap._kicked = True                       # hold the size-triggered flush: 2,500 calls arrive before any flush runs
    for i in range(2500):
        cap.on_call(ctx, {"kind": "chat", "model": "m", "body": {"request": {"i": i}}}, {"costUsd": 0.0})
    assert len(cap.queue) == MAX_QUEUE and cap.dropped == 500
    await cap.flush()
    cap.on_call(ctx, {"kind": "chat", "model": "m"}, {"costUsd": 0.0})
    stored = await rows(api)
    assert len(stored) == MAX_QUEUE + 1 and stored[-1]["dropped_before"] == 500


async def test_retention_deletes_rows_older_than_7_days(api: Api) -> None:
    cap = api.rt.capture
    cap.enabled = True
    ctx = call_ctx("reply", world_id="wld_seedMeridian")
    cap.on_call(ctx, {"kind": "chat", "model": "m"}, {})
    cap.queue[0]["created_at"] = "2026-09-24T00:00:00.000Z"   # 9 days before the frozen START
    cap.on_call(ctx, {"kind": "chat", "model": "m"}, {})
    await cap.flush()
    assert await cap.retention() == 1
    assert len(await rows(api)) == 1


async def test_an_embedding_row_has_no_texts(api: Api) -> None:
    cap = api.rt.capture
    cap.enabled = True
    cap.on_call(call_ctx("embed_doc", world_id="wld_seedMeridian"),
                {"kind": "embedding", "texts": 2, "model": "e", "body": {"request": {"input": ["secret"]}}}, {})
    (r,) = await rows(api)
    assert "secret" not in json.dumps(r) and r["request"] == {"kind": "embedding"}


# ── 6.3: Forget and capture ──
async def test_a_row_queued_before_forget_never_lands(api: Api) -> None:
    cap = api.rt.capture
    cap.enabled = True
    cap.on_call(call_ctx("reply", world_id="wld_seedMeridian", character_id="chr_seedAmara"),
                {"kind": "chat", "model": "m", "body": {"request": {"messages": [{"content": "the spare key"}]}}}, {})
    cap.on_call(call_ctx("reply", world_id="wld_seedMeridian"), {"kind": "chat", "model": "m"}, {})   # no character
    cap.on_call(call_ctx("reply", world_id="wld_seedSunnyHollow", character_id="chr_seedHana"),
                {"kind": "chat", "model": "m"}, {})
    from horizon.services.memory.forget import forget_chain

    async with api.rt.db.write() as tx:
        await forget_chain(api.rt, tx.conn, character_id="chr_seedAmara", world_id="wld_seedMeridian", chain=set())
    stored = await rows(api)
    assert [r["character_id"] for r in stored] == ["chr_seedHana"]


# ── 6.4: the purge hooks ──
async def test_character_and_message_hooks_delete_idempotently(api: Api) -> None:
    cap = api.rt.capture
    cap.enabled = True
    for cid, mid in (("chr_seedAmara", "msg_a"), ("chr_seedHana", "msg_b"), ("chr_seedHana", "msg_c")):
        cap.on_call(call_ctx("reply", world_id="wld_seedMeridian", character_id=cid, message_id=mid),
                    {"kind": "chat", "model": "m"}, {})
    await cap.flush()
    for _ in range(2):                                        # at-least-once delivery
        await api.rt.hooks.on_delete("character", ["chr_seedAmara"])
        await api.rt.hooks.on_delete("message", ["msg_b"])
        await api.rt.hooks.on_delete("session", ["ses_none"])
        await api.rt.hooks.on_delete("world", ["wld_none"])
    assert [r["message_id"] for r in await rows(api)] == ["msg_c"]


async def test_a_character_delete_reaches_the_hook_through_the_outbox(api: Api) -> None:
    cap = api.rt.capture
    cap.enabled = True
    cap.on_call(call_ctx("reply", world_id="wld_seedSunnyHollow", character_id="chr_seedRin"),
                {"kind": "chat", "model": "m"}, {})
    await cap.flush()
    assert (await api.client.delete(f"{API}/characters/chr_seedRin")).status_code in (200, 204)
    for _ in range(20):
        if not await rows(api, "character_id = 'chr_seedRin'"):
            break
        await api.drive(1000)
    assert await rows(api, "character_id = 'chr_seedRin'") == []
