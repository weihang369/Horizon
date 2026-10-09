"""Forget (doc 02 §3.7; long-term-memory "Forget removes a memory and all its versions", "Forget scrubs the memory from
past insights", "Forgotten text leaves the database files", "Forget notifies the AI layer"; design D14, D16).

In **one** writer transaction:
1. the chain: every version the memory superseded and every version that superseded it (to a fixpoint);
2. their vectors are zeroed, then the items are deleted (FTS and vec rows go by trigger; FTS5 `secure-delete` drops
   their terms; without it the index is optimised here);
3. every `turn_traces.trace` and `insight` event payload that recalled one of them is rewritten: its
   `memory.recalled[].text` becomes `"(forgotten)"`, and any other copy of the text in that trace is replaced too.
   They are found through `trace_memory_refs` **and** a scan of the world's traces and insight events for the text
   itself (a trace written without refs is still caught, and logged);
4. the refs go, and an `ai_purge_queue` row `{scope: "memory", ids: {memoryItemIds, characterId, messageIds}}` is queued.

After the commit: `entity.changed { kind: "memory", id: characterId, worldId }`; each live session that holds an
affected trace drops the text from its in-memory state (through its inbox: one writer per session); the purge worker is
woken; and a `wal_checkpoint(TRUNCATE)` copies the zeroed pages home and empties the WAL, so no old frame keeps the
text. Message contents are never edited: a phrase the user typed stays in the session where they typed it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from sqlalchemy import Text, and_, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.api.errors import not_found
from horizon.db import fts, spaces
from horizon.db import tables as t
from horizon.events.bus import GLOBAL

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.memory")
FORGOTTEN = "(forgotten)"
M = t.memory_items.c


def chain_of(start: str, items: Iterable[tuple[str, str | None]]) -> set[str]:
    """Every memory connected to `start` through `superseded_by`, in either direction."""
    newer = {mid: sup for mid, sup in items}
    chain = {start}
    while True:
        forward = {sup for m in chain if (sup := newer.get(m)) is not None}
        grow = (forward | {m for m, sup in newer.items() if sup in chain}) - chain
        if not grow:
            return chain
        chain |= grow


def scrub_value(value: Any, ids: set[str], texts: list[str]) -> tuple[Any, bool]:
    """A copy of a trace (or any JSON value) with the forgotten memories' text replaced; whether anything changed."""
    changed = False

    def walk(v: Any) -> Any:
        nonlocal changed
        if isinstance(v, dict):
            out = {k: walk(x) for k, x in v.items()}
            if out.get("memoryItemId") in ids and out.get("text") != FORGOTTEN:
                out["text"] = FORGOTTEN
                changed = True
            return out
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            s = v
            for tx in texts:
                if tx and tx in s:
                    s = s.replace(tx, FORGOTTEN)
            if s != v:
                changed = True
            return s
        return v

    return walk(value), changed


def _escaped(s: str) -> str:
    """How `s` appears inside a stored JSON column (the engines dump with ensure_ascii=False)."""
    return json.dumps(s, ensure_ascii=False)[1:-1]


async def _world_sessions(conn: AsyncConnection, world_id: str) -> list[str]:
    return list((await conn.execute(select(t.sessions.c.id).where(t.sessions.c.world_id == world_id))).scalars())


