"""The 1:1 slice (session-runtime "Turn order", "Turn event sequence", "Trace ownership", "Reply drains energy";
session-modes "1:1 conversation"; session-event-sourcing "Live exchange reduces to the snapshot")."""

from __future__ import annotations

from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages


async def test_reply_event_sequence_energy_ledger_and_trace(api: Api) -> None:
    await api.set_key()
    before = (await api.json(f"{API}/characters/chr_seedAmara"))["energy"]["current"]
    snap = await create(api, "one_on_one", ["chr_seedAmara"])
    sid = snap["session"]["id"]
    assert snap["session"]["isSeed"] is False and snap["lastSeq"] >= 2
    await api.drive(6000)
    await command(api, sid, "send", {"text": "I've had a headache for three days"})
    await api.drive(12000)
    msgs = await messages(api, sid)
    assert [m["author"]["type"] for m in msgs] == ["character", "user", "character"]
    reply = chars(msgs)[1]
    assert reply["status"] == "complete" and reply["content"]
    tr = reply["trace"]
    assert tr["energy"]["spent"] > 0
    call = next(c for c in tr["calls"] if c["purpose"] == "reply")
    assert call["costUsd"] == reply["usage"]["costUsd"]
    evs = await events(api, sid)
    types = {e["type"] for e in evs}
    for t in ("turn.next", "turn.thinking", "turn.start", "token", "emotion", "turn.end", "energy", "insight", "message"):
        assert t in types, t
    # Turn order: turn.next → thinking → start → … → turn.end → energy → insight for the reply.
    user_seq = next(x for x in evs if x["type"] == "message")["seq"]
    mine = [e["type"] for e in evs if e["payload"].get("messageId") == reply["id"]
            or (e["type"] in ("turn.next", "turn.thinking") and e["seq"] > user_seq)]
    assert mine.index("turn.start") < mine.index("turn.end") < mine.index("insight")
    rows = [r for r in await ledger(api) if r["message_id"] == reply["id"]]
    assert len(rows) == 1 and rows[0]["purpose"] == "reply" and rows[0]["provider"] == "scripted"
    assert rows[0]["category"] == "chat" and round(rows[0]["cost_usd"], 6) == reply["usage"]["costUsd"]
    after = (await api.json(f"{API}/characters/chr_seedAmara"))["energy"]["current"]
    assert after < before
    assert (await api.json(f"{API}/usage/summary"))["byCategory"]["chat"] > 0
    energy_ev = [e for e in evs if e["type"] == "energy" and e["payload"].get("spent")]
    assert energy_ev and energy_ev[-1]["payload"]["characterId"] == "chr_seedAmara"
    await assert_reduces(api, sid)


async def test_regenerate_keeps_the_original_and_reduces(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Quick question about sleep."})
    await api.drive(12000)
    reply = chars(await messages(api, sid))[-1]
    first = reply["content"]
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(12000)
    m = next(x for x in await messages(api, sid) if x["id"] == reply["id"])
    assert len(m["variants"]) == 2 and m["activeVariantId"] == m["variants"][1]["id"]
    assert m["variants"][0]["content"] == first and m["status"] == "complete"
    await assert_reduces(api, sid)


async def test_paused_one_on_one_auto_resumes(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    r = await api.client.post(f"{API}/sessions/{sid}/leave")
    assert r.status_code == 204
    assert (await api.json(f"{API}/sessions/{sid}"))["session"]["pausedReason"] == "navigated_away"
    await command(api, sid, "send", {"text": "Back again."})
    await api.drive(12000)
    evs = await events(api, sid)
    resumed = next(i for i, e in enumerate(evs) if e["type"] == "session.resumed")
    user = next(i for i, e in enumerate(evs) if e["type"] == "message" and e["payload"]["message"]["author"]["type"] == "user")
    assert resumed < user
    assert len(chars(await messages(api, sid))) == 2
