"""Memory pause runs (docs/ai/09 M1, M2, M6; memory design D7–D11; long-term-memory "Memories are written when a session
pauses", "Pause runs are bounded and independent of sessions", "A session opening runs the other session's memories
first", "Runs wait for a usable key", "Failed runs retry, then skip").

**Runs belong to the runtime, not the actor** (doc 09 M1): an actor's background task would keep it from ever going
idle, and deleting the actor would cancel the run. Each run is `rt.spawn("memory_run:{sid}")`.

**The scheduler (D8):** two FIFO queues, high (a session opening with a shared character, trigger 5) and normal; at
most `memory.maxConcurrent` (2) running, outside the reply slots (`llmConcurrency`). One run per session: a request
while it is queued merges into it (raised to high if asked), and a request while it runs queues one more run after.
Deleting a session, character or world, Reset demo and shutdown cancel the affected runs, which write nothing.

**The triggers (D7):**
1. the session stream's last subscriber gone for `memory.leaveGraceMs` (30 s), any status (`EventBus.watch`);
2. `leave` (the `navigated_away` pause), 3. `end`, a debate's end after its verdict, watch's `turn_cap` pause: all
   seen in the actor's events (`on_events`);
4. a reply still streaming at one of those moments reaches its `turn.end`: requested again then;
5. a session opening (an actor starting) with a character who has unread lines in another session: high priority;
6. start-up: every non-seed session with unread or re-read lines (`sweep`);
7. the idle release (the actor asks before it goes).

**A run (D8–D10):** the session must exist and not be a seed. An explicitly `scripted` profile advances the checkpoint
with no call (the mock never writes memories). With no usable key the run is deferred: nothing moves and no try is
counted. Otherwise it takes every present character's lock (sorted), reads their lists, builds the stretch, and runs
the writer piece by piece; each piece commits its memories with its checkpoint (`MemoryStore.apply_run`). Below the
minimum nothing moves (an ended session advances). A failed piece counts a try; after `memory.maxTries` it is skipped.
A daily-cap refusal is not a try. Every call a run makes says it never pauses sessions (D11).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

import sqlite_vec
from sqlalchemy import and_, select, text, update

from horizon.db import spaces
from horizon.db import tables as t
from horizon.events.bus import session_channel
from horizon.gateway.context import CallContext, call_ctx
from horizon.gateway.errors import ProviderError
from horizon.services.memory.block import memory_list
from horizon.services.memory.store import LostRace
from horizon.services.memory.stretch import (
    Msg,
    Present,
    Stretch,
    WriterResult,
    build_stretch,
    debate_header,
    watch_header,
)

if TYPE_CHECKING:
    from horizon.runtime import Runtime

log = logging.getLogger("horizon.memory")

PREFIX = "session:"
CONTEXT_REACH = 60          # messages before the checkpoint read for the context lines (only 6 kept ones are used)
REREAD_REACH = 10
NEAREST_K = 8               # the KNN reads a few and keeps the nearest still-current one (D16)
WriterMode = Literal["scripted", "defer", "write"]


@dataclass(frozen=True)
class RunContext:
    """What a writer gets besides the stretch (D12): the call contexts (never pausing sessions, D11), the clock, the
    memory knobs and the run's reads (`io`, the writer's only way to the database)."""

    world_id: str
    session_id: str
    now: Callable[[], datetime]
    knobs: Any = None
    io: Any = None

    def call(self, purpose: str, *, character_id: str | None = None) -> CallContext:
        return call_ctx(purpose, world_id=self.world_id, session_id=self.session_id, character_id=character_id,
                        pauses_sessions=False)


class RunIO:
    """The writer's reads (`horizon.ai.memory.writers.MemoryIO`), bound to one run's world (D16)."""

    def __init__(self, rt: Runtime, world_id: str) -> None:
        self.rt = rt
        self.world_id = world_id

    async def current(self, character_id: str) -> list[tuple[str, str, float]]:
        M = t.memory_items.c
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(select(M.id, M.text, M.importance).where(and_(
                M.character_id == character_id, M.world_id == self.world_id, M.superseded_by.is_(None))))).all()
        return [(str(r[0]), str(r[1]), float(r[2])) for r in rows]

    async def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        """The adds' one embedding in the active space (purpose `embed_doc`, never stored, never pausing sessions).
        None without a key or when it fails: the duplicate check is then case-folded equality only."""
        rt = self.rt
        if not texts or rt.keys.status() != "set":
            return None
        async with rt.db.read() as conn:
            space = await spaces.active(conn)
        ctx = call_ctx("embed_doc", world_id=self.world_id, pauses_sessions=False)
        try:
            async with rt.embed_slots.slot():
                got = await rt.ai.embedder(True).embed(texts, kind="document", space=space, ctx=ctx)
        except ProviderError as e:
            log.info("duplicate check without vectors: embedding failed (%s)", e.code)
            return None
        return space.id, list(got.vectors)

    async def nearest(self, character_id: str, space_id: str, vector: list[float]) -> tuple[str, float, float] | None:
        """The nearest current memory of this character in `space_id`: (id, cosine, importance), or None."""
        mem, _ = spaces.vec_tables(space_id)
        async with self.rt.db.read() as conn:
            try:
                rows = (await conn.execute(text(
                    f"SELECT m.id, v.distance, m.importance FROM {mem} v JOIN memory_items m ON m.rid = v.rid "
                    "WHERE v.embedding MATCH :q AND v.character_id = :c AND v.k = :n "
                    "AND m.character_id = :c AND m.world_id = :w AND m.superseded_by IS NULL ORDER BY v.distance"),
                    {"q": sqlite_vec.serialize_float32(vector), "c": character_id, "w": self.world_id,
                     "n": NEAREST_K})).all()
            except Exception:   # the space's tables are gone (retired under us): no vector check
                return None
        if not rows:
            return None
        return str(rows[0][0]), 1.0 - float(rows[0][1]), float(rows[0][2])


@dataclass
class _Run:
    sid: str
    task: asyncio.Task[None]
    characters: set[str] = field(default_factory=set)
    world_id: str | None = None


def writer_mode(rt: Runtime) -> WriterMode:
    """D8: an explicitly `scripted` profile writes nothing (and advances); no usable key defers; else write."""
    spec = rt.profile
    explicit = spec.overrides.get("memory_writer") or spec.profile
    if explicit == "scripted":
        return "scripted"
    if rt.keys.status() != "set":
        return "defer"
    return "write"


class MemoryRuns:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self._high: deque[str] = deque()
        self._normal: deque[str] = deque()
        self._queued: set[str] = set()
        self._running: dict[str, _Run] = {}
        self._again: set[str] = set()
        self._after_turn: set[str] = set()
        self._graces: dict[str, asyncio.Task[None]] = {}
        self.started = False
        self.log: list[dict[str, Any]] = []   # the last runs' outcomes (tests, the eval's timing)

    @property
    def knobs(self) -> Any:
        return self.rt.runtime_cfg.runtime.memory

    # ── lifecycle ──
    def start(self) -> None:
        if not self.started:
            self.rt.bus.watch(PREFIX, self._on_first, self._on_drained)
            self.started = True

    async def stop(self) -> None:
        """Shutdown never waits on DeepSeek: running runs are cancelled with their checkpoints unmoved, so the next
        start-up sweep reads the same lines (doc 09 M1 trigger 6)."""
        self.started = False
        for g in list(self._graces.values()):
            g.cancel()
        self._graces.clear()
        self._high.clear()
        self._normal.clear()
        self._queued.clear()
        self._again.clear()
        tasks = [r.task for r in self._running.values()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(BaseException):
                await task

    # ── requests ──
    def request(self, sid: str, *, high: bool = False, reason: str = "") -> None:
        if not self.started:
            return
        actor = self.rt.sessions.peek(sid) if self.rt._sessions is not None else None
        cur = getattr(actor, "current", None)
        if cur is not None and not getattr(cur, "closed", True):
            self._after_turn.add(sid)   # trigger 4: the kept reply is read once it ends
        if sid in self._running:
            self._again.add(sid)
            return
        if sid in self._queued:
            if high and sid in self._normal:
                self._normal.remove(sid)
                self._high.append(sid)
            return
        self._queued.add(sid)
        (self._high if high else self._normal).append(sid)
        log.debug("memory run requested for %s (%s)", sid, reason or "request")
        self._pump()

    def on_events(self, sid: str, events: Sequence[Mapping[str, Any]]) -> None:
        """Triggers 2–4, from what a session's actor just stored."""
        for e in events:
            typ = e.get("type")
            payload = e.get("payload") or {}
            if typ == "session.paused" and payload.get("reason") in ("navigated_away", "turn_cap"):
                self.request(sid, reason=str(payload.get("reason")))
            elif typ == "session.state" and payload.get("status") == "ended":
                self.request(sid, reason="ended")
            elif typ == "turn.end" and sid in self._after_turn:
                self._after_turn.discard(sid)
                self.request(sid, reason="kept turn ended")

    def _pump(self) -> None:
        while len(self._running) < max(1, int(self.knobs.max_concurrent)) and (self._high or self._normal):
            sid = self._high.popleft() if self._high else self._normal.popleft()
            self._queued.discard(sid)
            task: asyncio.Task[None] = self.rt.spawn(f"memory_run:{sid}", self._go(sid))
            self._running[sid] = _Run(sid=sid, task=task)
            task.add_done_callback(functools.partial(self._done, sid))

    def _done(self, sid: str, task: asyncio.Task[None]) -> None:
        run = self._running.get(sid)
        if run is not None and run.task is task:
            del self._running[sid]
        if not task.cancelled() and task.exception() is not None:
            log.error("memory run for %s failed: %r", sid, task.exception())
        if sid in self._again and self.started:
            self._again.discard(sid)
            self.request(sid, reason="again")
        if self.started:
            self._pump()

    async def drain(self) -> None:
        """Tests: wait until nothing is queued or running (the clock is driven by the caller)."""
        while self._running or self._high or self._normal:
            tasks = [r.task for r in self._running.values()]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                await asyncio.sleep(0)

    def busy(self, sid: str) -> bool:
        return sid in self._running or sid in self._queued

    # ── cancels (D8) ──
    def cancel(self, *, session: str | None = None, character: str | None = None, world: str | None = None) -> int:
        """Cancel the running runs this delete touches; queued ones re-read everything when they start."""
        n = 0
        for sid, run in list(self._running.items()):
            if (session is not None and sid == session) or (character is not None and character in run.characters) \
                    or (world is not None and run.world_id == world):
                run.task.cancel()
                self._again.discard(sid)
                n += 1
        if session is not None:
            self._dequeue(session)
            g = self._graces.pop(session, None)
            if g is not None:
                g.cancel()
        return n

    def cancel_all(self) -> int:
        n = 0
        for run in list(self._running.values()):
            run.task.cancel()
            n += 1
        for sid in list(self._queued):
            self._dequeue(sid)
        self._again.clear()
        return n

    def _dequeue(self, sid: str) -> None:
        self._queued.discard(sid)
        for q in (self._high, self._normal):
            with contextlib.suppress(ValueError):
                q.remove(sid)

    # ── trigger 1: the session stream left (event-streams "A session stream left empty is noticed") ──
    def _on_first(self, channel: str) -> None:
        g = self._graces.pop(channel[len(PREFIX):], None)
        if g is not None:
            g.cancel()

    def _on_drained(self, channel: str) -> None:
        sid = channel[len(PREFIX):]
        if not self.started or sid in self._graces:
            return
        self._graces[sid] = self.rt.spawn(f"memory_grace:{sid}", self._grace(sid))

    async def _grace(self, sid: str) -> None:
        try:
            await self.rt.clock.sleep(float(self.knobs.leave_grace_ms) / 1000)
        finally:
            if self._graces.get(sid) is asyncio.current_task():
                del self._graces[sid]
        if self.rt.bus.subscriber_count(session_channel(sid)) == 0:
            self.request(sid, reason="stream left")

    # ── triggers 5 and 6 ──
    async def opened(self, sid: str) -> None:
        """Trigger 5: another non-seed session in the world sharing a participant with unread lines runs first."""
        if not self.started:
            return
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(text(
                "SELECT DISTINCT s.id FROM sessions s JOIN participants p ON p.session_id = s.id "
                "WHERE s.is_seed = 0 AND s.id != :sid AND s.world_id = (SELECT world_id FROM sessions WHERE id = :sid) "
                "AND p.character_id IN (SELECT character_id FROM participants WHERE session_id = :sid) "
                "AND (s.memory_reread != '[]' OR (SELECT COALESCE(MAX(m.seq), 0) FROM messages m "
                "WHERE m.session_id = s.id) > s.memory_seq)"), {"sid": sid})).scalars().all()
        for other in rows:
            self.request(str(other), high=True, reason=f"{sid} opened")

    async def sweep(self) -> None:
        """Trigger 6: after `close_interrupted_streams`, every non-seed session with unread or re-read lines."""
        async with self.rt.db.read() as conn:
            rows = (await conn.execute(text(
                "SELECT s.id FROM sessions s WHERE s.is_seed = 0 AND (s.memory_reread != '[]' OR "
                "(SELECT COALESCE(MAX(m.seq), 0) FROM messages m WHERE m.session_id = s.id) > s.memory_seq) "
                "ORDER BY s.updated_at"))).scalars().all()
        for sid in rows:
            self.request(str(sid), reason="start-up sweep")

    # ── a run ──
    async def _go(self, sid: str) -> None:
        for _ in range(1000):   # pieces; each commits its own checkpoint
            if await self._one(sid) != "more":
                return

    async def _one(self, sid: str) -> str:
        rt = self.rt
        async with rt.db.read() as conn:
            srow = (await conn.execute(select(t.sessions).where(t.sessions.c.id == sid))).mappings().first()
            if srow is None or bool(srow["is_seed"]):
                return "done"
            parts = (await conn.execute(select(
                t.participants.c.character_id, t.participants.c.side, t.characters.c.profile,
                t.characters.c.deleted_at).join(t.characters, t.characters.c.id == t.participants.c.character_id)
                .where(t.participants.c.session_id == sid).order_by(t.participants.c.ord))).mappings().all()
        mode = writer_mode(rt)
        if mode == "defer":
            self._note(sid, "deferred")
            return "done"
        present_ids = [str(p["character_id"]) for p in parts if p["deleted_at"] is None]
        run = self._running.get(sid)
        if run is not None:
            run.characters = set(present_ids)
            run.world_id = str(srow["world_id"])
        async with rt.memory.run_locks(present_ids):
            pieces, upto, from_seq = await self._stretch(srow, parts)
            if not pieces:
                if (str(srow["status"]) == "ended" or mode == "scripted") and upto > from_seq:
                    await self._advance(sid, from_seq, upto, list(srow["memory_reread"] or []))
                    self._note(sid, "advanced", upto=upto)
                else:
                    self._note(sid, "below minimum")
                return "done"
            piece = pieces[0]
            if mode == "scripted":
                await self._advance(sid, piece.from_seq, piece.upto_seq, piece.reread_ids)
                self._note(sid, "scripted", upto=piece.upto_seq)
                return "more" if len(pieces) > 1 else "done"
            ctx = RunContext(world_id=piece.world_id, session_id=sid, now=rt.clock.now, knobs=self.knobs,
                             io=RunIO(rt, piece.world_id))
            try:
                result = await self._write(piece, ctx)
            except ProviderError as e:
                if e.code == "daily_budget_exceeded":
                    self._note(sid, "refused at the cap")   # not a try: the next trigger tries again
                    return "done"
                log.warning("memory run for %s failed: %s", sid, e.code)
                result = WriterResult(failed=True)
            except asyncio.CancelledError:
                raise
            except Exception:   # a bug inside the writer counts a try, like a failed call (D17)
                log.exception("memory writer for %s raised", sid)
                result = WriterResult(failed=True)
            if result.failed:
                await self._failed(sid, piece)
                return "done"
            commit = None
            for attempt in (1, 2):   # a failed commit retries once with no second call (doc 09 M6)
                try:
                    commit = await rt.memory.apply_run(
                        piece.world_id, result.ops, session_id=sid, from_seq=piece.from_seq, upto_seq=piece.upto_seq,
                        reread_done=piece.reread_ids, vectors=result.vectors, touched=result.touched,
                        read_variants={ln.message_id: ln.variant_id for ln in piece.lines
                                       if ln.reread and ln.variant_id})
                    break
                except LostRace:
                    log.info("memory run for %s lost the checkpoint race; nothing written", sid)
                    self._note(sid, "lost race")
                    return "done"
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if attempt == 2:
                        log.exception("memory run for %s could not commit", sid)
                        await self._failed(sid, piece)
                        return "done"
            assert commit is not None
            self._note(sid, "committed", upto=piece.upto_seq, changed=list(commit.changed),
                       dropped=[*result.log, *commit.dropped])
            self.after_commit(piece.world_id, commit.changed)
        return "more" if len(pieces) > 1 else "done"

    def after_commit(self, world_id: str, characters: Sequence[str]) -> None:
        """A live session holding one of these characters drops its cached memory list (D23): two tabs, trigger 5."""
        from horizon.services.memory.forget import drop_blocks

        drop_blocks(self.rt, characters)

    async def _write(self, piece: Stretch, ctx: RunContext) -> WriterResult:
        writer = self.rt.ai.memory_writer(True)
        on_stretch = getattr(writer, "on_stretch", None)
        if on_stretch is None:
            return WriterResult()
        result: WriterResult = await on_stretch(piece, ctx)
        return result

    async def _advance(self, sid: str, from_seq: int, upto: int, reread_done: Sequence[str]) -> bool:
        """Move the checkpoint with no memories (scripted, an ended session below the minimum, a skipped piece)."""
        async with self.rt.db.write() as tx:
            cur = (await tx.conn.execute(select(t.sessions.c.memory_reread).where(t.sessions.c.id == sid))).scalar()
            left = [i for i in (cur or []) if i not in set(reread_done)]
            res = await tx.conn.execute(update(t.sessions).where(and_(
                t.sessions.c.id == sid, t.sessions.c.memory_seq == from_seq)).values(
                memory_seq=upto, memory_tries=0, memory_reread=left))
            return bool(res.rowcount)

    async def _failed(self, sid: str, piece: Stretch) -> None:
        """A failed piece counts a try on its checkpoint; after `maxTries` it is skipped (doc 09 M6)."""
        async with self.rt.db.write() as tx:
            await tx.conn.execute(update(t.sessions).where(and_(
                t.sessions.c.id == sid, t.sessions.c.memory_seq == piece.from_seq)).values(
                memory_tries=t.sessions.c.memory_tries + 1))
            tries = (await tx.conn.execute(select(t.sessions.c.memory_tries).where(
                t.sessions.c.id == sid))).scalar()
        if tries is not None and int(tries) >= int(self.knobs.max_tries):
            log.warning("memory run for %s skipped messages %s–%s after %s failed tries", sid, piece.from_seq + 1,
                        piece.upto_seq, tries)
            await self._advance(sid, piece.from_seq, piece.upto_seq, piece.reread_ids)
            self._note(sid, "skipped", upto=piece.upto_seq)
        else:
            self._note(sid, "failed", tries=int(tries or 0))

    def _note(self, sid: str, outcome: str, **extra: Any) -> None:
        self.log.append({"sessionId": sid, "outcome": outcome, "at": self.rt.now_iso(), **extra})
        del self.log[:-200]

    async def _stretch(self, srow: Any, parts: Sequence[Any]) -> tuple[list[Stretch], int, int]:
        rt = self.rt
        sid = str(srow["id"])
        world_id = str(srow["world_id"])
        from_seq = int(srow["memory_seq"])
        reread = [str(i) for i in (srow["memory_reread"] or [])]
        now = rt.clock.now()
        async with rt.db.read() as conn:
            w = (await conn.execute(select(t.worlds.c.name, t.worlds.c.you).where(t.worlds.c.id == world_id))).first()
            M = t.messages.c
            reread_seqs = [int(x) for x in (await conn.execute(select(M.seq).where(and_(
                M.session_id == sid, M.id.in_(reread))))).scalars()] if reread else []
            lowest = min([from_seq - CONTEXT_REACH, *[s - REREAD_REACH for s in reread_seqs]])
            rows = (await conn.execute(select(
                M.id, M.seq, M.author_type, M.author_character_id, M.kind, M.content, M.status, M.active_variant_id,
                M.debate).where(and_(M.session_id == sid, M.seq > lowest)).order_by(M.seq))).mappings().all()
            present: list[Present] = []
            for p in parts:
                if p["deleted_at"] is not None:
                    continue
                prof = p["profile"] or {}
                listed, _ = await memory_list(conn, str(p["character_id"]), world_id, now, self.knobs)
                present.append(Present(n=len(present) + 1, character_id=str(p["character_id"]),
                                       name=str(prof.get("name") or p["character_id"]), role=str(prof.get("role") or ""),
                                       memories=listed, about=str((prof.get("personality") or {}).get("summary") or "")))
        names = {str(p["character_id"]): str((p["profile"] or {}).get("name") or p["character_id"]) for p in parts}
        msgs = [Msg(id=str(r["id"]), seq=int(r["seq"]), author_type=str(r["author_type"]),
                    character_id=r["author_character_id"], kind=str(r["kind"]), content=str(r["content"] or ""),
                    status=str(r["status"]), variant_id=str(r["active_variant_id"] or f"{r['id']}_v1"),
                    phase=(r["debate"] or {}).get("phase") if r["debate"] else None) for r in rows]
        you = (w[1] if w is not None else None) or {}
        user_name = str(you.get("displayName") or "") or "the user"
        mode = str(srow["mode"])
        config = srow["config"] or {}
        header = ""
        if mode == "debate":
            sides: dict[str, list[str]] = {"prop": [], "opp": []}
            for p in parts:
                if p["side"] in sides:
                    sides[str(p["side"])].append(names[str(p["character_id"])])
            state = srow["state"] or {}
            verdict = state.get("verdict") or (state.get("debate") or {}).get("verdict")
            header = debate_header(config, sides, verdict)
        elif mode == "watch":
            header = watch_header(config)
        pieces, upto = build_stretch(session_id=sid, world_id=world_id, world_name=str(w[0]) if w else "",
                                     user_name=user_name, mode=mode, header=header, msgs=msgs, from_seq=from_seq,
                                     reread_ids=reread, present=present, names=names,
                                     piece_tokens=int(self.knobs.piece_tokens))
        return pieces, upto, from_seq
