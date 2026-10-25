"""Recall's indexing: the lines that leave the history window (docs/ai/09 M9; memory design D29; session-recall "A drop
is indexed once", "Indexed lines follow their messages").

- **The hook:** after `SummaryTask` writes a rolling summary (the DeepSeek one or the free fallback) up to `upto_seq`,
  the messages that left the window — `seq` in (the previous summary's `upto_seq`, the new one], the lines heard in the
  scene (the user's chat, steer and interject; the characters' chat), active variant, complete — become one
  `message_index` row each, `"Name: text"`. FTS follows by trigger. A row per message, at most once.
- **One batch embedding** of the new rows: the active space only, purpose `embed_doc`, never pausing sessions, never
  through the response store (the user's text, W10), and only with a key. No key or a failure leaves them keyword-only;
  the next drop doesn't retry them.
- **It runs as the summary task's continuation**, in the actor's background set (`summary`): Stop doesn't cancel it,
  a delete and `clear(…)` do. Rows and vectors are each written in one transaction, so a cancel leaves no part of one.

`follow_*` keep indexed lines with their messages: a regenerate replaces the row's text and re-embeds it, a blocked
scrub zeroes the vector and deletes the row, a session delete zeroes the session's vectors before the cascade, and a
fork copies rows and vectors under the new ids with no new embedding.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import sqlite_vec
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import spaces
from horizon.db import tables as t
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.services.memory.stretch import Msg, heard, label

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.memory")
X = t.message_index.c


def line_text(speaker: str, content: str) -> str:
    return f"{speaker}: {' '.join(content.split())}"


def rows_of(state_msgs: Mapping[str, Any], ids: Sequence[str], names: Mapping[str, str], user_name: str,
            mode: str) -> list[tuple[str, int, str, str]]:
    """(message id, seq, author, "Name: text") for each dropped message heard in the scene, complete, active variant."""
    out: list[tuple[str, int, str, str]] = []
    for mid in ids:
        m = state_msgs.get(mid)
        if m is None:
            continue
        msg = Msg(id=mid, seq=int(m["seq"]), author_type=str(m["author"]["type"]),
                  character_id=m["author"].get("characterId"), kind=str(m["kind"]), content=str(m.get("content") or ""),
                  status=str(m["status"]), variant_id=m.get("activeVariantId"),
                  phase=(m.get("debate") or {}).get("phase") if m.get("debate") else None)
        if not heard(msg):
            continue
        out.append((mid, msg.seq, msg.author_type, line_text(label(msg, dict(names), user_name, mode), msg.content)))
    return out


async def index_drop(rt: Runtime, session_id: str, world_id: str, rows: Sequence[tuple[str, int, str, str]]) -> list[int]:
    """Write the new rows (one transaction), then embed them once (key only) and write their vectors (another).
    Returns the new rows' rids."""
    if not rows:
        return []
    now = rt.now_iso()
    async with rt.db.write() as tx:
        conn = tx.conn
        have = set((await conn.execute(select(X.message_id).where(X.message_id.in_([r[0] for r in rows])))).scalars())
        fresh = [r for r in rows if r[0] not in have]
        alive = set((await conn.execute(select(t.messages.c.id).where(t.messages.c.id.in_([r[0] for r in fresh]))))
                    .scalars()) if fresh else set()
        for mid, seq, author, body in fresh:
            if mid in alive:
                await conn.execute(t.message_index.insert().values(message_id=mid, session_id=session_id, seq=seq,
                                                                   author=author, text=body, created_at=now))
        new = (await conn.execute(select(X.rid, X.text).where(X.message_id.in_([r[0] for r in fresh if r[0] in alive])))
               ).all() if fresh else []
    await embed_lines(rt, session_id, world_id, [(int(r[0]), str(r[1])) for r in new])
    return [int(r[0]) for r in new]


async def embed_lines(rt: Runtime, session_id: str, world_id: str, lines: Sequence[tuple[int, str]]) -> int:
    """One batch embedding in the active space, the vectors written in one transaction for rows still there."""
    if not lines or rt.keys.status() != "set":
        return 0
    async with rt.db.read() as conn:
        space = await spaces.active(conn)
    ctx = call_ctx("embed_doc", world_id=world_id, session_id=session_id, pauses_sessions=False)
    try:
        async with rt.embed_slots.slot():
            got = await rt.ai.embedder(True).embed([b for _, b in lines], kind="message", space=space, ctx=ctx)
    except ProviderError as e:
        log.info("indexed lines of %s stay keyword-only: embedding failed (%s)", session_id, e.code)
        return 0
    table = spaces.message_vec_table(space.id)
    async with rt.db.write() as tx:
        return await write_vectors(tx.conn, table, session_id, [r for r, _ in lines], list(got.vectors))


