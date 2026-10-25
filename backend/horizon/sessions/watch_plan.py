"""Who speaks next in an `agent` watch, the steer, and the plan made ahead (M10; doc 07 G6, G7, G8; group-watch design
D13, D14, D15; watch-direction spec).

Per watch turn, under a planner that plans the cast: a Speak next nudge, else the nobody-left-out guard, else Jev's
`who_scene` over the awake, unmuted cast minus the last speaker. Everything here is read from the stored message log and
traces in `actor.state`, never from `ModeState` counters, so an idle release changes nothing (G6, D14).

The plan for the next turn starts right after a turn's `turn.end` (`actor.background("plan_ahead")`) and may wait for
Jev until that turn is due. It is stored with a fingerprint of its inputs; at turn time a different fingerprint
cancels it (ledger outcome `cancelled`) and the turn plans again with the normal deadline. M12 (rag D15): when the plan
made ahead picks a speaker whose gate says yes, their deep work starts as soon as the plan lands and is stored with
it; a stale plan cancels both.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import CastKind, CastPlan, SteerBlock
from horizon.domain import vclock
from horizon.sessions.modes.common import is_asleep, name_of, runner
from horizon.sessions.plans import cast_request, plan_cast

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

log = logging.getLogger("horizon.sessions")

Wire = dict[str, Any]
ROUNDS = 2            # G6: silent for 2 full rounds goes next (a code constant, not a knob: D13)
STEER_WINDOW = 2      # G7 / D14: at most one steer every 3 turns (none in the last 2 character messages)
PLAN_AHEAD = "plan_ahead"


# ── pure rules over the stored log ──
def scene_start(messages: Sequence[Mapping[str, Any]]) -> int:
    """The seq of the premise: the first `direction` message authored by the system (0 when there is none)."""
    for m in messages:
        if m.get("kind") == "direction" and m["author"]["type"] == "system":
            return int(m["seq"])
    return 0


def scene_lines(messages: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Character messages since the scene start: scene turns, Step turns and Step in replies count; director's notes
    and system notes don't (D13)."""
    start = scene_start(messages)
    return [m for m in messages if m["author"]["type"] == "character" and int(m["seq"]) > start]


def guard(messages: Sequence[Mapping[str, Any]], awake: Sequence[str]) -> tuple[str, int] | None:
    """G6: (who, k) when a character qualifies: at least `2n` character lines since the scene start and none of the
    last `2n` theirs, `n` the awake, unmuted characters now. Several: the one silent longest (never spoken first, then
    the oldest last line, then cast order). `k` is the character lines since their last one (or since the start)."""
    n = len(awake)
    lines = scene_lines(messages)
    if n == 0 or len(lines) < ROUNDS * n:
        return None
    recent = {m["author"].get("characterId") for m in lines[-ROUNDS * n:]}
    qualify = [c for c in awake if c not in recent]
    if not qualify:
        return None
    last: dict[str, int] = {}
    for i, m in enumerate(lines):
        last[str(m["author"].get("characterId"))] = i
    order = {c: i for i, c in enumerate(awake)}
    who = min(qualify, key=lambda c: (c in last, last.get(c, -1), order[c]))
    k = len(lines) - 1 - last[who] if who in last else len(lines)
    return who, k


def steered_recently(messages: Sequence[Mapping[str, Any]]) -> bool:
    """D14's cap, from the stored traces: one of the last 2 character messages steered."""
    for m in [m for m in messages if m["author"]["type"] == "character"][-STEER_WINDOW:]:
        rows = (((m.get("trace") or {}).get("system1") or {}).get("questions")) or []
        if any(r.get("id") == "talk_finished" and r.get("action") == "steer" for r in rows):
            return True
    return False


# ── the request ──
@dataclass(frozen=True)
class ScenePick:
    """What a planned scene turn needs besides the plan: how its speaker was chosen."""

    kind: CastKind
    forced: str | None = None
    forced_by: str | None = None
    reason: str | None = None


def _ordered(actor: SessionActor) -> list[Wire]:
    from horizon.services.runtime.reducer import ordered_messages

    out: list[Wire] = ordered_messages(actor.state)
    return out


def note_active(actor: SessionActor) -> bool:
    d = actor.mode.direction
    return d is not None and d[1] > 0


async def awake_cast(actor: SessionActor) -> list[str]:
    return [p["characterId"] for p in actor.session["participants"]
            if not p.get("mutedByUser") and await runner(actor).energy_now(p["characterId"]) is not None
            and not await is_asleep(actor, p["characterId"])]


async def latest_line(actor: SessionActor, messages: Sequence[Mapping[str, Any]]) -> str:
    """The line the next speaker follows ("Name: line", or the user's own words); "" at the opening."""
    start = scene_start(messages)
    for m in reversed(messages):
        if int(m["seq"]) <= start:
            break
        kind = m["author"]["type"]
        if m.get("content") and kind in ("character", "user") and m.get("kind") != "direction":
            if kind == "user":
                return str(m["content"])
            return f"{await name_of(actor, str(m['author']['characterId']))}: {m['content']}"
    return ""


