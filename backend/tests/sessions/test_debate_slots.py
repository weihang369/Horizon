"""A debate phase as slots, and a side with nobody awake (M11; doc 08 V1, V3, V5; debate design D3, D4; tasks 2.1–2.6;
session-modes "Debate phases", "A side with nobody awake pauses the debate", "The verdict knows the missed turns")."""

from __future__ import annotations

from typing import Any

from sqlalchemy import update

from horizon.db import tables as t
from horizon.sessions.debate_slots import Fill, cursor, fill, missed_sentence, missed_turns, phase_slots
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, messages, snapshot

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
TWO_V_ONE = {"format": "two_sided", "sides": {"prop": [AMARA, MEI], "opp": [VICTOR]}}


# ── pure rules ──
def test_slots_alternate_sides_and_a_panel_has_one_per_panellist() -> None:
    assert phase_slots({"format": "two_sided", "sides": {"prop": ["a", "b"], "opp": ["c", "d"]}}, "abcd") == \
        ["prop", "opp", "prop", "opp"]
    assert phase_slots(TWO_V_ONE, [AMARA, MEI, VICTOR]) == ["prop", "opp", "prop"]
    assert phase_slots({"format": "panel"}, ["a", "b", "c"]) == [None, None, None]


def test_the_fill_rule() -> None:
    awake = {"a": True, "b": True}
    assert fill(["a", "b"], [], awake) == Fill("speak", who="a", eligible=("a", "b"))
    assert fill(["a", "b"], ["a"], awake).who == "b"
    assert fill(["a", "b"], ["a"], {"a": True, "b": False}) == Fill("skip", who="b", asleep=("b",))
    assert fill(["a", "b"], [], {"a": False, "b": True}).who == "b"   # the asleep member's turn moves later
    assert fill(["a", "b"], [], {"a": False, "b": False}) == Fill("pause", asleep=("a", "b"))


def _m(seq: int, author: str, kind: str = "chat", content: str = "x", **kw: Any) -> dict[str, Any]:
    a = {"type": "character", "characterId": author} if author.startswith("chr") else {"type": author}
    return {"seq": seq, "author": a, "kind": kind, "content": content, **kw}


def test_the_cursor_counts_arguments_and_skips_since_the_banner() -> None:
    log = [_m(1, "system", "system_note", "ROUND 1 · OPENING"), _m(2, AMARA), _m(3, VICTOR),
           _m(4, "system", "system_note", "ROUND 2 · CLOSING"), _m(5, AMARA),
           _m(6, "user", "steer", "Victor, why?"), _m(7, VICTOR, forcedSpeaker=True),
           _m(8, "system", "system_note", "Mei is asleep, skipping.", targetCharacterId=MEI)]
    c = cursor(log)
    assert (c.used, c.heard, c.start_seq) == (2, (AMARA,), 4)   # the Ask answer is no slot


def test_missed_turns_by_side_and_reason() -> None:
    log = [_m(1, "system", "system_note", "ROUND 1 · OPENING"), _m(2, AMARA), _m(3, VICTOR), _m(4, MEI),
           _m(5, "system", "system_note", "ROUND 2 · CLOSING"), _m(6, AMARA),
           _m(7, "system", "system_note", "Victor is asleep (⚡ 0).", targetCharacterId=VICTOR)]
    missed = missed_turns(log, TWO_V_ONE, [AMARA, MEI, VICTOR])
    assert missed == {"prop": {"missed": 1, "reason": "the debate ended early"}, "opp": {"missed": 1, "reason": "asleep"}}
    assert missed_sentence(missed) == ("Proposition: 1 turn missed, the debate ended early; "
                                       "Opposition: 1 turn missed, everyone on that side was asleep")


# ── the runtime ──
async def debate(api: Api, *, cast: list[str] | None = None, **cfg: Any) -> str:
    await api.set_key()
    config = {"motion": "This house would tax sugary drinks", **TWO_V_ONE, "roundsPreset": "quick",
              "phases": ["opening", "closing"], "turnLength": "short", "moderator": "user", "verdictBy": "none",
              "rubric": [], "autoAdvance": True, "pauseMs": 1500, **cfg}
    sid: str = (await create(api, "debate", cast or [AMARA, MEI, VICTOR], config=config))["session"]["id"]
    return sid


async def drain(api: Api, *cids: str) -> None:
    async with api.rt.db.write() as tx:
        for cid in cids:
            await tx.conn.execute(update(t.characters).where(t.characters.c.id == cid).values(
                energy_current=0.0, energy_as_of=api.rt.now_iso()))


async def top_up(api: Api, cid: str) -> None:
    assert (await api.post(f"{API}/characters/{cid}/energy/top-up", {"points": 500})).status_code == 200


def speakers(msgs: list[dict[str, Any]]) -> list[str]:
    return [m["author"]["characterId"] for m in chars(msgs)]


async def test_fixed_order_while_everyone_is_awake(api: Api) -> None:
    sid = await debate(api)
    await api.drive(120000)
    msgs = await messages(api, sid)
    assert speakers(msgs) == [AMARA, VICTOR, MEI, AMARA, VICTOR, MEI]
    await assert_reduces(api, sid)


