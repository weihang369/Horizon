"""AI-owned per-message data (rag design D19; doc 13 W13; session-event-sourcing "AI-owned per-message data is not
event-sourced").

`message_ai_meta` is keyed by the **user message** being answered. `rewrites[speakerId] = {"text", "at"}` holds an
accepted query rewrite (doc 10 K4), so regenerate searches the same thing with no new call. Only accepted rewrites are
stored (a failed one is tried again). The runtime writes a row in its own small write after the deep work returns,
never in the event path; a message deleted meanwhile cascades its row away, and a missing message writes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from horizon.db import tables as t

if TYPE_CHECKING:
    from horizon.runtime import Runtime

A = t.message_ai_meta.c


async def stored_rewrite(rt: Runtime, message_id: str | None, speaker_id: str) -> str | None:
    if not message_id:
        return None
    async with rt.db.read() as conn:
        row = (await conn.execute(select(A.rewrites).where(A.message_id == message_id))).first()
    rewrites: dict[str, Any] = dict(row[0] or {}) if row is not None else {}
    got = rewrites.get(speaker_id)
    return str(got["text"]) if isinstance(got, dict) and got.get("text") else None


async def store_rewrite(rt: Runtime, message_id: str | None, speaker_id: str, text: str) -> bool:
    """Keep an accepted rewrite for (message, speaker). False when the message is gone (nothing written)."""
    if not message_id or not text:
        return False
    at = rt.now_iso()
    async with rt.db.write() as tx:
        exists = (await tx.conn.execute(select(t.messages.c.id).where(t.messages.c.id == message_id))).first()
        if exists is None:
            return False
        row = (await tx.conn.execute(select(A.rewrites).where(A.message_id == message_id))).first()
        rewrites = dict(row[0] or {}) if row is not None else {}
        rewrites[speaker_id] = {"text": text, "at": at}
        stmt = insert(t.message_ai_meta).values(message_id=message_id, rewrites=rewrites, updated_at=at)
        await tx.conn.execute(stmt.on_conflict_do_update(index_elements=["message_id"],
                                                          set_={"rewrites": rewrites, "updated_at": at}))
    return True
