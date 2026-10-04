"""Watch (session-modes "Watch pacing and the turn cap", "Watch controls", "Pacing uses the session clock"; tasks
9.1–9.3)."""

from __future__ import annotations

from typing import Any

from horizon.api.sessions import COMMAND_BODIES
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages, snapshot

DUO = ["chr_seedHana", "chr_seedTakeshi"]


async def _watch(api: Api, **cfg: Any) -> str:
    await api.set_key()
    config = {"premise": "Rainy afternoon at the shop.", "maxTurns": 10, "paceMs": 500, "openingSpeaker": "auto", **cfg}
    sid: str = (await create(api, "watch", DUO, world="wld_seedSunnyHollow", config=config))["session"]["id"]
    return sid


async def test_stop_at_the_cap_then_extend(api: Api) -> None:
    sid = await _watch(api)
    await api.drive(200000)
    snap = await snapshot(api, sid)
    assert len(chars(snap["messages"])) == 10
    assert snap["session"]["pausedReason"] == "turn_cap"
    assert snap["session"]["state"]["turnsTaken"] == 10
    first = snap["messages"][0]
    assert first["kind"] == "direction" and first["content"] == "Rainy afternoon at the shop."
    speakers = [m["author"]["characterId"] for m in chars(snap["messages"])]
    assert speakers == DUO * 5  # round-robin from the opening speaker
    await command(api, sid, "watch/extend", {"turns": 10})
    await api.drive(10000)
    snap = await snapshot(api, sid)
    assert len(chars(snap["messages"])) > 10 and snap["session"]["state"]["turnLimit"] == 20
    await assert_reduces(api, sid)


async def test_pace_is_clock_time(api: Api) -> None:
    from horizon.domain.timeutil import ms_from_iso

    sid = await _watch(api, paceMs=3000)
    await api.drive(30000)
    evs = await events(api, sid)
    ends = [e for e in evs if e["type"] == "turn.end"]
    nexts = [e for e in evs if e["type"] == "turn.next"]
    gaps = [ms_from_iso(n["at"]) - ms_from_iso(e["at"]) for e, n in zip(ends, nexts[1:], strict=False)]
    assert gaps and all(g == 400 + 3000 for g in gaps)  # the turn gap, then the pace


async def test_step_while_paused(api: Api) -> None:
    sid = await _watch(api)
    await api.drive(5000)
    await command(api, sid, "watch/pause")
    await api.drive(20000)
    n = len(chars(await messages(api, sid)))
    await command(api, sid, "watch/step")
    await api.drive(20000)
    snap = await snapshot(api, sid)
    assert len(chars(snap["messages"])) == n + 1
    assert snap["session"]["status"] == "paused" and snap["session"]["state"]["status"] == "paused"


async def test_play_pace_direct_and_next_speaker(api: Api) -> None:
    sid = await _watch(api)
    await api.drive(3000)
    await command(api, sid, "watch/pause")
    await command(api, sid, "watch/pace", {"paceMs": 1500})
    assert (await snapshot(api, sid))["session"]["config"]["paceMs"] == 1500
    assert (await api.post(f"{API}/sessions/{sid}/watch/pace", {"paceMs": 800})).status_code == 422
    await command(api, sid, "watch/direct", {"text": "A customer walks in soaking wet."})
    assert (await messages(api, sid))[-1]["kind"] == "direction"
    await command(api, sid, "next-speaker", {"characterId": "chr_seedTakeshi"})  # paused: steps once with the nudge
    await api.drive(15000)
    last = chars(await messages(api, sid))[-1]
    assert last["author"]["characterId"] == "chr_seedTakeshi"
    assert "soaking wet" in last["content"].lower() or "customer" in last["content"].lower()
    await command(api, sid, "watch/play")
    await api.drive(15000)
    assert (await snapshot(api, sid))["session"]["state"]["status"] == "playing"
    await assert_reduces(api, sid)


async def test_step_in_pauses_and_two_reply(api: Api) -> None:
    sid = await _watch(api)
    await api.drive(3000)
    n = len(chars(await messages(api, sid)))
    await command(api, sid, "watch/step-in", {"text": "Mind if I join?"})
    await api.drive(30000)
    snap = await snapshot(api, sid)
    assert snap["session"]["status"] == "paused"
    user = [m for m in snap["messages"] if m["author"]["type"] == "user"]
    assert [m["content"] for m in user] == ["Mind if I join?"]
    after = [m for m in chars(snap["messages"]) if m["seq"] > user[0]["seq"]]
    assert 1 <= len(after) <= 2 and len(chars(snap["messages"])) <= n + 2


async def test_summarise_is_billed(api: Api) -> None:
    sid = await _watch(api)
    await api.drive(10000)
    await command(api, sid, "watch/summarise")
    await api.drive(5000)
    assert any(m["kind"] == "summary" and m["content"].startswith("Episode summary") for m in await messages(api, sid))
    assert any(r["purpose"] == "summary" and r["category"] == "summary" for r in await ledger(api))


async def test_everyone_asleep_pauses_with_a_note(api: Api) -> None:
    await api.set_key()
    for cid in DUO:
        assert (await api.client.put(f"{API}/characters/{cid}/energy/max", json={"points": 1000})).status_code == 200
    assert (await api.post(f"{API}/_test/scenario", {"id": "character_exhausted"})).status_code == 204
    from sqlalchemy import update

    from horizon.db import tables as t

    async with api.rt.db.write() as tx:  # Hana asleep too
        await tx.conn.execute(update(t.characters).where(t.characters.c.id == "chr_seedHana").values(
            energy_current=0.0, energy_as_of=api.rt.now_iso()))
    sid: str = (await create(api, "watch", DUO, world="wld_seedSunnyHollow",
                              config={"premise": "Quiet night.", "maxTurns": 10, "paceMs": 500}))["session"]["id"]
    await api.drive(5000)
    snap = await snapshot(api, sid)
    assert any("Everyone's asleep" in m["content"] for m in snap["messages"])
    assert snap["session"]["status"] == "paused" and chars(snap["messages"]) == []


async def test_every_command_route_is_served(api: Api) -> None:
    """9.3: no command answers with a "not available yet" error."""
    await api.set_key()
    one = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    reply = chars(await messages(api, one))[0]["id"]
    bodies: dict[str, dict[str, Any]] = {
        "send": {"text": "hi"}, "regenerate": {"messageId": reply}, "set-emotion": {"characterId": "chr_seedAmara",
                                                                                   "emotion": "happy"},
        "set-emotion-mode": {"mode": "llm"}, "set-responder-policy": {"policy": "auto"}, "set-music-policy": {"policy": "arena"},
        "set-readable-mode": {"on": False}, "next-speaker": {}, "mute": {"characterId": "chr_seedAmara", "muted": False},
        "debate/auto-advance": {"on": False}, "debate/ask": {"characterId": "chr_seedAmara", "text": "why?"},
        "debate/interject": {"text": "hm"}, "debate/end": {"withVerdict": False}, "debate/pick": {"side": "prop"},
        "watch/pace": {"paceMs": 500}, "watch/direct": {"text": "rain"}, "watch/step-in": {"text": "hello"},
        "watch/extend": {"turns": 2},
    }
    for name in COMMAND_BODIES:
        r = await api.post(f"{API}/sessions/{one}/{name}", bodies.get(name, {}))
        body = r.json() if r.content else {}
        assert "availableIn" not in str(body), (name, body)
        assert r.status_code in (202, 409), (name, r.status_code, body)  # 409: a debate/watch command in a 1:1
        await command(api, one, "stop")
