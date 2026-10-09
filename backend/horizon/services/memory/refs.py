"""Trace memory refs (knowledge-memory-storage design D14): which memories a stored trace recalled.

Forget finds every trace and `insight` event that holds a memory's text through `trace_memory_refs`, so every path
that writes a trace keeps them: the session writer on each `insight`, fork for the copied traces under their new
message IDs, and the seed import. One helper derives them from `trace.memory.recalled[]`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import tables as t


def refs_from_trace(message_id: str, trace: Mapping[str, Any] | None) -> list[dict[str, str]]:
    recalled = ((trace or {}).get("memory") or {}).get("recalled") or []
    ids = {str(r["memoryItemId"]) for r in recalled if isinstance(r, Mapping) and r.get("memoryItemId")}
    return [{"memory_item_id": mid, "message_id": message_id} for mid in sorted(ids)]


async def replace_refs(conn: AsyncConnection, message_id: str, trace: Mapping[str, Any] | None) -> None:
    """Set the message's refs to exactly what its (latest) trace recalled."""
    await conn.execute(delete(t.trace_memory_refs).where(t.trace_memory_refs.c.message_id == message_id))
    rows = refs_from_trace(message_id, trace)
    if rows:
        await conn.execute(t.trace_memory_refs.insert(), rows)
