"""End-to-end scripted pass (task 13.2): 1:1, group, debate and watch each run to completion on the virtual clock.
Every response is schema-checked by the test-mode backend; here every stored event is checked against `SessionEvent`
and every session reduces exactly to its served messages."""

from __future__ import annotations

from typing import Any

from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, messages, snapshot


def _valid_events(api: Api, evs: list[dict[str, Any]]) -> None:
    for e in evs:
        assert api.rt.schema.errors("SessionEvent", e) == [], e["type"]


async def test_every_mode_runs_to_completion(api: Api) -> None:
    await api.set_key()

    one = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    for text in ("I've had a headache for three days.", "It's worse in the mornings."):
        await command(api, one, "send", {"text": text})
        await api.drive(12000)
    await command(api, one, "regenerate", {"messageId": chars(await messages(api, one))[-1]["id"]})
    await api.drive(12000)
    assert len(chars(await messages(api, one))) == 3
    await api.client.post(f"{API}/sessions/{one}/end")

    group = (await create(api, "group", ["chr_seedAmara", "chr_seedVictor", "chr_seedMei"]))["session"]["id"]
    await command(api, group, "send", {"text": "Victor, is the rota fair?", "mentions": ["chr_seedVictor"]})
    await api.drive(30000)
    await command(api, group, "everyone-answer")
    await api.drive(40000)
    assert len(chars(await messages(api, group))) >= 4
    await api.client.post(f"{API}/sessions/{group}/end")

    debate = (await create(api, "debate", ["chr_seedAmara", "chr_seedVictor"], config={
        "motion": "This house would adopt a four-day work week", "format": "two_sided",
        "sides": {"prop": ["chr_seedAmara"], "opp": ["chr_seedVictor"]}, "roundsPreset": "standard",
        "moderator": "auto_host", "verdictBy": "arbiter", "autoAdvance": True, "pauseMs": 1500}))["session"]["id"]
    await api.drive(150000)
    snap = await snapshot(api, debate)
    assert snap["session"]["status"] == "ended" and len(chars(snap["messages"])) == 6
    assert snap["session"]["state"]["verdict"]["decidedBy"] == "arbiter"

    watch = (await create(api, "watch", ["chr_seedHana", "chr_seedTakeshi"], world="wld_seedSunnyHollow",
                          config={"premise": "Closing time at the shop.", "maxTurns": 10, "paceMs": 500}))["session"]["id"]
    await api.drive(120000)
    snap = await snapshot(api, watch)
    assert snap["session"]["pausedReason"] == "turn_cap" and len(chars(snap["messages"])) == 10
    await command(api, watch, "watch/summarise")
    await api.drive(5000)

    for sid in (one, group, debate, watch):
        _valid_events(api, await events(api, sid))
        await assert_reduces(api, sid)
        assert all(m["status"] != "streaming" for m in await messages(api, sid))
    summary = await api.json(f"{API}/usage/summary")
    assert summary["byCategory"]["chat"] > 0 and summary["byCategory"]["decision"] > 0
