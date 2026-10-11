"""Opt-in AI call capture (docs/ai/02 B10; ai-call-capture spec; ai-foundation design D27–D29; tasks 6.1–6.4).

With `HORIZON_CAPTURE_AI_CALLS=1`, every paid call's redacted request and response (chat messages and text, Jev state,
questions and answers; never embedding inputs or vectors, image or audio bytes) and one row per finished turn (the
frozen `TurnContext` and the routing/Decider fallback flags) land in `ai_calls`, for `horizon eval capture`.

**Never on the hot path:** the gateway hook appends a dict to a bounded deque (2,000) and returns. A writer task
(`rt.spawn("capture")`) flushes every 2 s of clock time, or as soon as 200 rows wait, in one writer transaction.
Overflow drops the oldest row; the count goes into the next stored row's `dropped_before`. Off (the default): the hook
is never installed and no body is ever built.

**Retention:** at start-up and every hour of clock time, rows older than 7 days go, then all but the newest 20,000.

**Forget (D28):** before Forget's transaction deletes a character's rows (and the world's rows with no character),
it sets `forgotten[c]` / `forgotten_world[w]` = now; the flush drops any queued row of that character (or that world
with no character) created at or before the mark, so no forgotten text is written back.

**Purge hooks (D29):** `CaptureHooks` deletes rows on character and message deletes (idempotent `DELETE … WHERE`);
session and world deletes cascade by FK and are repeated harmlessly; `on_forget` is a no-op (Forget already deleted).
"""

from __future__ import annotations

import asyncio
import collections
import datetime as dt
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sqlalchemy import and_, delete, func, insert, or_, select

from horizon.db import tables as t
from horizon.db.uow import Database
from horizon.domain.ids import new_id
from horizon.gateway.context import CallContext

log = logging.getLogger("horizon.capture")

MAX_QUEUE = 2000
FLUSH_EVERY_S = 2.0
FLUSH_AT = 200
KEEP_DAYS = 7
KEEP_ROWS = 20_000
RETENTION_EVERY_S = 3600.0
C = t.ai_calls.c


