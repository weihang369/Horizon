"""EventWriter (session-runtime design D1, D3; session-event-sourcing "Live sessions stay event-sourced").

The one write path for a live session's rows. `append(events)`:
1. stamps each event with its id, the next `seq` (counters start from the stored `MAX(seq)`) and `at`;
2. reduces them with the shared reducer (`services/runtime/reducer.py`) into the writer's state;
3. in ONE writer transaction, stores the events and projects what they changed: the session row, participants,
   the touched messages, `turn_traces` (from `insight`) and `message_citations` (from `turn.end`);
4. publishes each stored event on the session channel only after the commit, so a subscriber never sees an event that
   isn't stored, and the event it sees is the stored one (stored == streamed by construction).

If the transaction fails, the in-memory state is reloaded from storage, so it never runs ahead of the rows.
The caller (the SessionActor) serialises appends; the writer itself is not reentrant.
"""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.api.errors import not_found
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.db.uow import Database, WriteTx
from horizon.domain.ids import new_id
from horizon.events.bus import GLOBAL, session_channel
from horizon.services.runtime.reducer import apply_in_place, initial_runtime, ordered_messages

Wire = dict[str, Any]
State = dict[str, Any]

# Event types after which the session's list entry changes (the MockClient's `changed("session")`).
SESSION_CHANGING = frozenset({"turn.end", "message", "session.state", "session.paused", "session.resumed", "phase"})


@dataclass(frozen=True)
class TraceMeta:
    """Which engine produced a trace (`turn_traces.engine/engine_version/prompt_version`)."""

    engine: str | None = None
    engine_version: str | None = None
    prompt_version: str | None = None


Extra = Callable[[WriteTx, list[Wire]], Awaitable[None]]


async def load_state(conn: AsyncConnection, session_id: str) -> tuple[State, bool]:
    """The reducer state for a stored session (session + messages), with `lastSeq` = the highest stored seq."""
    srow = (await conn.execute(select(t.sessions).where(t.sessions.c.id == session_id))).mappings().first()
    if srow is None:
        raise not_found("Session")
    parts = (await conn.execute(select(t.participants).where(t.participants.c.session_id == session_id))).mappings().all()
    mrows = (await conn.execute(select(t.messages).where(t.messages.c.session_id == session_id)
                                .order_by(t.messages.c.seq))).mappings().all()
    trows = {r[0]: r[1] for r in (await conn.execute(
        select(t.turn_traces.c.message_id, t.turn_traces.c.trace).where(
            t.turn_traces.c.message_id.in_([m["id"] for m in mrows])))).all()} if mrows else {}
    last = int((await conn.execute(select(func.coalesce(func.max(t.session_events.c.seq), 0))
                                   .where(t.session_events.c.session_id == session_id))).scalar_one())
    state = initial_runtime(mp.session_wire(srow, parts), [mp.message_wire(m, trows.get(m["id"])) for m in mrows])
    state["lastSeq"] = last
    return state, bool(srow["is_seed"])


