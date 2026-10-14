"""The debate plan through the runtime (M11; doc 08 V2, V3; doc 13 W1, W11; debate design D5, D6, D8, D27; debate-plan
spec).

After an argument's `turn.end`, the next rebuttal, closing or panel slot of the phase gets its plan at once: with two or
more eligible members the member is fixed by `turn.end` + the `debate_plan` deadline (which replaces the turn gap) and
`turn.next` names them; with one, the turn gap and `turn.next` are as before and the request carries only the face.
The request keeps running through the pause; the turn reads its faces when it starts.

A plan is stored with a fingerprint (M10 D15's, with V2's seq rule: only character and user messages count) and the
(phase, iteration) it was made for. At the turn's start a match uses it; a mismatch keeps the announced member and asks
the face again. `clear()` cancels it (the named background task `debate_plan`); Pause drops it. The plan made at a
phase's last `turn.end` for the next phase's first slot is used only if that phase opens.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import DebateFacts, DebatePlan, DebateRequest, SessionContext
from horizon.sessions.context import character_view, characters, document_titles, session_context
from horizon.sessions.debate_slots import is_argument
from horizon.sessions.modes.common import is_asleep
from horizon.sessions.plans import base_faces, manual

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]
NAME = "debate_plan"
LATE = "debate_plan_late"


@dataclass
class Stored:
    fp: tuple[Any, ...]
    slot: int
    target: tuple[str, int]
    call: Any                       # the planner's DebateCall (None for an opening's face plan)
    asked: bool                     # a member question was asked (two or more eligible)
    member: DebatePlan | None = None
    used: bool = False              # a turn has read it: its call is no longer the hold's to cancel
    speaker: str | None = None      # an opening's face plan: whose
    face_task: asyncio.Task[Any] | None = None   # an opening's face plan (`plan_cast(debate_opening)`)


def _ordered(actor: SessionActor) -> list[Wire]:
    from horizon.services.runtime.reducer import ordered_messages

    out: list[Wire] = ordered_messages(actor.state)
    return out


def facts(actor: SessionActor, sctx: SessionContext, phase: str, side: str | None,
          candidates: list[str]) -> tuple[DebateFacts, str]:
    """D6: the motion, the phase and side, the last argument by the other side (by anyone else in a panel), each
    candidate's latest argument; and the argument just made ("Name: text"), which `emotion_line` reads."""
    names = {p.character_id: p.name for p in sctx.participants}
    sides = {p.character_id: p.side for p in sctx.participants}
    motion = str((actor.session.get("config") or {}).get("motion", ""))
    return facts_from(_ordered(actor), names, sides, motion, phase, side, candidates)


def facts_from(msgs: list[Wire], names: dict[str, str], sides: dict[str, str | None], motion: str, phase: str,
               side: str | None, candidates: list[str]) -> tuple[DebateFacts, str]:
    """`facts` over a message list: pure, so the member slice cuts a committed history with the live code (D21)."""
    args = [m for m in msgs if is_argument(m)]

    def said(m: Wire) -> str:
        cid = str(m["author"].get("characterId"))
        return f"{names.get(cid, cid)}: {m.get('content', '')}"

    if side is None:
        opposing = args[-1] if args else None
    else:
        opposing = next((m for m in reversed(args) if sides.get(str(m["author"].get("characterId"))) not in (None, side)),
                        None)
    latest_by: dict[str, str] = {}
    for cid in candidates:
        mine = next((m for m in reversed(args) if m["author"].get("characterId") == cid), None)
        if mine is not None:
            latest_by[cid] = str(mine.get("content", ""))
    last_line = next((m for m in reversed(msgs) if m["author"]["type"] == "character" and m.get("kind") == "chat"), None)
    f = DebateFacts(motion=motion, phase=phase, side=side,
                    last_opposing=said(opposing) if opposing is not None else "", latest_by_candidate=latest_by)
    return f, said(last_line) if last_line is not None else ""


def fingerprint_of(epoch: int, reply_epoch: int, msgs: list[Wire], emotion_mode: Any,
                   parts: list[tuple[str, bool, bool, Any]], target: tuple[str, int]) -> tuple[Any, ...]:
    """The pure part (tested one part at a time): only character and user messages move the seq (V2)."""
    said = [m for m in msgs if m["author"]["type"] in ("character", "user")]
    return (epoch, reply_epoch, int(said[-1]["seq"]) if said else 0, emotion_mode, tuple(parts), target)


async def fingerprint(actor: SessionActor, target: tuple[str, int]) -> tuple[Any, ...]:
    """M10 D15's list with V2's seq rule: the seq of the last character or user message, so a round banner, a host
    line or a system note doesn't spoil the plan; plus the slot's (phase, iteration)."""
    parts = []
    for p in actor.session["participants"]:
        cid = p["characterId"]
        parts.append((cid, not await is_asleep(actor, cid), bool(p.get("mutedByUser")), p.get("currentEmotion")))
    return fingerprint_of(actor.epoch, actor.reply_epoch, _ordered(actor), actor.session.get("emotionMode"), parts,
                          target)