class Capture:
    def __init__(self, db: Callable[[], Database], now_iso: Callable[[], str], *, enabled: bool,
                 sleep: Callable[[float], Any], spawn: Callable[[str, Any], Any]) -> None:
        self._db = db
        self.now_iso = now_iso
        self.enabled = enabled
        self.sleep = sleep
        self.spawn = spawn
        self.queue: collections.deque[dict[str, Any]] = collections.deque()
        self.dropped = 0                       # since the last stored row
        self.dropped_total = 0
        self.forgotten: dict[str, str] = {}
        self.forgotten_world: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._loop: Any = None
        self._kicked = False
        self._unlinked: dict[str, list[str]] = {}   # session → turn-level call rows waiting for their turn
        self._consumed: dict[str, bool] = {}

    # ── producers (cheap: build a dict, append, return) ──
    def _push(self, row: dict[str, Any]) -> bool:
        """A full queue refuses the new row and counts it; the next accepted row records the count (B10)."""
        if len(self.queue) >= MAX_QUEUE:
            self.dropped += 1
            self.dropped_total += 1
            if self.dropped_total in (1, 100) or self.dropped_total % 1000 == 0:
                log.warning("capture queue full: %d row(s) dropped so far", self.dropped_total)
            return False
        row["dropped_before"] = self.dropped
        self.dropped = 0
        self.queue.append(row)
        if len(self.queue) >= FLUSH_AT and not self._kicked:
            self._kicked = True
            self.spawn("capture-flush", self.flush())
        return True

    def on_call(self, ctx: CallContext, summary: Mapping[str, Any], outcome: Mapping[str, Any]) -> None:
        """The gateway's `on_call` hook: one row per recorded paid call."""
        if not self.enabled:
            return
        body = summary.get("body") or {}
        if summary.get("kind") == "embedding":
            body = {}                          # never embedding inputs or vectors
        row_id = new_id("aic")
        if ctx.message_id is None and ctx.session_id:   # a turn-level call (the route decision): the turn links it
            if self._consumed.pop(ctx.session_id, False):
                self._unlinked[ctx.session_id] = []
            self._unlinked.setdefault(ctx.session_id, []).append(row_id)
            del self._unlinked[ctx.session_id][:-16]
        self._push({
            "id": row_id, "kind": "call", "created_at": self._started(outcome.get("latencyMs")), "purpose": ctx.purpose,
            "category": ctx.category, "model": summary.get("model"), "provider": outcome.get("provider"),
            "latency_ms": outcome.get("latencyMs"), "cost_usd": outcome.get("costUsd"),
            "finish_reason": outcome.get("finishReason"), "error_code": body.get("errorCode"),
            "usage_record_id": outcome.get("ledgerRowId"), "world_id": ctx.world_id, "session_id": ctx.session_id,
            "character_id": ctx.character_id, "message_id": ctx.message_id,
            "request": body.get("request") or {"kind": summary.get("kind")}, "response": body.get("response")})

    def _started(self, latency_ms: Any) -> str:
        """When the call started (now − its latency): a reply that began before a Forget is caught by its mark even
        when it is recorded after it."""
        now = self.now_iso()
        if not isinstance(latency_ms, int | float) or latency_ms <= 0:
            return now
        at = dt.datetime.fromisoformat(now.replace("Z", "+00:00")) - dt.timedelta(milliseconds=float(latency_ms))
        return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def on_turn(self, *, world_id: str | None, session_id: str, character_id: str, message_id: str,
                request: Mapping[str, Any], response: Mapping[str, Any]) -> None:
        """`TurnRunner.finish()`'s row: the frozen TurnContext and the plan/fallback flags (M7: plan null)."""
        if not self.enabled:
            return
        linked = list(self._unlinked.get(session_id, []))
        self._consumed[session_id] = True
        for r in self.queue:                   # still queued: give them the message they served
            if r["id"] in linked and r["message_id"] is None:
                r["message_id"] = message_id
        self._push({"id": new_id("aic"), "kind": "turn", "created_at": self.now_iso(), "purpose": "turn",
                    "category": None, "model": None, "provider": None, "latency_ms": None, "cost_usd": None,
                    "finish_reason": None, "error_code": None, "usage_record_id": None, "world_id": world_id,
                    "session_id": session_id, "character_id": character_id, "message_id": message_id,
                    "request": dict(request), "response": {**dict(response), "callIds": linked}})

    # ── Forget (D28) ──
    def mark_forgotten(self, character_id: str, world_id: str) -> None:
        now = self.now_iso()
        self.forgotten[character_id] = now
        self.forgotten_world[world_id] = now
        kept = [r for r in self.queue if not self._dropped_by_forget(r)]   # out of memory now, not only at flush
        self.queue.clear()
        self.queue.extend(kept)

    def _dropped_by_forget(self, r: Mapping[str, Any]) -> bool:
        c, w, at = r.get("character_id"), r.get("world_id"), str(r.get("created_at"))
        if c and c in self.forgotten and at <= self.forgotten[c]:
            return True
        return bool(not c and w and w in self.forgotten_world and at <= self.forgotten_world[w])

    async def delete_for_forget(self, conn: Any, character_id: str, world_id: str) -> None:
        """Inside Forget's writer transaction (B10): the character's rows and the world's character-less rows."""
        await conn.execute(delete(t.ai_calls).where(or_(C.character_id == character_id,
                                                        and_(C.world_id == world_id, C.character_id.is_(None)))))

    # ── the writer ──
    async def flush(self) -> int:
        async with self._lock:
            self._kicked = False
            if not self.queue:
                return 0
            rows = [r for r in self.queue if not self._dropped_by_forget(r)]
            self.queue.clear()
            if not rows:
                return 0
            async with self._db().write() as tx:
                # FKs: a row whose session or world is already gone is skipped, not an error
                sids = {r["session_id"] for r in rows if r["session_id"]}
                wids = {r["world_id"] for r in rows if r["world_id"]}
                live_s = set((await tx.conn.execute(select(t.sessions.c.id).where(t.sessions.c.id.in_(sids))))
                             .scalars()) if sids else set()
                live_w = set((await tx.conn.execute(select(t.worlds.c.id).where(t.worlds.c.id.in_(wids))))
                             .scalars()) if wids else set()
                keep = [r for r in rows if (not r["session_id"] or r["session_id"] in live_s)
                        and (not r["world_id"] or r["world_id"] in live_w)]
                if keep:
                    await tx.conn.execute(insert(t.ai_calls), keep)
            return len(keep)

    async def retention(self) -> int:
        cutoff = (dt.datetime.fromisoformat(self.now_iso().replace("Z", "+00:00"))
                  - dt.timedelta(days=KEEP_DAYS)).isoformat().replace("+00:00", "Z")
        async with self._db().write() as tx:
            n = (await tx.conn.execute(delete(t.ai_calls).where(C.created_at < cutoff))).rowcount or 0
            total = int((await tx.conn.execute(select(func.count()).select_from(t.ai_calls))).scalar_one())
            if total > KEEP_ROWS:
                oldest = select(C.id).order_by(C.created_at, C.id).limit(total - KEEP_ROWS).scalar_subquery()
                n += (await tx.conn.execute(delete(t.ai_calls).where(C.id.in_(oldest)))).rowcount or 0
        return int(n)

    async def run(self) -> None:
        """Flush every 2 s of clock time; retention at start-up and hourly."""
        since_retention = RETENTION_EVERY_S
        while True:
            if since_retention >= RETENTION_EVERY_S:
                since_retention = 0.0
                try:
                    await self.retention()
                except Exception:
                    log.exception("capture retention failed")
            await self.sleep(FLUSH_EVERY_S)
            since_retention += FLUSH_EVERY_S
            try:
                await self.flush()
            except Exception:
                log.exception("capture flush failed (rows dropped)")

    def start(self) -> None:
        if self.enabled and self._loop is None:
            self._loop = self.spawn("capture", self.run())

    async def stop(self) -> None:
        if self._loop is not None:
            self._loop.cancel()
            try:
                await self._loop
            except (asyncio.CancelledError, Exception):
                pass
            self._loop = None
        if self.enabled:
            await self.flush()


class CaptureHooks:
    """The first real AiStateHooks (D29). Every hook is an idempotent DELETE."""

    def __init__(self, db: Callable[[], Database]) -> None:
        self._db = db

    async def on_delete(self, scope: str, ids: Sequence[str]) -> None:
        if not ids:
            return
        col = {"character": C.character_id, "message": C.message_id, "session": C.session_id,
               "world": C.world_id}.get(scope)
        if col is None:
            return
        async with self._db().write() as tx:
            await tx.conn.execute(delete(t.ai_calls).where(col.in_(list(ids))))

    async def on_forget(self, memory_item_ids: Sequence[str], character_id: str, message_ids: Sequence[str]) -> None:
        return None   # Forget already deleted inside its own transaction (D28)