async def forget_chain(rt: Runtime, conn: AsyncConnection, *, character_id: str, world_id: str,
                       chain: set[str]) -> tuple[set[str], list[str]]:
    """Steps 2–4 inside the caller's transaction. Returns the message IDs whose traces were scrubbed, and the texts."""
    rows = (await conn.execute(select(M.rid, M.text).where(M.id.in_(chain)))).all()
    rids = [int(r[0]) for r in rows]
    texts = sorted({str(r[1]) for r in rows}, key=len, reverse=True)
    for space in await spaces.non_retired(conn):
        mem, _ = spaces.vec_tables(space.id)
        if rids:
            import sqlite_vec

            zero = sqlite_vec.serialize_float32([0.0] * space.dims)
            await conn.execute(text(f"UPDATE {mem} SET embedding = :z WHERE rid IN ({','.join(map(str, rids))})"),
                               {"z": zero})
    R = t.trace_memory_refs.c
    message_ids = set((await conn.execute(select(R.message_id).where(R.memory_item_id.in_(chain)))).scalars())
    sessions = await _world_sessions(conn, world_id)
    if sessions and texts:
        # The defensive pass (D14): traces and insight events that hold the text without a ref.
        for needle in {_escaped(x) for x in texts}:
            found = set((await conn.execute(
                select(t.turn_traces.c.message_id).join(t.messages, t.messages.c.id == t.turn_traces.c.message_id)
                .where(and_(t.messages.c.session_id.in_(sessions),
                            func.instr(func.cast(t.turn_traces.c.trace, Text), needle) > 0)))).scalars())
            found |= set((await conn.execute(select(t.session_events.c.message_id).where(and_(
                t.session_events.c.session_id.in_(sessions), t.session_events.c.type == "insight",
                func.instr(func.cast(t.session_events.c.payload, Text), needle) > 0)))).scalars())
            stray = {m for m in found if m} - message_ids
            if stray:
                log.warning("forget found %d trace(s) holding a memory's text without a ref", len(stray))
            message_ids |= {m for m in found if m}
    if message_ids:
        T = t.turn_traces.c
        for mid, trace in (await conn.execute(select(T.message_id, T.trace).where(T.message_id.in_(message_ids)))).all():
            new, changed = scrub_value(trace, chain, texts)
            if changed:
                await conn.execute(update(t.turn_traces).where(T.message_id == mid).values(trace=new))
        E = t.session_events.c
        for eid, payload in (await conn.execute(select(E.id, E.payload).where(and_(
                E.message_id.in_(message_ids), E.type == "insight")))).all():
            new, changed = scrub_value(payload, chain, texts)
            if changed:
                await conn.execute(update(t.session_events).where(E.id == eid).values(payload=new))
    await conn.execute(delete(t.trace_memory_refs).where(R.memory_item_id.in_(chain)))
    await conn.execute(delete(t.memory_items).where(M.id.in_(chain)))
    if not rt.fts_secure_delete:
        await fts.scrub_index(conn, "memory_fts")
    await conn.execute(t.ai_purge_queue.insert().values(
        scope="memory", ids={"memoryItemIds": sorted(chain), "characterId": character_id,
                             "messageIds": sorted(message_ids)},
        created_at=rt.now_iso(), attempts=0, done_at=None))
    return message_ids, texts


async def forget(rt: Runtime, memory_id: str) -> None:
    """`DELETE /memory/{id}`: 404 for an unknown memory; otherwise the whole Forget above."""
    async with rt.db.read() as conn:
        item = (await conn.execute(select(M.character_id, M.world_id).where(M.id == memory_id))).first()
    if item is None:
        raise not_found("Memory")
    character_id, world_id = str(item[0]), str(item[1])
    async with rt.memory.lock(character_id):
        async with rt.db.write() as tx:
            conn = tx.conn
            items = (await conn.execute(select(M.id, M.superseded_by).where(M.character_id == character_id))).all()
            if memory_id not in {r[0] for r in items}:
                raise not_found("Memory")
            chain = chain_of(memory_id, [(str(a), b) for a, b in items])
            message_ids, texts = await forget_chain(rt, conn, character_id=character_id, world_id=world_id,
                                                    chain=chain)
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "memory", "id": character_id, "worldId": world_id})
        await after_forget(rt, chain, message_ids, texts)


async def after_forget(rt: Runtime, chain: set[str], message_ids: set[str], texts: list[str]) -> None:
    """Live sessions drop the text from memory, the purge worker wakes, and the WAL is truncated (D16)."""
    if message_ids:
        async with rt.db.read() as conn:
            sids = set((await conn.execute(select(t.messages.c.session_id).where(t.messages.c.id.in_(message_ids))))
                       .scalars())
        for sid in sids:
            actor = rt.sessions.peek(sid)
            if actor is not None:
                actor.post(_scrub_actor(actor, chain, message_ids, texts))
    rt.purge.notify()
    await rt.db.checkpoint_truncate()


def _scrub_actor(actor: Any, chain: set[str], message_ids: set[str], texts: list[str]) -> Any:
    async def run() -> None:
        msgs = actor.state.get("messages", {})
        for mid in message_ids:
            m = msgs.get(mid)
            if m is not None and m.get("trace"):
                m["trace"], _ = scrub_value(m["trace"], chain, texts)
    return run
