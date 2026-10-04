"""Debate (session-modes "Debate phases", "Debate moderation", "Debate verdict"; tasks 8.1–8.4)."""

from __future__ import annotations

from typing import Any

from tests.conftest import Api
from tests.sessions.kit import assert_reduces, chars, command, create, events, ledger, messages, snapshot

PAIR = ["chr_seedAmara", "chr_seedVictor"]


async def _debate(api: Api, **cfg: Any) -> str:
    await api.set_key()
    config = {"motion": "This house would tax sugary drinks", "format": "two_sided",
              "sides": {"prop": ["chr_seedAmara"], "opp": ["chr_seedVictor"]}, "roundsPreset": "quick",
              "phases": ["opening", "closing"], "turnLength": "short", "moderator": "user", "verdictBy": "arbiter",
              "rubric": [], "autoAdvance": True, "pauseMs": 1500, **cfg}
    sid: str = (await create(api, "debate", PAIR, config=config))["session"]["id"]
    return sid


async def test_quick_debate_to_a_verdict(api: Api) -> None:
    sid = await _debate(api)
    await api.drive(90000)
    snap = await snapshot(api, sid)
    s, msgs = snap["session"], snap["messages"]
    assert s["status"] == "ended"
    assert len(chars(msgs)) == 4
    assert any(m["kind"] == "verdict" for m in msgs)
    assert s["state"]["phase"] == "ended" and s["state"]["verdict"]["decidedBy"] == "arbiter"
    # Speakers alternate prop/opp, marked round_order and tagged with phase, round and iteration.
    debate = [m["debate"] for m in chars(msgs)]
    assert [d["side"] for d in debate] == ["prop", "opp", "prop", "opp"]
    assert [(d["phase"], d["round"], d["iteration"]) for d in debate] == [
        ("opening", 1, 1), ("opening", 1, 1), ("closing", 2, 1), ("closing", 2, 1)]
    notes = [m["content"] for m in msgs if m["kind"] == "system_note"]
    assert notes[:2] == ["ROUND 1 · OPENING", "ROUND 2 · CLOSING"] and "ROUND 3 · VERDICT" in notes
    v = s["state"]["verdict"]
    assert v.get("strongerCase") in ("prop", "opp", None)
    assert all(0 <= x["value"] <= 10 for x in v.get("scores", []))
    assert any(r["purpose"] == "verdict" for r in await ledger(api))  # the arbiter verdict is a paid call
    nexts = [e for e in await events(api, sid) if e["type"] == "turn.next" and e["payload"].get("forcedBy")]
    assert all(e["payload"]["forcedBy"] == "round_order" for e in nexts)
    await assert_reduces(api, sid)


async def test_auto_host_narrates(api: Api) -> None:
    sid = await _debate(api, moderator="auto_host")
    await api.drive(5000)
    msgs = await messages(api, sid)
    narration = [m for m in msgs if m["kind"] == "narration"]
    assert narration and narration[0]["author"] == {"type": "host"} and "Opening statements" in narration[0]["content"]


async def test_pause_resume_next_and_auto_advance(api: Api) -> None:
    sid = await _debate(api, autoAdvance=False)
    await api.drive(15000)
    assert len(chars(await messages(api, sid))) == 1  # without auto-advance, one turn then wait
    await command(api, sid, "debate/next")
    await api.drive(15000)
    assert len(chars(await messages(api, sid))) == 2
    await command(api, sid, "debate/auto-advance", {"on": True})
    await command(api, sid, "debate/pause")
    await api.drive(30000)
    n = len(chars(await messages(api, sid)))
    assert (await snapshot(api, sid))["session"]["status"] == "paused"
    await command(api, sid, "debate/resume")
    await api.drive(60000)
    assert len(chars(await messages(api, sid))) > n
    assert (await snapshot(api, sid))["session"]["status"] == "ended"


