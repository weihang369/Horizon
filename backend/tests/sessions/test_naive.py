"""The naive DeepSeek TurnEngine over the in-process fake provider (ai-ports "Naive reply engine", "Inline emotion tag";
design D11; tasks 10.2, 10.3). No network: the fake answers in process."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import httpx

from horizon.db import tables as t
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages


def sse(chunks: list[str], *, error_after: int | None = None, gid: str = "gen-naive-0001") -> httpx.Response:
    base = {"id": gid, "model": "deepseek/deepseek-v4.1-flash", "provider": "DeepSeek", "object": "chat.completion.chunk"}
    sent = chunks if error_after is None else chunks[:error_after]
    frames = [{**base, "choices": [{"index": 0, "delta": {"content": c}, "finish_reason": None}]} for c in sent]
    if error_after is not None:
        frames.append({**base, "error": {"message": "upstream reset"}, "choices": []})
    else:
        frames.append({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 900, "completion_tokens": 9, "cost": 0.0003,
                                 "prompt_tokens_details": {"cached_tokens": 0}}})
    text = "".join(f"data: {json.dumps(f)}\n\n" for f in frames) + ("data: [DONE]\n\n" if error_after is None else "")
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=text.encode("utf-8"))


def chat_bodies(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/chat/completions")]


async def _naive(api: Api) -> str:
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"turn": "naive"}})
    assert r.status_code == 204
    sid: str = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    return sid


async def test_streamed_reply_with_the_tag_parsed_off(api: Api) -> None:
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(["<e:ha", "ppy>Hello ", "there, friend."]))
    sid = await _naive(api)
    greeting = chars(await messages(api, sid))[0]
    assert greeting["content"] == "Hello there, friend." and greeting["emotion"] == "happy"
    assert greeting["emotionSource"] == "llm" and greeting["status"] == "complete"
    body = chat_bodies(api)[-1]
    assert body["reasoning"] == {"enabled": False} and body["max_tokens"] == 350
    assert body["messages"][0]["role"] == "system" and "<e:LABEL>" in body["messages"][0]["content"]
    row = next(r for r in await ledger(api) if r["message_id"] == greeting["id"])
    assert row["provider"] == "DeepSeek" and row["cost_usd"] == 0.0003 and row["purpose"] == "reply"
    assert greeting["trace"]["energy"]["spent"] == 3
    await assert_reduces(api, sid)


async def test_no_tag_keeps_the_previous_face(api: Api) -> None:
    sid = await _naive(api)  # the fake answers plain "ok"
    m = chars(await messages(api, sid))[0]
    assert m["content"] == "ok" and m["emotionSource"] == "default" and m["emotion"] == "neutral"


async def test_warm_flag_on_a_repeated_prefix(api: Api, monkeypatch: Any) -> None:
    sid = await _naive(api)
    seen: list[bool] = []
    real = api.rt.gateway.chat_estimate

    def spy(req: Any, **kw: Any) -> float:
        seen.append(bool(kw.get("warm")))
        return real(req, **kw)

    monkeypatch.setattr(api.rt.gateway, "chat_estimate", spy)
    for text in ("First question.", "Second question."):
        await command(api, sid, "send", {"text": text})
        await api.drive(12000)
    assert seen == [True, True]  # the greeting set the prefix; both replies reuse it


async def test_mid_stream_error_keeps_the_partial_text(api: Api) -> None:
    sid = await _naive(api)
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(["<e:sad>Hello", " and then"], error_after=2))
    await command(api, sid, "send", {"text": "Go on."})
    await api.drive(12000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "interrupted" and reply["interruptedBy"] == "error"
    assert reply["content"] == "Hello and then" and reply["error"]["code"] == "provider_error"
    assert any(e["type"] == "error" and e["payload"].get("messageId") == reply["id"] for e in await events(api, sid))
    rows = [r for r in await ledger(api) if r["message_id"] == reply["id"]]
    assert len(rows) == 1 and rows[0]["cost_source"] == "estimate"
    await assert_reduces(api, sid)


async def test_prefix_stays_stable_between_drops(api: Api) -> None:
    sid = await _naive(api)
    for text in ("First question.", "Second question."):
        await command(api, sid, "send", {"text": text})
        await api.drive(12000)
    a, b = chat_bodies(api)[-2:]
    assert b["messages"][:len(a["messages"])] == a["messages"]


async def test_window_drops_half_at_once(api: Api) -> None:
    sid = await _naive(api)
    rt = api.rt
    rt.runtime_cfg = dataclasses.replace(rt.runtime_cfg, runtime=dataclasses.replace(rt.runtime_cfg.runtime, window_tokens=40))
    for i in range(6):
        await command(api, sid, "send", {"text": f"Question number {i}: what about sleep, rotas and coffee?"})
        await api.drive(12000)
    async with rt.db.read() as conn:
        rows = (await conn.execute(t.session_summaries.select().where(t.session_summaries.c.session_id == sid)
                                   .order_by(t.session_summaries.c.id))).mappings().all()
    assert rows and rows[-1]["kind"] == "rolling"
    upto = rows[-1]["upto_seq"]
    msgs = await messages(api, sid)
    last = chat_bodies(api)[-1]["messages"]
    summary = next(m for m in last if m["role"] == "system" and m["content"].startswith("Earlier in this conversation"))
    assert summary  # the rolling summary sits between the system prompt and the history
    history = [m["content"] for m in last[2:]]
    kept = [m for m in msgs if m["seq"] > upto and m["content"] and m["status"] != "streaming"]
    assert len(history) == len(kept) - 1 or len(history) == len(kept)  # starts at the boundary
    dropped = [m for m in msgs if m["seq"] <= upto and m["author"]["type"] == "user"]
    assert dropped and all(m["content"] not in " ".join(history) for m in dropped)
