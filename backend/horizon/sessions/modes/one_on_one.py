"""1:1 (session-modes "1:1 conversation"; port of `mock/engines/oneOnOne.ts`): greet, send, regenerate (D-58)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from horizon.ai.contexts import LineHint
from horizon.ai.scripted.bank import greeting
from horizon.sessions.context import characters
from horizon.sessions.modes.common import asleep_note, is_asleep, last_user_text, message_event, speak_then, user_message
from horizon.sessions.turn import TurnSpec

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor


def _speaker(actor: SessionActor) -> str | None:
    parts = actor.session["participants"]
    return str(parts[0]["characterId"]) if parts else None


def greet(actor: SessionActor) -> None:
    cid = _speaker(actor)
    if cid is None:
        return

    async def job() -> None:
        await actor.rt.clock.sleep(actor.rt.runtime_cfg.timing.greeting_ms / 1000)
        if await is_asleep(actor, cid):
            await asleep_note(actor, cid, skipping=False)
            return
        row = (await characters(actor.rt, [cid]))[cid]
        line = greeting(row["profile"])
        await speak_then(actor, TurnSpec(speaker=cid, line=LineHint(kind="greeting", text=line.text, emotion=line.emotion)))

    actor.enqueue(job)


async def send(actor: SessionActor, text: str) -> None:
    cid = _speaker(actor)
    await actor.emit(message_event(user_message(actor, text)))
    if cid is None:
        return

    async def job() -> None:
        if await is_asleep(actor, cid):
            await asleep_note(actor, cid, skipping=False)
            return
        await speak_then(actor, TurnSpec(speaker=cid, prompt=text))

    actor.enqueue(job)


def regenerate(actor: SessionActor, message_id: str) -> None:
    m = actor.state["messages"].get(message_id)
    cid = m["author"].get("characterId") if m else None
    if m is None or not cid:
        return
    prompt = last_user_text(actor, before_seq=int(m["seq"]))

    async def job() -> None:
        if await is_asleep(actor, cid):
            await asleep_note(actor, cid, skipping=False)
            return
        await speak_then(actor, TurnSpec(speaker=cid, prompt=f"{prompt} (again)", variant_of=message_id))

    actor.enqueue(job)
