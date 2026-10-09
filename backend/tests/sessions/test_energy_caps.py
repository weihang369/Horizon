"""Energy gates, scenarios and the daily cap (session-runtime "Energy gate in turns", "Daily cap pauses live
sessions"; event-streams "Budget warning reaches the live session", "Changes are announced"; http-api "Scenarios
mirror the mock"; tasks 6.1–6.5)."""

from __future__ import annotations

from typing import Any

from horizon.events.bus import GLOBAL
from tests.conftest import Api
from tests.jobs.kit import cancel_overlay_jobs
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, messages, snapshot
from tests.sessions.test_turns import FixedEngine


async def _scenario(api: Api, sid: str) -> None:
    assert (await api.post(f"{API}/_test/scenario", {"id": sid})).status_code == 204


def _drain(sub: Any) -> list[dict[str, Any]]:
    out = []
    while not sub.queue.empty():
        x = sub.queue.get_nowait()
        if isinstance(x, dict):
            out.append(x)
    return out


async def test_mentioned_character_asleep(api: Api) -> None:
    await api.set_key()
    await _scenario(api, "character_exhausted")
    sid = (await create(api, "group", ["chr_seedHana", "chr_seedTakeshi"], world="wld_seedSunnyHollow"))["session"]["id"]
    await command(api, sid, "send", {"text": "Dad, dinner?", "mentions": ["chr_seedTakeshi"]})
    await api.drive(15000)
    msgs = await messages(api, sid)
    assert any(m["kind"] == "system_note" and "Takeshi is asleep" in m["content"] for m in msgs)
    assert any(e["type"] == "error" and e["payload"]["code"] == "energy_exhausted" for e in await events(api, sid))
    assert all(m["author"].get("characterId") != "chr_seedTakeshi" for m in chars(msgs))
    assert chars(msgs)  # Hana answered
    r = await api.post(f"{API}/characters/chr_seedTakeshi/energy/top-up", {"points": 500})
    assert r.status_code == 200
    assert (await api.json(f"{API}/characters/chr_seedTakeshi"))["energy"]["current"] == 500
    await assert_reduces(api, sid)


async def test_threshold_follows_the_period(api: Api) -> None:
    await api.set_key()
    await _scenario(api, "character_exhausted")
    assert (await api.post(f"{API}/characters/chr_seedTakeshi/energy/top-up", {"points": 6})).status_code == 200
    assert (await api.json(f"{API}/characters/chr_seedTakeshi"))["energy"]["state"] == "tired"
    await _scenario(api, "rush_hour")
    assert (await api.json(f"{API}/settings"))["pricing"]["period"] == "peak"
    assert (await api.json(f"{API}/characters/chr_seedTakeshi"))["energy"]["state"] == "exhausted"
    sid = (await create(api, "group", ["chr_seedHana", "chr_seedTakeshi"], world="wld_seedSunnyHollow"))["session"]["id"]
    await command(api, sid, "send", {"text": "Anyone hungry?"})
    await api.drive(20000)
    evs = await events(api, sid)
    opening = next(e for e in evs if e["type"] == "energy" and e["payload"]["characterId"] == "chr_seedTakeshi")
    assert opening["payload"]["state"] == "exhausted"
    msgs = await messages(api, sid)
    assert all(m["author"].get("characterId") != "chr_seedTakeshi" for m in chars(msgs))
    skipped = [s for m in msgs for s in ((m.get("trace") or {}).get("routing") or {}).get("skipped", [])]
    assert {"characterId": "chr_seedTakeshi", "reason": "exhausted"} in skipped


async def test_scenarios_mirror_the_mock_and_keep_user_sessions(api: Api) -> None:
    await api.set_key()
    fork = (await api.post(f"{API}/sessions/ses_seedDebate4Day/fork", {}, status=201)).json()
    await _scenario(api, "character_exhausted")
    assert (await api.json(f"{API}/characters/chr_seedTakeshi"))["energy"]["current"] == 0
    assert len(await messages(api, fork["session"]["id"])) == len(fork["messages"])
    await _scenario(api, "rush_hour")
    assert (await api.json(f"{API}/settings"))["pricing"]["period"] == "peak"
    r = await api.post(f"{API}/_test/scenario", {"id": "network_down"})
    assert r.status_code == 422 and r.json()["error"]["details"]["clientSide"] is True
    await api.post(f"{API}/admin/factory-reset", {"confirm": "DELETE EVERYTHING"}, status=204)
    assert (await api.json(f"{API}/settings"))["pricing"]["period"] == "off_peak"  # the override is cleared


async def test_cap_reached_by_the_greeting(api: Api) -> None:
    await api.set_key()
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 0.00005}})).status_code == 200
    sub = api.rt.bus.subscribe(GLOBAL)
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(8000)
    globals_ = _drain(sub)
    assert any(g["type"] == "budget.reached" for g in globals_)
    snap = await snapshot(api, sid)
    assert snap["session"]["pausedReason"] == "daily_budget"
    assert chars(snap["messages"]) == []  # the refused turn left no message
    r = await api.post(f"{API}/sessions/{sid}/send", {"text": "hello?"})
    assert r.status_code == 402 and r.json()["error"]["code"] == "daily_budget_exceeded"
    await assert_reduces(api, sid)


async def test_crossing_the_cap_pauses_then_a_raised_cap_resumes(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)  # M4: the test-mode overlay job would spend in the background
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    spent = (await api.json(f"{API}/settings"))["spentTodayUsd"]
    assert spent > 0
    # The next reply costs exactly the headroom: its estimate fits, and its row lands on the cap (a crossing).
    api.rt.ai.override("turn", FixedEngine(api, text="Sleep first, then we talk.", cost=0.0001))
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": spent + 0.0001}})).status_code == 200
    await command(api, sid, "send", {"text": "One more question about sleep."})
    await api.drive(12000)
    snap = await snapshot(api, sid)
    assert len(chars(snap["messages"])) == 2 and chars(snap["messages"])[-1]["status"] == "complete"
    assert snap["session"]["pausedReason"] == "daily_budget"
    r = await api.post(f"{API}/sessions/{sid}/send", {"text": "hello?"})
    assert r.status_code == 402
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 1}})).status_code == 200
    await command(api, sid, "send", {"text": "And now?"})
    await api.drive(12000)
    snap = await snapshot(api, sid)
    assert snap["session"]["status"] == "active" and len(chars(snap["messages"])) == 3
    await assert_reduces(api, sid)


async def test_budget_warning_inside_a_session(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    spent = (await api.json(f"{API}/settings"))["spentTodayUsd"]
    # The warning line (1 % of the cap) sits just above today's spend: the next reply crosses it, far below the cap.
    cap = (spent + 0.00002) * 100
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": cap, "warnAtPct": 1}})).status_code == 200
    sub = api.rt.bus.subscribe(GLOBAL)
    await command(api, sid, "send", {"text": "A short one."})
    await api.drive(12000)
    warn = [e for e in await events(api, sid) if e["type"] == "budget.warning"]
    assert len(warn) == 1 and warn[0]["payload"]["scope"] == "daily"
    globals_ = _drain(sub)
    assert any(g["type"] == "budget.warning" for g in globals_)
    assert any(g == {"type": "entity.changed", "kind": "usage"} for g in globals_)
    assert any(g.get("kind") == "session" and g.get("id") == sid for g in globals_)
    await assert_reduces(api, sid)
