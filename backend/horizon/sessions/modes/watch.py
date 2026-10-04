"""Watch (session-modes "Watch pacing and the turn cap", "Watch controls"; a port of `mock/engines/watch.ts`).

The premise is posted as a `direction` message; speakers take turns round-robin from the opening speaker, `paceMs` of
clock time apart. Each turn raises `turnsTaken` (`watch.state` + `session.state`); reaching `turnLimit` pauses with
`turn_cap`. A director's note colours the next 2 turns; Step in pauses and lets up to 2 characters reply.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import LineHint
from horizon.gateway.errors import ProviderError
from horizon.sessions.context import session_context
from horizon.sessions.modes.common import (
    asleep_note,
    is_asleep,
    message_event,
    note,
    patch_settings,
    runner,
    speak_then,
    user_message,
)
from horizon.sessions.modes.group import run_speakers
from horizon.sessions.turn import TurnSpec

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]
SUMMARY_DELAY_MS = 1200


def cfg_of(actor: SessionActor) -> Wire:
    c: Wire = actor.session.get("config") or {}
    return c


def state_of(actor: SessionActor) -> Wire:
    st: Wire = actor.session.get("state") or {"status": "paused", "turnsTaken": 0,
                                              "turnLimit": int(cfg_of(actor).get("maxTurns", 20))}
    return st


def watch_state(actor: SessionActor, patch: Wire) -> list[Wire]:
    st = {**state_of(actor), **patch}
    for k, v in list(st.items()):
        if v is None:
            del st[k]
    return [{"type": "watch.state", "payload": {"status": st["status"], "paceMs": cfg_of(actor).get("paceMs", 1500),
                                                "turnsTaken": st["turnsTaken"], "turnLimit": st["turnLimit"]}},
            {"type": "session.state", "payload": {"state": st}}]


def start(actor: SessionActor) -> None:
    async def job() -> None:
        await actor.rt.clock.sleep(actor.rt.runtime_cfg.timing.watch_start_ms / 1000)
        premise = str(cfg_of(actor).get("premise", ""))
        await actor.emit(message_event(note(actor, premise, "direction")), *watch_state(actor, {"status": "playing"}))
        turn(actor)

    actor.enqueue(job)


async def pick_speaker(actor: SessionActor) -> str | None:
    m = actor.mode
    if m.nudge:
        n: str = m.nudge
        m.nudge = None
        return n
    cast = [p["characterId"] for p in actor.session["participants"] if not p.get("mutedByUser")]
    if not cast:
        return None
    if m.watch_idx is None:
        opening = cfg_of(actor).get("openingSpeaker", "auto")
        director = actor.rt.ai.director(runner(actor).key_set())
        order = director.order(cast, opening if opening != "auto" else None)
        m.watch_idx = cast.index(order[0]) + int(state_of(actor).get("turnsTaken", 0))
    for _ in range(len(cast)):
        cid = str(cast[m.watch_idx % len(cast)])
        m.watch_idx += 1
        if not await is_asleep(actor, cid):
            return cid
    return None


def turn(actor: SessionActor, manual: bool = False) -> None:
    """One scene turn. `manual` (Step) runs while paused and doesn't chain."""
    async def job() -> None:
        st = state_of(actor)
        if not manual and (actor.held or st.get("status") != "playing"):
            return
        if int(st["turnsTaken"]) >= int(st["turnLimit"]):
            await actor.emit(*watch_state(actor, {"status": "ended", "nextSpeakerId": None}),
                             {"type": "session.paused", "payload": {"reason": "turn_cap"}})
            return
        cid = await pick_speaker(actor)
        if cid is None:
            parts = actor.session["participants"]
            if parts:
                await asleep_note(actor, parts[0]["characterId"], skipping=False)
            await actor.emit(message_event(note(actor, "Everyone's asleep. Top someone up to continue the scene.")),
                             *watch_state(actor, {"status": "paused"}),
                             {"type": "session.paused", "payload": {"reason": "user"}})
            actor.held = True
            return
        m = actor.mode
        direction = None
        if m.direction is not None and m.direction[1] > 0:
            direction = m.direction[0]
        if m.direction is not None:
            m.direction = (m.direction[0], m.direction[1] - 1)
        out = await speak_then(actor, TurnSpec(speaker=cid, line=LineHint(kind="scene"), direction_note=direction))
        if out.status not in ("complete", "interrupted", "error"):
            return
        taken = int(state_of(actor)["turnsTaken"]) + 1
        ended = taken >= int(state_of(actor)["turnLimit"])
        await actor.emit(*watch_state(actor, {"turnsTaken": taken, "status": "ended" if ended else state_of(actor)["status"]}))
        if ended:
            await actor.emit({"type": "session.paused", "payload": {"reason": "turn_cap"}})
        if not ended and not manual and not actor.held:
            actor.after(float(cfg_of(actor).get("paceMs", 1500)), lambda: turn(actor))

    actor.enqueue(job)


async def play(actor: SessionActor) -> None:
    actor.held = False
    await actor.emit(*watch_state(actor, {"status": "playing"}), {"type": "session.resumed", "payload": {"reason": "user"}})
    if not actor.busy and len(actor.turns) == 0:
        turn(actor)


async def pause(actor: SessionActor) -> None:
    actor.held = True
    await actor.emit(*watch_state(actor, {"status": "paused"}), {"type": "session.paused", "payload": {"reason": "user"}})


def step_once(actor: SessionActor) -> None:
    turn(actor, manual=True)


async def set_pace(actor: SessionActor, pace_ms: float) -> None:
    await actor.emit(patch_settings({"config": {**cfg_of(actor), "paceMs": pace_ms}}))
    await actor.emit(*watch_state(actor, {}))


async def direct(actor: SessionActor, text: str) -> None:
    actor.mode.direction = (text, 2)
    await actor.emit(message_event(user_message(actor, text, "direction")))


async def step_in(actor: SessionActor, text: str) -> None:
    if not actor.held:
        await pause(actor)
    await actor.emit(message_event(user_message(actor, text)))
    awake = [p["characterId"] for p in actor.session["participants"]
             if not p.get("mutedByUser") and not await is_asleep(actor, p["characterId"])]
    random.Random(f"{actor.seed}:stepin:{actor.mode.turn}").shuffle(awake)
    chosen = awake[:2]

    async def job() -> None:
        await run_speakers(actor, chosen, text)

    actor.enqueue(job)


async def extend(actor: SessionActor, turns: int = 10) -> None:
    st = state_of(actor)
    actor.held = False
    await actor.emit(*watch_state(actor, {"turnLimit": int(st["turnLimit"]) + turns, "status": "playing"}),
                     {"type": "session.resumed", "payload": {"reason": "extend"}})
    turn(actor)


async def summarise(actor: SessionActor) -> None:
    await actor.clear(keep_current=True)

    async def job() -> None:
        await actor.rt.clock.sleep(SUMMARY_DELAY_MS / 1000)
        sctx = await session_context(actor.rt, actor)
        try:
            text = await actor.rt.ai.summariser(runner(actor).key_set()).episode(sctx)
        except ProviderError:
            return
        await actor.emit(message_event(note(actor, text, "summary")))

    actor.enqueue(job)
