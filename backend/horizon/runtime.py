"""The backend runtime: everything the app holds between requests, and the startup lifespan (doc 01 §8).

Startup (in order): create `data/` → logging → `alembic upgrade head` → SpaceManager → seed if empty →
close leftover `streaming` messages → [recover jobs: M4] → [drain the AI purge queue: M3] → sweeper.

`factory_reset()` runs the Windows-safe sequence (doc 02 §4, design D12) behind a lifecycle gate: new requests
wait, in-flight requests drain, the engines and log file are closed, `data/` is removed except `models/`, and
startup runs again in the same process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import stat
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from horizon import logs
from horizon.config import Config
from horizon.contract import mappers as mp
from horizon.contract.validate import ContractSchema, default_schema
from horizon.db import spaces
from horizon.db import tables as t
from horizon.db.migrate import upgrade_head
from horizon.db.uow import Database
from horizon.domain.clock import Clock, SystemClock, calendar_for
from horizon.domain.energy import energy_day as _energy_day_ms
from horizon.domain.ids import new_id
from horizon.domain.timeutil import ms_from_iso, to_iso
from horizon.events.bus import GLOBAL, EventBus, session_channel
from horizon.services import seed as seeding
from horizon.services.runtime.reducer import apply_event, initial_runtime, ordered_messages
from horizon.services.settings import local_day, read_local_settings, read_seed_settings

log = logging.getLogger("horizon.runtime")


class Gate:
    """Lifecycle gate: closed during a factory reset. Requests wait for it, and the reset waits for in-flight ones."""

    def __init__(self) -> None:
        self._open = asyncio.Event()
        self._open.set()
        self._inflight = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @asynccontextmanager
    async def request(self) -> AsyncIterator[None]:
        await self._open.wait()
        self._inflight += 1
        self._idle.clear()
        try:
            yield
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()

    @asynccontextmanager
    async def closed(self, own_requests: int = 1) -> AsyncIterator[None]:
        self._open.clear()
        try:
            while self._inflight > own_requests:
                self._idle.clear()
                await asyncio.sleep(0.01)
            yield
        finally:
            self._open.set()


class Runtime:
    def __init__(self, cfg: Config, *, clock: Clock | None = None, schema: ContractSchema | None = None) -> None:
        self.cfg = cfg
        self.schema = schema or default_schema()
        self.clock: Clock = clock or SystemClock(calendar_for(cfg.tz))
        self.bus = EventBus()
        self.gate = Gate()
        self._db: Database | None = None
        self.space_id: str | None = None
        self.seed_settings: dict[str, Any] = {}
        self._seed: seeding.SeedData | None = None
        self.started = False
        self.sse_ping_sec = 15.0
        self.loop: asyncio.AbstractEventLoop | None = None

    # ── accessors ──
    @property
    def db(self) -> Database:
        if self._db is None:
            raise RuntimeError("runtime not started")
        return self._db

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        if self.cfg.test_mode:
            def_name = "GlobalEvent" if channel == GLOBAL else None
            if def_name:
                self.schema.check(def_name, event)
        self.bus.publish(channel, event)

    def local_settings(self) -> dict[str, Any]:
        return read_local_settings(self.cfg.settings_local_path)

    def est_reply_points(self) -> float:
        return float(self.seed_settings["energy"]["estReplyPoints"][self.clock.pricing_period()])

    def energy_day(self, at_iso: str) -> str:
        offset = self.clock.calendar.local(self.clock.now()).utcoffset()
        minutes = int(offset.total_seconds() // 60) if offset is not None else 0
        return _energy_day_ms(ms_from_iso(at_iso), minutes)

    def local_day(self, at_iso: str) -> str:
        return local_day(self.clock, at_iso)

    def now_iso(self) -> str:
        return to_iso(self.clock.now())

    # ── lifecycle ──
    async def start(self) -> None:
        cfg = self.cfg
        self.loop = asyncio.get_running_loop()
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        logs.setup_logging(cfg.logs_dir, cfg.log_level)
        self.seed_settings = read_seed_settings(cfg.seed_dir)
        await asyncio.to_thread(upgrade_head, cfg.db_path)
        self._db = Database(cfg.db_path, publish=self.publish)
        async with self.db.write() as tx:
            await spaces.drop_retired(tx.conn)
            self.space_id = await spaces.ensure_active(tx.conn, self.now_iso())
            await tx.conn.execute(t.idempotency_keys.delete().where(
                (t.idempotency_keys.c.state == "in_flight") | (t.idempotency_keys.c.expires_at < self.now_iso())))
        async with self.db.read() as conn:
            empty = not await seeding.has_worlds(conn)
        if empty:
            await self.import_seed()
        await self.close_interrupted_streams()
        # Step 6 (recover jobs) arrives with M4; step 7 (drain ai_purge_queue) with M3.
        await asyncio.to_thread(sweep, cfg.data_dir, self.referenced_files_sync())
        self.started = True
        log.info("horizon backend ready (data=%s, test_mode=%s)", cfg.data_dir, cfg.test_mode)

    async def stop(self) -> None:
        self.bus.close_all()
        if self._db is not None:
            await self._db.dispose()
            self._db = None
        self.started = False

    # ── seed ──
    async def load_seed(self) -> seeding.SeedData:
        if self._seed is None:
            self._seed = await asyncio.to_thread(seeding.load_seed, self.cfg.seed_dir, self.schema,
                                                 include_mock=self.cfg.test_mode)
        return self._seed

    async def import_seed(self) -> list[str]:
        data = await self.load_seed()
        async with self.db.write() as tx:
            return await seeding.apply_seed(tx.conn, data, energy_day=self.energy_day, local_day=self.local_day)

    async def reset_demo(self) -> None:
        """POST /admin/reset-demo (doc 02 §4): re-seed seed records in place; user data survives."""
        data = await self.load_seed()
        async with self.db.write() as tx:
            sids = await seeding.apply_seed(tx.conn, data, energy_day=self.energy_day, local_day=self.local_day)
            if sids:
                await tx.conn.execute(t.ai_purge_queue.insert().values(scope="session", ids=sids, created_at=self.now_iso(),
                                                                       attempts=0, done_at=None))
            tx.publish(GLOBAL, {"type": "mock.reset"})

    async def factory_reset(self) -> None:
        """Wipe `data/` except `models/` and start again in-process (Windows-safe)."""
        async with self.gate.closed():
            await self.stop()
            logs.close_file_logging()
            await asyncio.to_thread(wipe_data_dir, self.cfg.data_dir)
            self._seed = None
            await self.start()

    # ── recovery ──
    async def close_interrupted_streams(self) -> None:
        """Startup step 5: a message left `streaming` by a crash is closed with `turn.end` (interrupted by error)."""
        async with self.db.read() as conn:
            open_sessions = (await conn.execute(select(t.messages.c.session_id).where(t.messages.c.status == "streaming")
                                                .distinct())).scalars().all()
        for sid in open_sessions:
            async with self.db.write() as tx:
                await self._close_streams(tx.conn, sid, tx.publish)

    async def _close_streams(self, conn: Any, sid: str, publish: Any) -> None:
        srow = (await conn.execute(select(t.sessions).where(t.sessions.c.id == sid))).mappings().one()
        parts = (await conn.execute(select(t.participants).where(t.participants.c.session_id == sid))).mappings().all()
        mrows = (await conn.execute(select(t.messages).where(t.messages.c.session_id == sid))).mappings().all()
        last_seq = (await conn.execute(text("SELECT COALESCE(MAX(seq), 0) FROM session_events WHERE session_id = :s"),
                                       {"s": sid})).scalar_one()
        state = initial_runtime(mp.session_wire(srow, parts), [mp.message_wire(m) for m in mrows])
        state["lastSeq"] = last_seq
        for m in [m for m in mrows if m["status"] == "streaming"]:
            last_seq += 1
            evt = {"id": new_id("evt"), "sessionId": sid, "seq": last_seq, "at": self.now_iso(),
                   "type": "turn.end", "payload": {"messageId": m["id"], "status": "interrupted", "interruptedBy": "error"}}
            state = apply_event(state, evt)
            await conn.execute(t.session_events.insert().values(**mp.event_row(evt)))
            publish(session_channel(sid), evt)
        for msg in ordered_messages(state):
            row = mp.message_row(msg)
            await conn.execute(t.messages.update().where(t.messages.c.id == msg["id"]).values(
                **{k: v for k, v in row.items() if k != "id"}))
        srow2, _ = mp.session_rows(state["session"], is_seed=bool(srow["is_seed"]))
        await conn.execute(t.sessions.update().where(t.sessions.c.id == sid).values(
            **{k: v for k, v in srow2.items() if k not in ("id", "is_seed")}))

    def referenced_files_sync(self) -> set[str]:
        """Relative paths under `data/assets/` that rows point at (the sweeper keeps these)."""
        import sqlite3

        refs: set[str] = set()
        if not self.cfg.db_path.is_file():
            return refs
        con = sqlite3.connect(self.cfg.db_path)
        try:
            for (rel,) in con.execute("SELECT rel_path FROM image_assets WHERE rel_path IS NOT NULL "
                                      "UNION SELECT rel_path FROM theme_songs WHERE rel_path IS NOT NULL"):
                refs.add(str(rel))
            for (cover,) in con.execute("SELECT cover FROM worlds"):
                url = (json.loads(cover) if cover else {}).get("url")
                if url:
                    refs.add(mp.url_to_rel(url) or "")
        finally:
            con.close()
        return refs


def sweep(data_dir: Path, referenced: set[str], *, max_age_s: float = 3600) -> int:
    """Startup sweeper (doc 02 §2): remove `*.tmp` files and unreferenced generated files older than an hour."""
    removed = 0
    now = time.time()
    for root in (data_dir / "assets", data_dir / "knowledge", data_dir / "originals"):
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix == ".tmp":
                p.unlink(missing_ok=True)
                removed += 1
                continue
            if root.name == "assets":
                rel = p.relative_to(root).as_posix()
                if rel.startswith("gen/") and rel not in referenced and now - p.stat().st_mtime > max_age_s:
                    p.unlink(missing_ok=True)
                    removed += 1
    return removed


def _on_rm_error(func: Any, path: str, _exc: Any) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def wipe_data_dir(data_dir: Path, *, attempts: int = 5, delay: float = 0.2) -> None:
    """Delete everything in `data/` except `models/`, retrying for Windows file locks (doc 02 §4)."""
    if not data_dir.is_dir():
        return
    for child in list(data_dir.iterdir()):
        if child.name == "models":
            continue
        for i in range(attempts):
            try:
                if child.is_dir():
                    shutil.rmtree(child, onexc=_on_rm_error)
                else:
                    child.unlink(missing_ok=True)
                break
            except OSError:
                if i == attempts - 1:
                    raise
                time.sleep(delay)