async def test_a_side_heard_already_skips_the_slot(api: Api) -> None:
    await drain(api, MEI)
    sid = await debate(api, phases=["opening"])
    await api.drive(60000)
    msgs = await messages(api, sid)
    assert speakers(msgs) == [AMARA, VICTOR]
    skip = [m for m in msgs if m["content"] == "Mei is asleep, skipping."]
    assert len(skip) == 1 and skip[0]["debate"]["phase"] == "opening"
    assert (await snapshot(api, sid))["session"]["status"] == "ended"


async def test_a_side_with_nobody_awake_pauses_and_keeps_the_slot(api: Api) -> None:
    await drain(api, VICTOR)
    sid = await debate(api)
    await api.drive(20000)
    snap = await snapshot(api, sid)
    msgs = snap["messages"]
    assert speakers(msgs) == [AMARA]
    assert any(m["content"].startswith("Victor is asleep (⚡") for m in msgs)
    assert any(m["content"] == "The Opposition is asleep. Top someone up to continue the debate." for m in msgs)
    assert snap["session"]["status"] == "paused"
    evs = await events(api, sid)
    assert [e["payload"]["reason"] for e in evs if e["type"] == "session.paused"] == ["user"]
    assert any(e["type"] == "error" and e["payload"]["code"] == "energy_exhausted" for e in evs)

    await command(api, sid, "debate/resume")   # play without a top-up: the same notes again
    await api.drive(5000)
    msgs = await messages(api, sid)
    assert len([m for m in msgs if m["content"].startswith("The Opposition is asleep")]) == 2
    assert speakers(msgs) == [AMARA]

    await top_up(api, VICTOR)
    await command(api, sid, "debate/resume")
    await api.drive(60000)
    msgs = await messages(api, sid)
    assert speakers(msgs)[:3] == [AMARA, VICTOR, MEI]   # the kept slot ran with Victor
    await assert_reduces(api, sid)


async def test_the_cursor_survives_an_idle_release(api: Api) -> None:
    sid = await debate(api, autoAdvance=False)
    await api.drive(15000)
    await command(api, sid, "debate/next")
    await api.drive(15000)
    assert speakers(await messages(api, sid)) == [AMARA, VICTOR]
    actor = await api.rt.sessions.get(sid)
    await api.rt.sessions.release(sid, actor)
    await command(api, sid, "debate/next")
    await api.drive(15000)
    assert speakers(await messages(api, sid)) == [AMARA, VICTOR, MEI]   # the third slot, not the first again


async def test_an_announced_member_asleep_at_turn_start_gives_way(api: Api) -> None:
    """In the closing (openings are prefetched, and a prefetched opening speaks: its energy was drawn when it started)."""
    sid = await debate(api, cast=[AMARA, MEI, VICTOR], format="panel", sides=None, autoAdvance=False)
    await api.drive(15000)
    for _ in range(4):   # the other two openings, the boundary, the closing's first slot
        await command(api, sid, "debate/next")
        await api.drive(15000)
    assert speakers(await messages(api, sid)) == [AMARA, MEI, VICTOR, AMARA]
    nexts = [e for e in await events(api, sid) if e["type"] == "turn.next"]
    assert nexts[-1]["payload"]["nextSpeakerId"] == MEI
    await drain(api, MEI)
    await command(api, sid, "debate/next")
    await api.drive(15000)
    msgs = await messages(api, sid)
    assert speakers(msgs) == [AMARA, MEI, VICTOR, AMARA, VICTOR]
    fresh = [e for e in await events(api, sid) if e["type"] == "turn.next"][-1]
    assert fresh["payload"] == {"nextSpeakerId": VICTOR, "forcedBy": "round_order",
                                "skipped": [{"characterId": MEI, "reason": "exhausted"}]}
    victor = chars(msgs)[-1]
    assert victor["trace"]["routing"].get("skipped") == [{"characterId": MEI, "reason": "exhausted"}]
    await assert_reduces(api, sid)


async def test_an_auto_advance_debate_loaded_mid_round_goes_on_after_its_first_command(api: Api) -> None:
    """U-43: the chain lived only in the released actor's timer; the loaded actor's first command (an Ask) re-arms it
    after the answer, and the debate runs to its end in order."""
    sid = await debate(api)
    await api.drive(20000)
    before = speakers(await messages(api, sid))
    assert 1 <= len(before) < 6
    actor = await api.rt.sessions.get(sid)
    await api.rt.sessions.release(sid, actor)   # a restart or an idle release: the timer goes with the actor
    await api.drive(20000)
    assert speakers(await messages(api, sid)) == before   # nothing moves without a command
    await command(api, sid, "debate/ask", {"characterId": MEI, "text": "Mei, give us a number."})
    await api.drive(120000)
    msgs = await messages(api, sid)
    turns = [m for m in chars(msgs) if not m.get("forcedSpeaker")]
    assert [m["author"]["characterId"] for m in turns] == [AMARA, VICTOR, MEI, AMARA, VICTOR, MEI]
    assert len([m for m in chars(msgs) if m.get("forcedSpeaker")]) == 1   # the answer, once
    assert (await snapshot(api, sid))["session"]["status"] == "ended"
    await assert_reduces(api, sid)


async def test_a_fresh_debate_first_command_does_not_start_a_second_chain(api: Api) -> None:
    sid = await debate(api)
    await api.drive(3000)
    await command(api, sid, "debate/interject", {"text": "Numbers, please."})
    await api.drive(120000)
    assert speakers(await messages(api, sid)) == [AMARA, VICTOR, MEI, AMARA, VICTOR, MEI]