async def start(actor: SessionActor, slot: int, target: tuple[str, int], side: str | None, candidates: list[str],
                started_at: datetime) -> Stored | None:
    """Start the slot's plan now and store it. None when the profile has no debate plan (`naive`, `scripted`)."""
    rt = actor.rt
    planner = rt.ai.planner(rt.keys.status() == "set")
    if not candidates:
        return None
    sctx = await session_context(rt, actor)
    f, latest = facts(actor, sctx, target[0], side, candidates)
    rows = await characters(rt, candidates)
    docs = await document_titles(rt, sctx.world.id, candidates) if getattr(planner, "decides_retrieval", False) else {}
    req = DebateRequest(session=sctx, phase=target[0], iteration=target[1], side=side, candidates=candidates,
                        cast=[character_view(rows[c]) for c in candidates if c in rows], facts=f, latest=latest,
                        turn_index=actor.mode.turn, base_faces=base_faces(actor, sctx, candidates), manual=manual(actor),
                        started_at=started_at, documents=docs)
    call = planner.start_debate(req)
    if call is None:
        return None
    drop(actor)
    stored = Stored(fp=await fingerprint(actor, target), slot=slot, target=target, call=call,
                    asked=len(candidates) >= 2)
    actor.background(NAME, _hold(stored))
    actor.mode.debate_plan = stored
    return stored


async def _hold(stored: Stored) -> None:
    """Keeps the request owned by the actor: `clear()` cancels this task, which cancels the call (recorded
    `cancelled` unless it already settled); idle release waits for it. Once a turn has used the plan, its late answer
    belongs to that turn's `debate_plan_late` task, so a newer plan replacing this hold leaves the call alone."""
    try:
        await stored.call.late_rows()
    except asyncio.CancelledError:
        if not stored.used:
            stored.call.cancel()
        raise


def drop(actor: SessionActor) -> None:
    """Forget any stored plan (Pause, Extend, Skip, a new plan): its call is cancelled."""
    stored, actor.mode.debate_plan = actor.mode.debate_plan, None
    if stored is not None and stored.call is not None:
        stored.call.cancel()
    actor.cancel_background(NAME)


async def start_opening(actor: SessionActor, target: tuple[str, int], cid: str, due: datetime) -> None:
    """D8: the first opening's face is planned at Start, inside the start delay, and stored with the fingerprint; its
    Jev deadline is the first opening's turn start (`due`). Under `naive` and `scripted` it plans nothing."""
    from horizon.sessions.plans import plans_cast

    if not plans_cast(actor):
        return
    drop(actor)
    fp = await fingerprint(actor, target)
    task = actor.background(NAME, opening_face(actor, cid, target, due))
    actor.mode.debate_plan = Stored(fp=fp, slot=0, target=target, call=None, asked=False, speaker=cid, face_task=task)


async def opening_face(actor: SessionActor, cid: str, target: tuple[str, int], due: datetime | None = None) -> Any:
    """An opening's face (`emotion_debate_opening`), by `due` or the `turn_plan` deadline."""
    from horizon.sessions.modes.debate import plan_face

    return await plan_face(actor, cid, target, kind="debate_opening", deadline_at=due)


async def take(actor: SessionActor, slot: int, target: tuple[str, int]) -> tuple[Stored | None, bool]:
    """At the turn's start: (the stored plan for this slot, whether its fingerprint still holds). A plan made for
    another slot or phase is dropped."""
    stored = actor.mode.debate_plan
    if stored is None:
        return None, False
    if stored.slot != slot or stored.target != target:
        drop(actor)
        return None, False
    return stored, stored.fp == await fingerprint(actor, target)


def stale(actor: SessionActor) -> None:
    """Pause (D8, as M10 D28 for watch): the stored faces are dropped, so Play plans them afresh; an announced member
    stays (`turn.next` already named them), and a phase's first-slot plan is not used."""
    stored = actor.mode.debate_plan
    if stored is not None:
        stored.fp = ("paused",)


def finish_with(actor: SessionActor, stored: Stored) -> None:
    """The turn has used the plan: forget it, without cancelling the request (a late answer still lands)."""
    stored.used = True
    if actor.mode.debate_plan is stored:
        actor.mode.debate_plan = None


async def append_late(actor: SessionActor, stored: Stored, message_id: str, speaker: str) -> None:
    """D27 / W1: an answer that landed after the turn started is written to that argument's trace as `fallback` rows
    with Jev's late answer; the face shown stays the fallback."""
    plan = await stored.call.late_rows()
    if plan is None:
        return
    rows = list(plan.shared_rows)
    for cid, row in plan.face_rows.items():
        rows.append(row if cid == speaker else {**row, "result": "not_used"})
    await actor.append_system1(message_id, None, rows, plan.calls)