class EventWriter:
    def __init__(self, db: Database, session_id: str, state: State, *, is_seed: bool, now_iso: Callable[[], str]) -> None:
        self.db = db
        self.session_id = session_id
        self.state = state
        self.is_seed = is_seed
        self.now_iso = now_iso

    @classmethod
    async def load(cls, db: Database, session_id: str, now_iso: Callable[[], str]) -> EventWriter:
        async with db.read() as conn:
            state, is_seed = await load_state(conn, session_id)
        return cls(db, session_id, state, is_seed=is_seed, now_iso=now_iso)

    @property
    def last_seq(self) -> int:
        return int(self.state["lastSeq"])

    @property
    def session(self) -> Wire:
        s: Wire = self.state["session"]
        return s

    async def reload(self) -> None:
        async with self.db.read() as conn:
            self.state, self.is_seed = await load_state(conn, self.session_id)

    def stamp(self, events: Sequence[Mapping[str, Any]], at: str | None = None) -> list[Wire]:
        when = at or self.now_iso()
        out: list[Wire] = []
        seq = self.last_seq
        for e in events:
            seq += 1
            out.append({"id": new_id("evt"), "sessionId": self.session_id, "seq": seq, "at": when, "type": e["type"],
                        "payload": copy.deepcopy(e["payload"])})
        return out

    async def append(self, events: Sequence[Mapping[str, Any]], *, traces: Mapping[str, TraceMeta] | None = None,
                     extra: Extra | None = None) -> list[Wire]:
        """Store, project and (after commit) publish `events` (`{type, payload}`). Returns the stored SessionEvents."""
        if not events:
            return []
        stamped = self.stamp(events)
        before_parts = copy.deepcopy(self.session["participants"])
        apply_in_place(self.state, stamped)
        try:
            async with self.db.write() as tx:
                await self._project(tx, stamped, before_parts, traces or {})
                if extra is not None:
                    await extra(tx, stamped)
                for e in stamped:
                    tx.publish(session_channel(self.session_id), e)
                if any(e["type"] in SESSION_CHANGING for e in stamped):
                    tx.publish(GLOBAL, {"type": "entity.changed", "kind": "session", "id": self.session_id,
                                        "worldId": self.session["worldId"]})
        except BaseException:
            await self.reload()
            raise
        return stamped

    async def _project(self, tx: WriteTx, stamped: list[Wire], before_parts: list[Wire],
                       traces: Mapping[str, TraceMeta]) -> None:
        conn = tx.conn
        await conn.execute(t.session_events.insert(), [mp.event_row(e) for e in stamped])
        srow, prow = mp.session_rows(self.session, is_seed=self.is_seed)
        await conn.execute(update(t.sessions).where(t.sessions.c.id == self.session_id).values(
            **{k: v for k, v in srow.items() if k not in ("id", "is_seed", "created_at")}))
        if prow != mp.session_rows({**self.session, "participants": before_parts}, is_seed=self.is_seed)[1]:
            await self._participants(conn, prow, before_parts)
        touched: list[str] = []
        for e in stamped:
            mid = mp.event_message_id(e)
            if mid and mid not in touched:
                touched.append(mid)
        msgs = {m["id"]: m for m in ordered_messages(self.state)}
        for mid in touched:
            m = msgs.get(mid)
            if m is None:
                continue
            row = mp.message_row(m)
            stmt = sqlite_insert(t.messages).values(**row)
            await conn.execute(stmt.on_conflict_do_update(index_elements=["id"],
                                                          set_={k: stmt.excluded[k] for k in row if k != "id"}))
        for e in stamped:
            if e["type"] == "insight":
                mid = e["payload"]["messageId"]
                if mid not in msgs:
                    continue
                meta = traces.get(mid, TraceMeta())
                row = {"message_id": mid, "trace": e["payload"]["trace"], "engine": meta.engine,
                       "engine_version": meta.engine_version, "prompt_version": meta.prompt_version, "created_at": e["at"]}
                stmt = sqlite_insert(t.turn_traces).values(**row)
                await conn.execute(stmt.on_conflict_do_update(index_elements=["message_id"],
                                                              set_={k: stmt.excluded[k] for k in row if k != "message_id"}))
            elif e["type"] == "turn.end":
                mid = e["payload"]["messageId"]
                if mid not in msgs:
                    continue
                await conn.execute(delete(t.message_citations).where(t.message_citations.c.message_id == mid))
                rows = mp.citation_rows(msgs[mid])
                if rows:
                    await conn.execute(t.message_citations.insert(), rows)

    async def _participants(self, conn: AsyncConnection, rows: list[dict[str, Any]], before: list[Wire]) -> None:
        P = t.participants.c
        if [r["character_id"] for r in rows] == [p["characterId"] for p in before]:
            for r in rows:
                await conn.execute(update(t.participants).where(and_(
                    P.session_id == self.session_id, P.character_id == r["character_id"])).values(
                    ord=r["ord"], role=r["role"], side=r["side"], current_emotion=r["current_emotion"], muted=r["muted"]))
            return
        await conn.execute(delete(t.participants).where(P.session_id == self.session_id))
        await conn.execute(t.participants.insert(), rows)
