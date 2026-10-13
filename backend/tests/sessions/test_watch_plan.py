"""Watch under `agent`: who speaks next, the guard, the opening, the steer and the plan made ahead (group-watch tasks
6.2–6.5; design D13–D15; watch-direction spec). No network: Jev's answers come from the fake, with chosen answers
patched in per request."""

from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest

from horizon.domain.timeutil import ms_from_iso
from horizon.sessions.actor import SessionActor
from horizon.sessions.modes.common import message_event, note
from horizon.sessions.turn import TurnRunner
from horizon.sessions.watch_plan import fingerprint, guard, start_plan_ahead, take_plan
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
TRIO = [AMARA, MEI, VICTOR]
PREMISE = "A storm traps everyone at the inn."


def jev(api: Api, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Patch the fake's decisions: `fn(body)` returns answers to put in place of the fake's defaults."""
    fake = api.rt.fake
    assert fake is not None
    plain = fake._decide

    def decide(body: dict[str, Any]) -> httpx.Response:
        data = json.loads(plain(body).content)
        data["answers"].update(fn(body))
        return httpx.Response(200, json=data)

    fake._decide = decide  # type: ignore[method-assign]


def pick(c: str, conf: float = 0.9) -> dict[str, Any]:
    return {"type": "choice", "choice": c, "confidence": conf, "probabilities": {c: conf}}


def plan_bodies(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    out = []
    for r in api.rt.fake.requests:
        if r.url.path.endswith("/alpha/decisions"):
            body = json.loads(r.content)
            if any(k.startswith(("who_", "emotion_line", "emotion_opening", "talk_finished")) for k in body["questions"]):
                out.append(body)
    return out


async def agent_watch(api: Api, *, manual: bool = False, **config: Any) -> str:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    cfg = {"premise": PREMISE, "maxTurns": 20, "paceMs": 1500, **config}
    sid: str = (await create(api, "watch", TRIO, config=cfg))["session"]["id"]
    if manual:
        await command(api, sid, "set-emotion-mode", {"mode": "user"})
    return sid


def speakers(msgs: list[dict[str, Any]]) -> list[str]:
    return [m["author"]["characterId"] for m in chars(msgs)]


def rows(m: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    return [r for r in m["trace"]["system1"]["questions"] if r["id"] == qid]


async def drive_until(api: Api, cond: Callable[[], Any], step: float = 25, limit: float = 120000) -> None:
    spent = 0.0
    while spent < limit:
        if await cond():
            return
        await api.drive(step)
        spent += step
    raise AssertionError("condition never held")


async def replies(api: Api, sid: str, n: int, *, pause: bool = True) -> list[dict[str, Any]]:
    """Drive until `n` replies are complete (then pause the scene); the first `n`."""
    async def done() -> bool:
        return len([m for m in chars(await messages(api, sid)) if m["status"] == "complete"]) >= n

    await drive_until(api, done, step=100, limit=600000)
    if pause:
        await command(api, sid, "watch/pause")
        await api.drive(30000)
    return chars(await messages(api, sid))[:n]


# ── 6.2: who speaks next ──
async def test_never_twice_in_a_row_even_when_jev_favours_the_last_speaker(api: Api) -> None:
    sid = await agent_watch(api, maxTurns=40, paceMs=500)
    actor: SessionActor = await api.rt.sessions.get(sid)

    def favour_last(body: dict[str, Any]) -> dict[str, Any]:
        lines = [m for m in actor.state["messages"].values() if m["author"]["type"] == "character"]
        if "who_scene" not in body["questions"] or not lines:
            return {}
        return {"who_scene": pick(str(max(lines, key=lambda m: m["seq"])["author"]["characterId"]))}

    jev(api, favour_last)
    who = speakers(await replies(api, sid, 30))
    assert all(a != b for a, b in itertools.pairwise(who))


async def _without_mei(api: Api, n: int = 7) -> tuple[str, list[dict[str, Any]]]:
    sid = await agent_watch(api, maxTurns=10, paceMs=500)

    def never_mei(body: dict[str, Any]) -> dict[str, Any]:
        q = body["questions"].get("who_scene")
        if q is None:
            return {}
        crit = list(q["criteria"])
        return {"who_scene": pick(AMARA if AMARA in crit else VICTOR)}

    jev(api, never_mei)
    return sid, await replies(api, sid, n)


async def test_the_guard_fires_with_its_reason_and_no_who_row(api: Api) -> None:
    sid, msgs = await _without_mei(api)
    assert speakers(msgs) == [AMARA, VICTOR, AMARA, VICTOR, AMARA, VICTOR, MEI]
    mei = msgs[-1]
    assert mei["trace"]["routing"]["forcedBy"] == "round_order"
    assert mei["trace"]["routing"]["reason"] == "Mei hadn't spoken for 6 turns."
    assert rows(mei, "who_scene") == [] and len(rows(mei, "talk_finished")) == 1
    evs = await events(api, sid)
    nxt = [e for e in evs if e["type"] == "turn.next"][6]
    assert nxt["payload"] == {"nextSpeakerId": MEI, "forcedBy": "round_order"}


async def test_the_guard_survives_a_release(api: Api) -> None:
    from horizon.services.runtime.reducer import ordered_messages

    sid, _ = await _without_mei(api, 6)
    actor: SessionActor = await api.rt.sessions.get(sid)
    before = guard(ordered_messages(actor.state), TRIO)
    await api.rt.sessions.release(sid, actor)
    rebuilt: SessionActor = await api.rt.sessions.get(sid)
    assert rebuilt is not actor
    assert guard(ordered_messages(rebuilt.state), TRIO) == before == (MEI, 6)


async def test_naive_stays_round_robin(api: Api) -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    sid: str = (await create(api, "watch", TRIO, config={"premise": PREMISE, "maxTurns": 10, "paceMs": 500,
                                                          "openingSpeaker": MEI}))["session"]["id"]
    assert speakers(await replies(api, sid, 6)) == [MEI, VICTOR, AMARA, MEI, VICTOR, AMARA]
    assert plan_bodies(api) == []


# ── 6.3: the opening ──
async def test_auto_opening_asks_who_scene_and_opening_faces_without_talk_finished(api: Api) -> None:
    sid = await agent_watch(api, maxTurns=10)
    jev(api, lambda b: {"who_scene": pick(VICTOR)} if "who_scene" in b["questions"] else {})
    first = await replies(api, sid, 1)
    body = plan_bodies(api)[0]
    assert set(body["questions"]) == {"who_scene", *(f"emotion_opening:{c}" for c in TRIO)}
    assert "none" not in body["questions"]["who_scene"]["criteria"]
    assert speakers(first) == [VICTOR]


async def test_a_chosen_opening_speaker_is_forced(api: Api) -> None:
    sid = await agent_watch(api, maxTurns=10, openingSpeaker=MEI)
    first = await replies(api, sid, 1)
    assert list(plan_bodies(api)[0]["questions"]) == [f"emotion_opening:{MEI}"]
    assert speakers(first) == [MEI]


# ── 6.4: the steer ──
def cues(monkeypatch: Any) -> list[Any]:
    seen: list[Any] = []
    stream = TurnRunner._stream

    async def spy(self: TurnRunner, actor: Any, spec: Any, info: Any, ctx: Any, *a: Any, **k: Any) -> Any:
        seen.append(ctx.plan.cue if ctx.plan is not None else None)
        return await stream(self, actor, spec, info, ctx, *a, **k)

    monkeypatch.setattr(TurnRunner, "_stream", spy)
    return seen


def finished(p: float) -> Callable[[dict[str, Any]], dict[str, Any]]:
    return lambda b: {"talk_finished": {"type": "noul", "noul": p}} if "talk_finished" in b["questions"] else {}


async def test_steer_then_cap(api: Api, monkeypatch: Any) -> None:
    seen = cues(monkeypatch)
    sid = await agent_watch(api, maxTurns=10, paceMs=500)
    jev(api, finished(0.9))
    msgs = await replies(api, sid, 5)
    actions = [rows(m, "talk_finished")[0]["action"] if rows(m, "talk_finished") else None for m in msgs]
    assert actions == [None, "steer", "no steer (steered recently)", "no steer (steered recently)", "steer"]
    assert seen[:5] == [None, "steer", None, None, "steer"]
    row = rows(msgs[1], "talk_finished")[0]
    assert (row["answer"], row["p"], row["result"]) == ("yes", 0.9, "used")
    assert row["compared"] == [{"name": "t_end", "value": 0.9, "threshold": 0.8}]


async def test_no_steer_during_a_directors_note(api: Api, monkeypatch: Any) -> None:
    seen = cues(monkeypatch)
    sid = await agent_watch(api, maxTurns=10, paceMs=1500)
    jev(api, finished(0.95))

    async def opened() -> bool:
        return len(chars(await messages(api, sid))) == 1

    await drive_until(api, opened)
    await command(api, sid, "watch/direct", {"text": "The lights go out."})
    msgs = await replies(api, sid, 2)
    assert rows(msgs[1], "talk_finished")[0]["action"] == "no steer (director's note)"
    assert seen[1] is None


# ── 6.5: the plan made ahead ──
async def _until_turn_end(api: Api, sid: str, n: int) -> dict[str, Any]:
    async def ended() -> bool:
        return len([e for e in await events(api, sid) if e["type"] == "turn.end"]) >= n

    await drive_until(api, ended, step=10)
    return [e for e in await events(api, sid) if e["type"] == "turn.end"][n - 1]


def cancelled_plans(rows_: list[dict[str, Any]]) -> int:
    return len([r for r in rows_ if r["purpose"] == "turn_plan" and r["finish_reason"] == "cancelled"])


async def test_hidden_by_the_pace(api: Api) -> None:
    """MANUAL (no reactions, no face check), so the only decisions are plans: call 1 opens, call 2 is made ahead."""
    sid = await agent_watch(api, manual=True, maxTurns=10, paceMs=1500)
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)
    end = await _until_turn_end(api, sid, 1)
    t_end = ms_from_iso(end["at"])
    await api.drive(1200 - (ms_from_iso(api.rt.now_iso()) - t_end))
    release.set()                                             # Jev answers 1.2 s after turn.end
    second = (await replies(api, sid, 2))[1]
    assert cancelled_plans(await ledger(api)) == 0            # no redo
    assert not [c for c in second["trace"]["calls"] if c["purpose"] == "turn_plan" and c.get("fallback")]
    nxt = [e for e in await events(api, sid) if e["type"] == "turn.next"][1]
    assert 1900 <= ms_from_iso(nxt["at"]) - t_end < 1950    # when the pace timer fires (gap 400 + pace 1500)


async def test_none_at_the_limit_and_one_request_per_turn(api: Api) -> None:
    """Nothing changes between turns: each turn makes exactly one plan request, and the last makes none ahead."""
    sid = await agent_watch(api, manual=True, maxTurns=10, paceMs=500)
    for _ in range(20):
        await api.drive(30000)
    assert len(chars(await messages(api, sid))) == 10 and len(plan_bodies(api)) == 10
    assert cancelled_plans(await ledger(api)) == 0


async def test_a_directors_note_in_the_gap_redoes_the_plan(api: Api) -> None:
    """Jev hasn't answered the plan made ahead when a director's note lands: the turn finds the fingerprint changed and
    plans again, and uses that plan (its call is no fallback)."""
    sid = await agent_watch(api, manual=True, maxTurns=10, paceMs=1500)
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)   # the plan made ahead
    await _until_turn_end(api, sid, 1)
    await api.drive(100)
    await command(api, sid, "watch/direct", {"text": "The lights go out."})
    second = (await replies(api, sid, 2))[1]
    release.set()
    await api.drive(2000)
    bodies = plan_bodies(api)
    assert [sorted(b["questions"]) for b in bodies[1:3]] == [sorted(bodies[1]["questions"])] * 2   # ahead, then redone
    # the stored plan was never used: it ran out at the due time (`late`), the moment the turn found it stale
    finish = [r["finish_reason"] for r in await ledger(api) if r["purpose"] == "turn_plan"]
    assert finish.count("late") == 1 and "cancelled" not in finish
    assert rows(second, "talk_finished")[0]["action"] in ("no steer (director's note)", "no steer")
    assert not [c for c in second["trace"]["calls"] if c["purpose"] == "turn_plan" and c.get("fallback")]


async def test_stop_during_the_gap_cancels_the_plan_made_ahead(api: Api) -> None:
    from tests.helpers.storm import assert_writer_free

    sid = await agent_watch(api, manual=True, maxTurns=10, paceMs=1500)
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)
    await _until_turn_end(api, sid, 1)
    await api.drive(100)
    await command(api, sid, "stop")
    await api.drive(10000)
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["finish_reason"] == "cancelled"
    assert len([e for e in await events(api, sid) if e["type"] == "turn.next"]) == 1
    msgs = chars(await messages(api, sid))
    assert len(msgs) == 1 and not rows(msgs[0], "who_scene")[1:]   # the cancelled plan wrote no rows anywhere
    await assert_writer_free(api.rt.db)
    await assert_reduces(api, sid)


# each change to one of D15's inputs forces a redo; none uses the stored plan
async def _mute(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    await command(api, sid, "mute", {"characterId": MEI, "muted": True})


async def _face(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    await command(api, sid, "set-emotion", {"characterId": MEI, "emotion": "happy"})


async def _mode(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    await command(api, sid, "set-emotion-mode", {"mode": "user"})


async def _awake(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    from horizon.sessions import watch_plan

    plain = watch_plan.is_asleep  # type: ignore[attr-defined]

    async def asleep(a: Any, cid: str) -> bool:
        return cid == MEI or await plain(a, cid)

    mp.setattr(watch_plan, "is_asleep", asleep)


async def _note_line(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    await actor.emit(message_event(note(actor, "The fire crackles.")))


async def _clear_epoch(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    actor.mode_epoch_bump()


async def _reply_epoch(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    await actor.supersede()


async def _direction(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    actor.mode.direction = ("Rain starts.", 2)


async def _nudge(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    actor.mode.nudge = MEI


async def _nothing(api: Api, sid: str, actor: SessionActor, mp: Any) -> None:
    return None


@pytest.mark.parametrize(("change", "redo"), [
    (_clear_epoch, True), (_reply_epoch, True), (_note_line, True), (_direction, True), (_nudge, True),
    (_mode, True), (_awake, True), (_mute, True), (_face, True), (_nothing, False)],
    ids=["clear epoch", "reply epoch", "last message", "director's note", "nudge", "emotion mode", "awake", "muted",
         "face", "unchanged"])
async def test_each_fingerprint_field_forces_a_redo(api: Api, monkeypatch: Any, change: Any, redo: bool) -> None:
    sid = await agent_watch(api, maxTurns=20, paceMs=1500)
    await _until_turn_end(api, sid, 1)
    await command(api, sid, "watch/pause")                    # nothing else runs; the pause dropped any plan made ahead
    await api.drive(5000)
    actor: SessionActor = await api.rt.sessions.get(sid)
    assert actor.mode.plan_ahead is None
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 1)
    await start_plan_ahead(actor, api.rt.clock.now() + timedelta(seconds=10))
    await api.drive(50)
    assert actor.mode.plan_ahead is not None
    fp, stored = actor.mode.plan_ahead
    n = len(plan_bodies(api))
    await change(api, sid, actor, monkeypatch)
    assert (fp != await fingerprint(actor)) is redo
    task = api.rt.spawn("take", take_plan(actor))
    await asyncio.sleep(0)
    await api.drive(1000)
    release.set()
    await api.drive(10000)
    plan, _ = await task
    assert plan is not None
    assert stored.cancelled() is redo
    assert len(plan_bodies(api)) == n + (1 if redo else 0)
