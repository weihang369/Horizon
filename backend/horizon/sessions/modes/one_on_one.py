"""1:1 (session-modes "1:1 conversation"; port of `mock/engines/oneOnOne.ts`): greet, send, regenerate (D-58).

M8 (docs/ai/04 P9; session-lifecycle "New session opening"; persona-context D19, D20): a character's FIRST chat opens
with its approved greeting, word for word and at no cost (a verbatim line: no model call, ledger row or energy).
Later chats generate the greeting through the profile's engine (the scripted one still bills its bank greeting).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from horizon.ai.contexts import LineHint
from horizon.ai.scripted.bank import greeting
from horizon.sessions.context import characters
from horizon.sessions.modes.common import asleep_note, is_asleep, last_user_text, message_event, speak_then, user_message
from horizon.sessions.retrieve import start_query
from horizon.sessions.turn import REGENERATE_SUFFIX, TurnSpec

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
        stored = str(row["profile"].get("greeting") or "").strip()
        if stored and await is_first_chat(actor, cid):
            hint = LineHint(kind="greeting", text=stored, verbatim=True)
        elif actor.rt.ai.impl("turn", key_set=actor.rt.keys.status() == "set") == "scripted":
            line = greeting(row["profile"])   # the scripted demo's billed greeting (D-81)
            hint = LineHint(kind="greeting", text=line.text, emotion=line.emotion)
        else:   # naive and agent generate it (agent avoids the stored one, P9)
            agent = actor.rt.ai.impl("turn", key_set=actor.rt.keys.status() == "set") == "agent"
            hint = LineHint(kind="greeting", last_time=await last_time(actor, cid) if agent else [])
        await speak_then(actor, TurnSpec(speaker=cid, line=hint))

    actor.enqueue(job)


LAST_TIME_MAX = 2


async def last_time(actor: SessionActor, character_id: str) -> list[str]:
    """M13 (memory D25; doc 09 M10): the ≤ 2 newest still-current memories this character took from its last other 1:1
    session (newest `created_at`). No waiting for a pending run: the list is what is committed now."""
    from sqlalchemy import and_, select

    from horizon.db import tables as t
    from horizon.services.memory.block import one_line

    S, M = t.sessions.c, t.memory_items.c
    async with actor.rt.db.read() as conn:
        last = (await conn.execute(select(M.source_session_id).join(t.sessions, S.id == M.source_session_id).where(and_(
            M.character_id == character_id, M.superseded_by.is_(None), M.source_mode == "one_on_one",
            S.mode == "one_on_one", S.id != actor.sid)).order_by(M.created_at.desc(), M.id.desc()).limit(1))).scalar()
        if last is None:
            return []
        rows = (await conn.execute(select(M.text).where(and_(
            M.character_id == character_id, M.superseded_by.is_(None), M.source_session_id == last))
            .order_by(M.created_at.desc(), M.id.desc()).limit(LAST_TIME_MAX))).scalars().all()
    return [one_line(str(x)) for x in rows]


async def is_first_chat(actor: SessionActor, character_id: str) -> bool:
    """P9's rule: no other non-seed, non-fork 1:1 session holds a message this character wrote. Asleep notes point at
    the character through `target_character_id`, so they don't count; deleted sessions are gone."""
    from sqlalchemy import and_, exists, select

    from horizon.db import tables as t

    S, M = t.sessions.c, t.messages.c
    q = select(exists().where(and_(
        M.session_id == S.id, M.author_character_id == character_id, S.mode == "one_on_one", S.is_seed.is_(False),
        S.continued_from.is_(None), S.id != actor.sid)))
    async with actor.rt.db.read() as conn:
        return not bool((await conn.execute(q)).scalar())


async def send(actor: SessionActor, text: str) -> None:
    cid = _speaker(actor)
    msg = user_message(actor, text)
    await actor.emit(message_event(msg))
    start_query(actor, text, str(msg["id"]), [cid] if cid else [])  # M5 design D12: in parallel with the turn
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
        from horizon.services.memory.undo import undo_read

        await undo_read(actor.rt, actor.sid, message_id)   # M13 (memory D20): an already-read reply, before it streams
        out = await speak_then(actor, TurnSpec(speaker=cid, prompt=f"{prompt}{REGENERATE_SUFFIX}",
                                               variant_of=message_id))
        done = actor.state["messages"].get(message_id)
        if out.status == "complete" and done is not None:   # M13 (memory D29): an indexed line follows, off the queue
            from horizon.services.memory.index import follow_regenerate

            actor.background("memory_index", follow_regenerate(actor.rt, actor.sid, str(actor.session["worldId"]),
                                                               message_id, str(done.get("content") or "")))

    actor.enqueue(job)