async def plan_scene(actor: SessionActor, *, deadline_at: datetime | None = None) -> tuple[CastPlan | None, ScenePick]:
    """D13's order for the next scene turn, then its cast plan. Pure over the actor's state: nothing is consumed here
    (the nudge is cleared by the turn that uses it), so a plan made ahead and a plan made now agree."""
    msgs = _ordered(actor)
    awake = await awake_cast(actor)
    if not awake:
        return None, ScenePick(kind="scene")
    start = scene_start(msgs)
    opening = not scene_lines(msgs)
    kind: CastKind = "opening" if opening else "scene"
    block: SteerBlock | None = None if opening else ("note" if note_active(actor) else
                                                     "recent" if steered_recently(msgs) else None)
    latest = "" if opening else await latest_line(actor, msgs)
    nudge = actor.mode.nudge
    pick: ScenePick
    if nudge:
        pick = ScenePick(kind=kind, forced=nudge, forced_by="nudge")
    elif opening:
        chosen = (actor.session.get("config") or {}).get("openingSpeaker", "auto")
        pick = ScenePick(kind=kind, forced=str(chosen) if chosen not in (None, "auto") and chosen in awake else None,
                         forced_by="opening" if chosen not in (None, "auto") and chosen in awake else None)
    elif (g := guard(msgs, awake)) is not None:
        who, k = g
        pick = ScenePick(kind=kind, forced=who, forced_by="round_order",
                         reason=f"{await name_of(actor, who)} hadn't spoken for {k} turns.")
    else:
        pick = ScenePick(kind=kind)
    if pick.forced is not None:
        req = await cast_request(actor, kind, [], forced=[pick.forced], forced_by=pick.forced_by, reason=pick.reason,
                                 latest=latest, steer_block=block, scene_start=start, deadline_at=deadline_at)
        return await plan_cast(actor, req), pick
    last = next((m["author"].get("characterId") for m in reversed(msgs) if m["author"]["type"] == "character"), None)
    cands = [c for c in awake if c != last] or awake   # one awake character in all continues alone
    req = await cast_request(actor, kind, cands, latest=latest, steer_block=block, scene_start=start,
                             deadline_at=deadline_at)
    return await plan_cast(actor, req), pick


# ── the plan made ahead (D15) ──
async def fingerprint(actor: SessionActor) -> tuple[Any, ...]:
    """D15's exact list: the clear epoch, the reply epoch, the last message's seq, the director's note and its turns
    left, the nudge, the emotion mode, and per participant in cast order: ID, awake, muted, the face now."""
    msgs = _ordered(actor)
    parts = []
    for p in actor.session["participants"]:
        cid = p["characterId"]
        parts.append((cid, not await is_asleep(actor, cid), bool(p.get("mutedByUser")), p.get("currentEmotion")))
    return (actor.epoch, actor.reply_epoch, int(msgs[-1]["seq"]) if msgs else 0, actor.mode.direction,
            actor.mode.nudge, actor.session.get("emotionMode"), tuple(parts))


async def _plan_ahead(actor: SessionActor, due: datetime, holder: list[Any]) -> tuple[CastPlan | None, ScenePick]:
    """The plan made ahead, then (M12) its speaker's deep work, started at once and kept in `holder`."""
    plan, pick = await plan_scene(actor, deadline_at=due)
    if plan is not None and plan.order:
        from horizon.ai.contexts import LineHint
        from horizon.sessions.deep import attach
        from horizon.sessions.turn import TurnSpec

        spec = TurnSpec(speaker=plan.order[0], line=LineHint(kind="scene"))
        spec.plan = plan.for_speaker(plan.order[0])
        await attach(actor, spec)
        if spec.deep is not None:
            holder.append(spec.deep)
    return plan, pick


async def start_plan_ahead(actor: SessionActor, due: datetime) -> None:
    """Start the next turn's plan now, waiting for Jev until `due` (the next turn's start), and store it."""
    fp = await fingerprint(actor)
    holder: list[Any] = []
    task = actor.background(PLAN_AHEAD, _plan_ahead(actor, due, holder))
    actor.mode.plan_ahead = (fp, task, holder)


def _drop_deep(holder: list[Any]) -> None:
    for call in holder:
        call.cancel()   # M12: its Jev calls are recorded `cancelled`
    holder.clear()


async def take_plan(actor: SessionActor) -> tuple[CastPlan | None, ScenePick, Any]:
    """At turn time: the stored plan (and its speaker's deep work) when its fingerprint still matches; else cancel
    both and plan now (700 ms)."""
    stored, actor.mode.plan_ahead = actor.mode.plan_ahead, None
    if stored is not None:
        fp, task, holder = stored
        if fp == await fingerprint(actor) and not task.cancelled():
            try:
                got: tuple[CastPlan | None, ScenePick] = await vclock.join(task)
                return got[0], got[1], holder[0] if holder else None
            except asyncio.CancelledError:
                if not task.cancelled():
                    raise
            except Exception:
                log.exception("the plan made ahead failed in %s; planning now", actor.sid)
            _drop_deep(holder)
        else:
            actor.cancel_background(PLAN_AHEAD)
            _drop_deep(holder)
    plan, pick = await plan_scene(actor)
    return plan, pick, None


def drop_deep_ahead(actor: SessionActor) -> None:
    """A change that spoils the plan made ahead (a director's note): its deep work goes now; the plan is left to the
    turn's fingerprint check (M10 D15)."""
    if actor.mode.plan_ahead is not None:
        _drop_deep(actor.mode.plan_ahead[2])


def drop_plan_ahead(actor: SessionActor) -> None:
    """Pause and clear: the plan made ahead and its deep work go."""
    stored, actor.mode.plan_ahead = actor.mode.plan_ahead, None
    actor.cancel_background(PLAN_AHEAD)
    if stored is not None:
        _drop_deep(stored[2])
