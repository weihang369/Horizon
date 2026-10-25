"""AI-owned per-message data (rag design D19; doc 13 W13; session-event-sourcing "AI-owned per-message data is not
event-sourced").

`message_ai_meta` is keyed by the **user message** being answered. `rewrites[speakerId] = {"text", "at"}` holds an
accepted query rewrite (doc 10 K4), so regenerate searches the same thing with no new call. Only accepted rewrites are
stored (a failed one is tried again). The runtime writes a row in its own small write after the deep work returns,
never in the event path; a message deleted meanwhile cascades its row away, and a missing message writes nothing.

M14 (safety design D5; migration 0006): `safety` holds the stored answers to "unsafe request?" and "at risk?" for the
user line, `{steer, care, pInput, pCare, at, v}`. Only Jev's answers are stored: a fallback, late or refused answer
writes nothing, so the next plan that sees the line asks again. The booleans are the decision the reply got (a
regenerate after a threshold change reuses them). A row without `safety` (every line before M14) reads "not flagged".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
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


# ── M14 (safety D5): the stored safety answers ──
@dataclass(frozen=True)
class StoredSafety:
    steer: bool                       # pInput >= tSteer when it was answered
    care: bool | None                 # pCare >= tCare (the raw yes, not the stay); None where care isn't asked
    p_input: float
    p_care: float | None
    at: str = ""
    versions: Mapping[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"steer": self.steer, "care": self.care, "pInput": self.p_input, "pCare": self.p_care, "at": self.at,
                "v": dict(self.versions)}

    @staticmethod
    def from_json(raw: Any) -> StoredSafety | None:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("steer"), bool):
            return None
        care, p_care = raw.get("care"), raw.get("pCare")
        return StoredSafety(steer=raw["steer"], care=care if isinstance(care, bool) else None,
                            p_input=float(raw.get("pInput") or 0.0),
                            p_care=float(p_care) if isinstance(p_care, int | float) else None,
                            at=str(raw.get("at") or ""), versions=dict(raw.get("v") or {}))


async def stored_safety(rt: Runtime, message_id: str | None) -> StoredSafety | None:
    if not message_id:
        return None
    return (await stored_safety_many(rt, [message_id])).get(message_id)


async def stored_safety_many(rt: Runtime, message_ids: Iterable[str]) -> dict[str, StoredSafety]:
    """The stored answers for these lines; a line with no row (or no answer) is absent: "not flagged"."""
    ids = [i for i in dict.fromkeys(message_ids) if i]
    if not ids:
        return {}
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(A.message_id, A.safety).where(A.message_id.in_(ids)))).all()
    out: dict[str, StoredSafety] = {}
    for mid, raw in rows:
        got = StoredSafety.from_json(raw)
        if got is not None:
            out[str(mid)] = got
    return out


async def store_safety(rt: Runtime, message_id: str | None, flags: StoredSafety) -> bool:
    """Keep Jev's answers for a user line, in their own small write (never in the event path). False when the message
    is gone (nothing written). The caller passes only answers that came from Jev (design D5)."""
    if not message_id:
        return False
    at = flags.at or rt.now_iso()
    value = StoredSafety(flags.steer, flags.care, flags.p_input, flags.p_care, at, flags.versions).to_json()
    async with rt.db.write() as tx:
        exists = (await tx.conn.execute(select(t.messages.c.id).where(t.messages.c.id == message_id))).first()
        if exists is None:
            return False
        stmt = insert(t.message_ai_meta).values(message_id=message_id, safety=value, updated_at=at)
        await tx.conn.execute(stmt.on_conflict_do_update(index_elements=["message_id"],
                                                          set_={"safety": value, "updated_at": at}))
    return True
