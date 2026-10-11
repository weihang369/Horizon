"""The approved greeting first (docs/ai/04 P9; session-lifecycle "New session opening"; session-runtime "A verbatim line
is spoken without a model call"; persona-context D19, D20; tasks 6.1–6.2). Virtual clock, no network."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select, update

from horizon.db import tables as t
from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, events, ledger, messages, use_first_chat
from tests.sessions.test_naive import chat_bodies

AMARA = "chr_seedAmara"


async def stored_greeting(api: Api, cid: str = AMARA) -> str:
    async with api.rt.db.read() as conn:
        p = (await conn.execute(select(t.characters.c.profile).where(t.characters.c.id == cid))).scalar_one()
    return str(p["greeting"])


async def first(api: Api, sid: str) -> dict[str, Any]:
    return chars(await messages(api, sid))[0]


async def test_first_chat_is_the_stored_greeting_with_no_model_call(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    g = await first(api, sid)
    assert g["content"] == await stored_greeting(api) and g["status"] == "complete"
    assert g["emotion"] == "happy" and g["emotionSource"] == "default" and "usage" not in g
    tr = g["trace"]
    assert "model" not in tr and tr["calls"] == [] and tr["emotion"] == {"chosen": "happy", "source": "default"}
    assert not [r for r in await ledger(api) if r["message_id"] == g["id"]]
    assert not [e for e in await events(api, sid) if e["type"] == "energy" and e["payload"].get("spent")]
    async with api.rt.db.read() as conn:
        row = (await conn.execute(select(t.turn_traces.c.engine, t.turn_traces.c.prompt_version)
                                  .where(t.turn_traces.c.message_id == g["id"]))).first()
    assert row is not None and tuple(row) == ("verbatim", None)


async def test_seed_sessions_and_a_continue_live_fork_do_not_count(api: Api) -> None:
    await api.set_key()
    r = await api.post(f"{API}/sessions/ses_seedAmaraHeadache/fork", {})
    assert r.status_code in (200, 201), r.text
    fork = r.json()["session"]["id"]
    assert (await api.post(f"{API}/sessions/{fork}/leave", {})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    assert (await first(api, sid))["content"] == await stored_greeting(api)


async def test_an_asleep_only_first_session_does_not_count(api: Api) -> None:
    await api.set_key()
    async with api.rt.db.write() as tx:
        await tx.conn.execute(update(t.characters).where(t.characters.c.id == AMARA).values(
            energy_current=0.0, energy_as_of=api.rt.now_iso()))
    asleep = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    assert not chars(await messages(api, asleep))          # only the asleep note
    assert (await api.post(f"{API}/sessions/{asleep}/leave", {})).status_code == 204
    async with api.rt.db.write() as tx:
        await tx.conn.execute(update(t.characters).where(t.characters.c.id == AMARA).values(
            energy_current=1000.0, energy_as_of=api.rt.now_iso()))
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    assert (await first(api, sid))["content"] == await stored_greeting(api)


async def test_second_chat_scripted_is_the_billed_bank_greeting(api: Api) -> None:
    await api.set_key()
    await use_first_chat(api)
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    g = await first(api, sid)
    assert g["content"] == await stored_greeting(api) and g["trace"]["model"]["costUsd"] > 0   # D-81: billed
    assert [r for r in await ledger(api) if r["message_id"] == g["id"]]


async def test_second_chat_naive_and_agent_generate_it(api: Api) -> None:
    await api.set_key()
    await use_first_chat(api)
    for profile, cue in (("naive", "Open the conversation with a short, warm greeting in character."),
                         ("agent", "Don't reuse your usual greeting: '")):
        assert (await api.post(f"{API}/_test/ai-profile", {"profile": profile})).status_code == 204
        sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
        await api.drive(6000)
        g = await first(api, sid)
        assert g["content"] == "ok" and g["trace"]["model"]["costUsd"] > 0     # the fake's generated answer
        assert cue in json.dumps(chat_bodies(api)[-1]["messages"], ensure_ascii=False)
        assert (await api.post(f"{API}/sessions/{sid}/leave", {})).status_code == 204


async def test_stop_mid_greeting_keeps_the_text_at_no_cost(api: Api) -> None:
    await api.set_key()
    long = "Hello there, it is good to finally meet you after all this time. " * 6
    async with api.rt.db.write() as tx:
        p = (await tx.conn.execute(select(t.characters.c.profile).where(t.characters.c.id == AMARA))).scalar_one()
        await tx.conn.execute(update(t.characters).where(t.characters.c.id == AMARA).values(
            profile={**p, "greeting": long.strip()}))
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    for _ in range(80):
        await api.drive(100)
        if any(m["status"] == "streaming" for m in await messages(api, sid)):
            break
    await api.drive(300)
    await command(api, sid, "stop")
    await api.drive(1000)
    g = await first(api, sid)
    assert g["status"] == "interrupted" and 0 < len(g["content"]) < len(long.strip())
    assert not [r for r in await ledger(api) if r["message_id"] == g["id"]]


async def test_regenerating_the_verbatim_greeting_is_a_billed_variant(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    g = await first(api, sid)
    await command(api, sid, "regenerate", {"messageId": g["id"]})
    await api.drive(12000)
    again = await first(api, sid)
    assert len(again["variants"]) == 2 and again["trace"]["model"]["costUsd"] > 0
    assert [r for r in await ledger(api) if r["message_id"] == g["id"] and r["purpose"] == "reply"]