async def write_vectors(conn: AsyncConnection, table: str, session_id: str, rids: Sequence[int],
                        vectors: Sequence[Sequence[float]]) -> int:
    if not rids:
        return 0
    alive = set((await conn.execute(select(X.rid).where(X.rid.in_(list(rids))))).scalars())
    n = 0
    for rid, vec in zip(rids, vectors, strict=True):
        if rid not in alive:
            continue
        await conn.execute(text(f"DELETE FROM {table} WHERE rid = :r"), {"r": rid})
        await conn.execute(text(f"INSERT INTO {table}(rid, session_id, embedding) VALUES (:r, :s, :e)"),
                           {"r": rid, "s": session_id, "e": sqlite_vec.serialize_float32(list(vec))})
        n += 1
    return n


async def zero_vectors(conn: AsyncConnection, rids: Sequence[int]) -> None:
    """Zero these lines' vectors in every non-retired space (one row per statement: vec0 refuses `rid IN (…)`)."""
    if not rids:
        return
    for space in await spaces.non_retired(conn):
        table = spaces.message_vec_table(space.id)
        zero = sqlite_vec.serialize_float32([0.0] * space.dims)
        for rid in rids:
            await conn.execute(text(f"UPDATE {table} SET embedding = :z WHERE rid = :r"), {"z": zero, "r": rid})


# ── following their messages (D29) ──
async def follow_regenerate(rt: Runtime, session_id: str, world_id: str, message_id: str, content: str) -> None:
    """The new active variant's text replaces the row's (FTS by trigger, the speaker's label kept), and its vector is
    embedded again. A message that was never indexed has nothing to follow."""
    async with rt.db.write() as tx:
        row = (await tx.conn.execute(select(X.rid, X.text).where(X.message_id == message_id))).first()
        if row is None:
            return
        rid = int(row[0])
        body = line_text(str(row[1]).split(": ", 1)[0], content)
        await tx.conn.execute(t.message_index.update().where(X.rid == rid).values(text=body))
    await embed_lines(rt, session_id, world_id, [(int(rid), body)])


async def follow_blocked(conn: AsyncConnection, message_id: str) -> None:
    """Inside the scrub's transaction: zero the line's vector, then delete its row."""
    rid = (await conn.execute(select(X.rid).where(X.message_id == message_id))).scalar()
    if rid is None:
        return
    await zero_vectors(conn, [int(rid)])
    await conn.execute(t.message_index.delete().where(X.rid == rid))


async def follow_session_delete(conn: AsyncConnection, session_id: str) -> None:
    """Inside the delete's transaction, before the cascade: zero the session's line vectors."""
    rids = [int(x) for x in (await conn.execute(select(X.rid).where(X.session_id == session_id))).scalars()]
    await zero_vectors(conn, rids)


async def follow_fork(conn: AsyncConnection, source_session: str, new_session: str, id_map: Mapping[str, str]) -> int:
    """Inside the fork's transaction: copy the rows of the copied messages under their new ids, and their vectors in
    every non-retired space (no new embedding)."""
    if not id_map:
        return 0
    rows = (await conn.execute(select(X.rid, X.message_id, X.seq, X.author, X.text, X.created_at).where(and_(
        X.session_id == source_session, X.message_id.in_(list(id_map)))))).all()
    targets = await spaces.non_retired(conn)
    n = 0
    for rid, mid, seq, author, body, created in rows:
        res = await conn.execute(t.message_index.insert().values(message_id=id_map[str(mid)], session_id=new_session,
                                                                 seq=seq, author=author, text=body, created_at=created))
        new_rid = res.inserted_primary_key[0] if res.inserted_primary_key else None
        for space in targets:
            table = spaces.message_vec_table(space.id)
            vec = (await conn.execute(text(f"SELECT embedding FROM {table} WHERE rid = :r"), {"r": rid})).scalar()
            if vec is not None and new_rid is not None:
                await conn.execute(text(f"INSERT INTO {table}(rid, session_id, embedding) VALUES (:r, :s, :e)"),
                                   {"r": new_rid, "s": new_session, "e": vec})
        n += 1
    return n
