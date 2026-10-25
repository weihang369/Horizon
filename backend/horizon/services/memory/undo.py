"""The undo (docs/ai/09 M7; memory design D20; long-term-memory "A regenerated message is read again").

When an already-read message changes (Regenerate or Continue on a character message with `seq ≤ memory_seq`,
including an interrupted or failed reply completed later), the command does this **before it streams**, in one writer
transaction:
1. the memories whose `source_message_id` is that message **and that are still current** go through the Forget path,
   for those memories only (vectors zeroed, traces scrubbed, the character's stored rewrites cleared, D21); the lines
   they superseded become current again;
2. the message joins `memory_reread`, so the next run reads its new variant.

The checkpoint doesn't move, so no later message is read twice. A memory already superseded by a later run's rewrite
isn't current and is left; a `Reinforce` leaves no source and can't be undone (D20's named limitations).

The blocked reply (session-runtime "A blocked reply is scrubbed") uses step 1 only, inside the scrub's transaction: a
blocked new variant can't destroy older memories that were only superseded, and is never read (the stretch skips it).

Neither takes the characters' run locks: a regenerate never waits on a pause run. A run already in flight drops what the
undo made stale inside `apply_run` (the variant check, and the Forget-race rule for its rewrites and confirms).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import tables as t
from horizon.events.bus import GLOBAL
from horizon.services.memory.forget import after_forget, forget_chain

if TYPE_CHECKING:
    from horizon.runtime import Runtime

M = t.memory_items.c


@dataclass
class Undone:
    removed: set[str] = field(default_factory=set)
    restored: set[str] = field(default_factory=set)
    characters: set[tuple[str, str]] = field(default_factory=set)    # (character id, world id)
    message_ids: set[str] = field(default_factory=set)               # traces scrubbed
    texts: list[str] = field(default_factory=list)
    reread: bool = False


async def undo_derived(rt: Runtime, conn: AsyncConnection, message_id: str) -> Undone:
    """Step 1 inside the caller's transaction: the still-current memories sourced from `message_id` are forgotten one
    by one, and what each superseded is current again."""
    out = Undone()
    derived = (await conn.execute(select(M.id, M.character_id, M.world_id).where(and_(
        M.source_message_id == message_id, M.superseded_by.is_(None))))).all()
    for mem_id, character_id, world_id in derived:
        mid = str(mem_id)
        older = set((await conn.execute(select(M.id).where(M.superseded_by == mid))).scalars())
        if older:
            await conn.execute(update(t.memory_items).where(M.id.in_(older)).values(superseded_by=None))
        msgs, texts = await forget_chain(rt, conn, character_id=str(character_id), world_id=str(world_id),
                                         chain={mid})
        out.removed.add(mid)
        out.restored |= {str(x) for x in older}
        out.characters.add((str(character_id), str(world_id)))
        out.message_ids |= msgs
        out.texts.extend(texts)
    return out


async def undo_read(rt: Runtime, session_id: str, message_id: str) -> Undone | None:
    """D20, before a regenerate or continue streams: None when the message hasn't been read yet (nothing to undo)."""
    async with rt.db.write() as tx:
        conn = tx.conn
        row = (await conn.execute(select(t.messages.c.seq, t.sessions.c.memory_seq, t.sessions.c.memory_reread,
                                         t.sessions.c.is_seed)
                                  .join(t.sessions, t.sessions.c.id == t.messages.c.session_id)
                                  .where(and_(t.messages.c.id == message_id, t.messages.c.session_id == session_id)))
               ).first()
        if row is None or bool(row[3]) or int(row[0]) > int(row[1]):
            return None
        out = await undo_derived(rt, conn, message_id)
        reread = [str(x) for x in (row[2] or [])]
        if message_id not in reread:
            await conn.execute(update(t.sessions).where(t.sessions.c.id == session_id).values(
                memory_reread=[*reread, message_id]))
        out.reread = True
        for cid, wid in out.characters:
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "memory", "id": cid, "worldId": wid})
    await after_undo(rt, out)
    return out


async def after_undo(rt: Runtime, out: Undone) -> None:
    """After the commit: what a Forget does after its own (live traces scrubbed, purge woken, WAL truncated), and the
    live actors holding these characters drop their cached memory lists (D23)."""
    if not out.removed:
        return
    await after_forget(rt, out.removed, out.message_ids, out.texts, characters=[c for c, _ in out.characters])