async def test_extend_round_repeats_the_phase(api: Api) -> None:
    sid = await _debate(api)
    await api.drive(5000)
    await command(api, sid, "debate/extend-round")
    await api.drive(120000)
    msgs = chars(await messages(api, sid))
    phases = [(m["debate"]["phase"], m["debate"]["iteration"]) for m in msgs]
    assert phases[:4] == [("opening", 1), ("opening", 1), ("opening", 2), ("opening", 2)]
    assert "ROUND 1 · OPENING · EXTENDED" in [m["content"] for m in await messages(api, sid)]


async def test_skip_to_closing_lands_at_the_boundary(api: Api) -> None:
    sid = await _debate(api, phases=["opening", "rebuttal", "closing"], roundsPreset="standard")
    await api.drive(5000)
    await command(api, sid, "debate/skip-to-closing")
    await api.drive(120000)
    phases = [m["debate"]["phase"] for m in chars(await messages(api, sid))]
    assert "rebuttal" not in phases and phases[-1] == "closing"


async def test_ask_lands_at_the_boundary(api: Api) -> None:
    sid = await _debate(api, autoAdvance=False)
    for _ in range(40):
        await api.drive(250)
        if any(m["status"] == "streaming" for m in await messages(api, sid)):
            break
    streaming = next(m for m in await messages(api, sid) if m["status"] == "streaming")
    assert streaming["author"]["characterId"] == "chr_seedAmara"
    await command(api, sid, "debate/ask", {"characterId": "chr_seedVictor", "text": "Is a tax regressive?"})
    await api.drive(20000)
    msgs = await messages(api, sid)
    first = next(m for m in msgs if m["id"] == streaming["id"])
    assert first["status"] == "complete"  # the streaming reply finished
    steer = next(m for m in msgs if m["kind"] == "steer")
    answer = next(m for m in chars(msgs) if m["author"]["characterId"] == "chr_seedVictor")
    assert steer["targetCharacterId"] == "chr_seedVictor" and answer["seq"] > first["seq"]
    assert answer["forcedSpeaker"] is True
    assert answer["trace"]["routing"]["forcedBy"] == "user_ask"
    nxt = [e for e in await events(api, sid) if e["type"] == "turn.next" and e["payload"].get("forcedBy") == "user_ask"]
    assert nxt


async def test_interject_posts_a_message(api: Api) -> None:
    sid = await _debate(api, autoAdvance=False)
    await api.drive(3000)
    await command(api, sid, "debate/interject", {"text": "Keep it civil."})
    m = (await messages(api, sid))[-1]
    assert m["kind"] == "interject" and m["author"] == {"type": "user"} and m["debate"]["phase"] == "opening"
    await command(api, sid, "send", {"text": "Also: sources, please."})  # a send in a debate is an interjection
    assert (await messages(api, sid))[-1]["kind"] == "interject"


async def test_user_decides(api: Api) -> None:
    sid = await _debate(api, verdictBy="user")
    await api.drive(90000)
    snap = await snapshot(api, sid)
    assert snap["session"]["state"]["phase"] == "verdict" and snap["session"]["status"] == "active"
    await command(api, sid, "debate/pick", {"side": "prop"})
    snap = await snapshot(api, sid)
    v = snap["session"]["state"]["verdict"]
    assert v["decidedBy"] == "user" and v["strongerCase"] == "prop" and snap["session"]["status"] == "ended"
    await assert_reduces(api, sid)


async def test_end_with_and_without_a_verdict(api: Api) -> None:
    sid = await _debate(api)
    await api.drive(3000)
    await command(api, sid, "debate/end", {"withVerdict": False})
    await api.drive(20000)
    snap = await snapshot(api, sid)
    assert snap["session"]["status"] == "ended" and "verdict" not in snap["session"]["state"]
    other = await _debate(api, verdictBy="none", format="panel", sides=None)
    await api.drive(3000)
    await command(api, other, "debate/end", {"withVerdict": True})
    await api.drive(20000)
    v = (await snapshot(api, other))["session"]["state"]["verdict"]
    assert v["decidedBy"] in ("none", "arbiter") and v["strongerCase"] is None
