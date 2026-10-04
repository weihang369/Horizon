"""Helpers shared by the modes (a port of `mock/engines/host.ts`): notes, user messages, the asleep note and
`speak_then` (a turn, then the turn gap). Modes call these and the TurnRunner; they never write rows themselves."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from horizon.ai.scripted.bank import first_name
from horizon.domain.ids import new_id
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
    return note(actor, text, kind, {"type": "user"}, **extra)


def message_event(m: Wire) -> Wire:
    return {"type": "message", "payload": {"message": m}}


async def name_of(actor: SessionActor, character_id: str) -> str:
    row = (await characters(actor.rt, [character_id])).get(character_id)
    return first_name(str(row["profile"].get("name", character_id))) if row is not None else character_id


async def asleep_note(actor: SessionActor, character_id: str, *, skipping: bool) -> None:
    """"{name} is asleep" (+ `energy_exhausted`, so the UI can offer a top-up)."""
    name = await name_of(actor, character_id)
    energy = await runner(actor).energy_now(character_id)
    current = int(energy["current"]) if energy else 0
    text = f"{name} is asleep, skipping." if skipping else f"{name} is asleep (⚡ {current})."
    msg = note(actor, text, targetCharacterId=character_id)
    await actor.emit(message_event(msg), {"type": "error", "payload": {
        "code": "energy_exhausted", "message": f"{name} is asleep (⚡ 0).", "retryable": False, "messageId": msg["id"]}})


async def speak_then(actor: SessionActor, spec: TurnSpec, *, prefetch: Any = None) -> TurnOutcome:
    """One turn, then the turn gap before the next queued turn (the mock's `speakThen`)."""
    out = await runner(actor).run(actor, spec, prefetch=prefetch)
    if out.status in ("complete", "interrupted", "error"):
        await actor.rt.clock.sleep(actor.rt.runtime_cfg.timing.turn_gap_ms / 1000)
    return out


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
