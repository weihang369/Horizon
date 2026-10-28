"""Helpers shared by the modes (a port of `mock/engines/host.ts`): notes, user messages, the asleep note and
`speak_then` (a turn, then the turn gap). Modes call these and the TurnRunner; they never write rows themselves."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from horizon.ai.scripted.bank import first_name
from horizon.domain import vclock
from horizon.domain.ids import new_id
from horizon.sessions.after_turn import on_user_message
from horizon.sessions.context import characters
from horizon.sessions.turn import TurnOutcome, TurnRunner, TurnSpec

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]


def runner(actor: SessionActor) -> TurnRunner:
    r: TurnRunner = actor.manager.runner
    return r


def next_seq(actor: SessionActor) -> int:
    msgs = actor.state["messages"]
    return max((m["seq"] for m in msgs.values()), default=0) + 1


def note(actor: SessionActor, content: str, kind: str = "system_note", author: Wire | None = None, **extra: Any) -> Wire:
    """The mock's `systemNote`: a complete message from the system (or the given author)."""
    m: Wire = {"id": new_id("msg"), "sessionId": actor.sid, "seq": next_seq(actor), "author": author or {"type": "system"},
               "kind": kind, "content": content, "status": "complete", "createdAt": actor.rt.now_iso()}
    m.update({k: v for k, v in extra.items() if v is not None})
    return m


def user_message(actor: SessionActor, text: str, kind: str = "chat", **extra: Any) -> Wire:
    """Every mode's send path builds its user line here, just before emitting it: pending listener reactions are
    dropped (M9 D20, E5)."""
    on_user_message(actor)
    return note(actor, text, kind, {"type": "user"}, **extra)


def message_event(m: Wire) -> Wire:
    return {"type": "message", "payload": {"message": m}}


async def name_of(actor: SessionActor, character_id: str) -> str:
    row = (await characters(actor.rt, [character_id])).get(character_id)
    return first_name(str(row["profile"].get("name", character_id))) if row is not None else character_id


async def asleep_note(actor: SessionActor, character_id: str, *, skipping: bool, debate: Wire | None = None) -> None:
    """"{name} is asleep" (+ `energy_exhausted`, so the UI can offer a top-up). A debate's notes carry its phase tag
    (M11, debate design D3), so the slot cursor can read them from the log."""
    name = await name_of(actor, character_id)
    energy = await runner(actor).energy_now(character_id)
    if energy is None and not skipping:   # pass 2 J3-08: deleted, not asleep, so no Top up (the skip note's wording
        #                                   stays: the debate's slot cursor counts it)
        await actor.emit(message_event(note(actor, f"{name} has left.", targetCharacterId=character_id, debate=debate)))
        return
    current = int(energy["current"]) if energy else 0
    text = f"{name} is asleep, skipping." if skipping else f"{name} is asleep (⚡ {current})."
    msg = note(actor, text, targetCharacterId=character_id, debate=debate)
    await actor.emit(message_event(msg), {"type": "error", "payload": {
        "code": "energy_exhausted", "message": f"{name} is asleep (⚡ 0).", "retryable": False, "messageId": msg["id"]}})


async def muted_mentions(actor: SessionActor, mentions: list[str]) -> list[str]:
    """Pass 2 J3-11 (the user's choice: mute wins): a muted character never speaks, even when @mentioned. Each muted
    mention gets "{name} is muted." and is dropped; the rest are returned."""
    muted = {p["characterId"] for p in actor.session["participants"] if p.get("mutedByUser")}
    for m in mentions:
        if m in muted:
            await actor.emit(message_event(note(actor, f"{await name_of(actor, m)} is muted.", targetCharacterId=m)))
    return [m for m in mentions if m not in muted]


async def speak_then(actor: SessionActor, spec: TurnSpec, *, prefetch: Any = None) -> TurnOutcome:
    """One turn, then the turn gap before the next queued turn (the mock's `speakThen`). M14 (safety D10): the gap
    counts from the stream's end, so the output check's time is hidden in it."""
    out = await runner(actor).run(actor, spec, prefetch=prefetch)
    if out.status in ("complete", "interrupted", "error"):
        await gap(actor, spec.epoch, max(0.0, actor.rt.runtime_cfg.timing.turn_gap_ms / 1000 - checked_s(out)))
    return out


def checked_s(out: Any) -> float:
    """M14 (safety D10): the seconds between a turn's stream end and its `turn.end` (the output check), taken off the
    waits after it, so a check shorter than the wait adds nothing to the cadence."""
    end, done = getattr(out, "stream_end", None), getattr(out, "ended_at", None)
    return max(0.0, (done - end).total_seconds()) if end is not None and done is not None else 0.0


async def gap(actor: SessionActor, epoch: int | None, seconds: float | None = None) -> None:
    """The turn gap (or what is left of it). A reply job's gap ends at once when a user message supersedes its epoch
    (doc 07 G5; group-watch D12), so the new message's routing doesn't sit behind an old gap."""
    rt = actor.rt
    s = rt.runtime_cfg.timing.turn_gap_ms / 1000 if seconds is None else seconds
    if epoch is None:
        await rt.clock.sleep(s)
        return
    if not actor.current_epoch(epoch):
        return
    task = rt.spawn(f"gap:{actor.sid}", rt.clock.sleep(s))
    try:
        if not await vclock.wait_unless(task, actor.superseded(epoch)):
            task.cancel()
    except asyncio.CancelledError:
        task.cancel()
        raise


async def is_asleep(actor: SessionActor, character_id: str) -> bool:
    return await runner(actor).is_asleep(character_id)


def last_user_text(actor: SessionActor, before_seq: int | None = None) -> str:
    from horizon.services.runtime.reducer import ordered_messages

    for m in reversed(ordered_messages(actor.state)):
        if m["author"]["type"] == "user" and (before_seq is None or m["seq"] < before_seq):
            return str(m["content"])
    return ""


def patch_settings(patch: Wire) -> Wire:
    return {"type": "session.state", "payload": {"settings": patch}}
