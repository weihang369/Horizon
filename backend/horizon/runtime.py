"""The backend runtime: everything the app holds between requests, and the startup lifespan (doc 01 §8).

Startup (in order): create `data/` → logging → `alembic upgrade head` → SpaceManager → seed if empty →
close leftover `streaming` messages → build the gateway, sessions and job scheduler → recover jobs (M4, step 6: never
sent → requeued; result stored → derived only; sent without a result → failed, retryable) → drain the AI purge queue
(M3) → resume cost corrections (M2) → sweeper.

M4 (generation-jobs design D1): the JobScheduler, `image_slots` (2) and `music_slots` (1) beside the shared
`llm_slots`, and the test-mode job faults. `stop()` and the factory reset stop the scheduler first.

M2 (design D15): the key store, the gateway (the in-process fake provider in test mode), the reservation book, the
ledger writer, per-character energy locks and the cost corrector are built on start and torn down on stop, so a factory
reset drops reservations, the rejected-key memory and the secrets file together.

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
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import select, text

from horizon import logs
from horizon.ai.decider import Decider, DeciderFixtures
from horizon.ai.hooks import AiStateHooks, NoOpHooks
from horizon.ai.image_prompt import ImagePromptCompiler
from horizon.ai.profile import AiPorts, ProfileSpec
from horizon.ai.scripted.ports import AiDeps
from horizon.config import Config
from horizon.contract import mappers as mp
from horizon.contract.validate import ContractSchema, default_schema
from horizon.db import spaces
from horizon.db import tables as t
from horizon.db.migrate import upgrade_head
from horizon.db.uow import Database
from horizon.domain.clock import Clock, FrozenClock, SystemClock, calendar_for
from horizon.domain.energy import energy_day as _energy_day_ms
from horizon.domain.ids import new_id
from horizon.domain.pricing import PriceTable, load_price_table
from horizon.domain.runtime_config import RuntimeConfig, load_runtime_config
from horizon.domain.timeutil import ms_from_iso, to_iso
from horizon.domain.vclock import Slots
from horizon.events.bus import GLOBAL, EventBus, session_channel
from horizon.gateway.client import HttpCore
from horizon.gateway.fake import FakeOpenRouter
from horizon.gateway.pipeline import Caps, Gateway
from horizon.gateway.reservations import ReservationBook
from horizon.gateway.types import GatewayConfig
from horizon.services import seed as seeding
from horizon.services.corrector import CostCorrector
from horizon.services.energy_writes import EnergyLocks, EnergyParams
from horizon.services.keys import KeyStore
from horizon.services.ledger import LedgerWriter
from horizon.services.purge import PurgeWorker
from horizon.services.runtime.reducer import apply_event, initial_runtime, ordered_messages
from horizon.services.settings import deep_merge, local_day, read_local_settings, read_seed_settings

log = logging.getLogger("horizon.runtime")
T = TypeVar("T")


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
    async def closed(self) -> AsyncIterator[None]:
        """Close the gate and wait for every in-flight request. The reset's own request is not gated (middleware
        `UNGATED_SUFFIXES`), so there is none to leave out: counting one let the reset dispose the database under a
        request still writing, whose connection then kept `horizon.db` open."""
        self._open.clear()
        try:
            await self._idle.wait()
            yield
        finally:
            self._open.set()


class Runtime:
    def __init__(self, cfg: Config, *, clock: Clock | None = None, schema: ContractSchema | None = None) -> None:
        self.cfg = cfg
        self.schema = schema or default_schema()
        self.prices: PriceTable = load_price_table(cfg.seed_dir)
        peak = self.prices.peak
        cal = calendar_for(cfg.tz, peak_tz=peak.tz, windows=peak.windows)
        # Test mode: a released FrozenClock, so `/_test/clock` can freeze it in place (everything holding it follows).
        self.clock: Clock = clock or (FrozenClock(cal, released=True) if cfg.test_mode else SystemClock(cal))
        self.bus = EventBus()
        self.gate = Gate()
        self._db: Database | None = None
        self.space_id: str | None = None
        self.seed_settings: dict[str, Any] = {}
        self._seed: seeding.SeedData | None = None
        self.started = False
        self.sse_ping_sec = 15.0
        self.loop: asyncio.AbstractEventLoop | None = None
        # M2: built in start(), torn down in stop().
        self.energy_locks = EnergyLocks()
        self.book = ReservationBook()
        self._keys: KeyStore | None = None
        self._gateway: Gateway | None = None
        self._corrector: CostCorrector | None = None
        self._decider: Decider | None = None
        self.decider_fixtures = DeciderFixtures()
        self.settings_lock = asyncio.Lock()
        self.fake: FakeOpenRouter | None = None
        # M3 (session-runtime design D1): the pacing table, LLM slots, AI ports, the live sessions and the purge worker.
        self.runtime_cfg: RuntimeConfig = load_runtime_config(cfg.seed_dir)
        self.llm_slots = Slots(self.runtime_cfg.runtime.llm_concurrency)
        self.profile = ProfileSpec.from_env(cfg.ai_env)
        self.hooks: AiStateHooks = NoOpHooks()
        self._ledger: LedgerWriter | None = None
        self._sessions: Any = None
        self._ai: AiPorts | None = None
        self._purge: PurgeWorker | None = None
        self.stream_faults: list[int] = []   # test mode: `stream_cut` one-shot faults (afterTokens), consumed per turn
        # M4 (generation-jobs design D1): the scheduler, provider slots, scenario faults, palettes and the compiler.
        self.image_slots = Slots(2)
        self.music_slots = Slots(1)
        self.job_faults: str | None = None   # test mode: "partial" | "all" | "song" (design D12)
        self._jobs: Any = None
        self.palettes: dict[str, tuple[str, str, str]] = load_palettes(cfg.seed_dir)
        self.prompt_compiler = ImagePromptCompiler(load_style_presets(cfg.seed_dir))

    # ── accessors ──
    @property
    def db(self) -> Database:
        if self._db is None:
            raise RuntimeError("runtime not started")
        return self._db

    @property
    def keys(self) -> KeyStore:
        if self._keys is None:
            raise RuntimeError("runtime not started")
        return self._keys

    @property
    def gateway(self) -> Gateway:
        if self._gateway is None:
            raise RuntimeError("runtime not started")
        return self._gateway

    @property
    def corrector(self) -> CostCorrector:
        if self._corrector is None:
            raise RuntimeError("runtime not started")
        return self._corrector

    @property
    def decider(self) -> Decider:
        if self._decider is None:
            raise RuntimeError("runtime not started")
        return self._decider

    @property
    def ledger(self) -> LedgerWriter:
        if self._ledger is None:
            raise RuntimeError("runtime not started")
        return self._ledger

    @property
    def sessions(self) -> Any:
        """The LiveSessionManager (`horizon.sessions.manager`)."""
        if self._sessions is None:
            raise RuntimeError("runtime not started")
        return self._sessions

    @property
    def ai(self) -> AiPorts:
        if self._ai is None:
            raise RuntimeError("runtime not started")
        return self._ai

    @property
    def jobs(self) -> Any:
        """The JobScheduler (`horizon.services.jobs.scheduler`)."""
        if self._jobs is None:
            raise RuntimeError("runtime not started")
        return self._jobs

    def palette_ids(self) -> list[str]:
        return list(self.palettes)

    def palette(self, palette_id: str) -> tuple[str, str, str]:
        """(stage, primary, secondary) colours for the scripted placeholder portrait."""
        return self.palettes.get(palette_id) or next(iter(self.palettes.values()), ("#1A1A22", "#FF4D2E", "#FFB199"))

    @property
    def purge(self) -> PurgeWorker:
        if self._purge is None:
            raise RuntimeError("runtime not started")
        return self._purge

    def take_stream_fault(self) -> int | None:
        """The next character turn's `stream_cut` fault (afterTokens), consumed once."""
        return self.stream_faults.pop(0) if self.stream_faults else None

    def set_profile(self, spec: ProfileSpec) -> None:
        self.profile = spec
        if self._ai is not None:
            self._ai = AiPorts(self._ai.deps, spec)

    def settings_doc(self) -> dict[str, Any]:
        """Seed settings overlaid by the local file (the editable layer; computed fields come from services/settings)."""
        return deep_merge(self.seed_settings, self.local_settings())

    def caps(self) -> Caps:
        b = self.settings_doc()["budget"]
        return Caps(daily_cap_usd=float(b["dailyCapUsd"]), creation_cap_usd=float(b["perCharacterCreationCapUsd"]),
                    warn_at_pct=float(b["warnAtPct"]))

    def utc_offset_min(self) -> int:
        offset = self.clock.calendar.local(self.clock.now()).utcoffset()
        return int(offset.total_seconds() // 60) if offset is not None else 0

    def energy_params(self) -> EnergyParams:
        return EnergyParams(now_ms=ms_from_iso(self.now_iso()), frozen=self.keys.demo_mode(),
                            est_reply_points=self.est_reply_points(),
                            usd_per_point=float(self.settings_doc()["energy"]["usdPerPoint"]),
                            utc_offset_min=self.utc_offset_min())

    def _settings_changed(self) -> None:
        self.publish(GLOBAL, {"type": "entity.changed", "kind": "settings"})

    def _build_m2(self) -> None:
        cfg = self.cfg
        models = self.seed_settings["models"]
        self._keys = KeyStore(cfg.openrouter_key, cfg.data_dir, on_change=self._settings_changed)
        self.fake = (FakeOpenRouter(models=models.values(), image_cost=self.prices.generation["portrait"])
                     if cfg.test_mode else None)
        core = HttpCore(self._keys, transport=self.fake.transport() if self.fake else None)
        ledger = self._ledger = LedgerWriter(self.db, self.clock, self.energy_locks, self.energy_params)
        self.book.clear()
        self._gateway = Gateway(core=core, cfg=GatewayConfig.from_mapping(self.prices.gateway), prices=self.prices,
                                book=self.book, ledger=ledger, caps=self.caps, period=self.clock.pricing_period,
                                publish=lambda ev: self.publish(GLOBAL, ev), decision_model=str(models["decision"]),
                                on_estimate_row=lambda row_id: self.corrector.enqueue(row_id))
        self._corrector = CostCorrector(self.db, self.clock, self._gateway.meta.generation, self.energy_locks,
                                        self.energy_params)
        self._decider = Decider(self._gateway.decide, self._gateway.cfg.timeouts, self.decider_fixtures)

    def _build_m3(self) -> None:
        from horizon.sessions.manager import LiveSessionManager

        manager = LiveSessionManager(self)
        self._sessions = manager
        self.gateway.on_spend = manager.on_spend
        self.gateway.on_budget = manager.on_budget
        deps = AiDeps(gateway=lambda: self.gateway, decider=lambda: self.decider, prices=self.prices,
                      timing=self.runtime_cfg.timing, clock=lambda: self.clock,
                      window_tokens=self.runtime_cfg.runtime.window_tokens, palette_ids=self.palette_ids,
                      schema=lambda: self.schema)
        self._ai = AiPorts(deps, self.profile)
        self._purge = PurgeWorker(self.db, self.hooks, self.now_iso)
        self._purge.start()

    def _build_m4(self) -> None:
        from horizon.services.jobs.scheduler import JobScheduler

        self._jobs = JobScheduler(self)

    async def _stop_m4(self) -> None:
        if self._jobs is not None:
            await self._jobs.stop()
        self._jobs = None

    async def _stop_m3(self) -> None:
        if self._sessions is not None:
            await self._sessions.shutdown()
        if self._purge is not None:
            await self._purge.stop()
        self._sessions = self._purge = None

    async def _stop_m2(self) -> None:
        if self._decider is not None:
            await self._decider.stop()  # late decisions are recorded at their estimate on the way out
        if self._gateway is not None:
            await self._gateway.drain_background()  # before the corrector stops: a late row may still enqueue into it
        if self._corrector is not None:
            await self._corrector.stop()
        if self._gateway is not None:
            await self._gateway.core.aclose()
        self.book.clear()
        self._gateway = self._corrector = self._keys = self._decider = None

    def spawn(self, name: str, coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        """The only way `sessions/` and `ai/` start background work: the task holds an activity token while it runs,
        so a virtual-time advance waits for it (session-runtime D2)."""
        return self.clock.activity.spawn(name, coro)

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
        self.clock.period_override = None
        self.stream_faults = []
        self.job_faults = None
        self._build_m2()
        self._build_m3()  # step 7 (drain ai_purge_queue) starts with the purge worker
        self._build_m4()
        await self.jobs.recover()  # step 6, before the first request is served
        await self.corrector.scan()
        await asyncio.to_thread(sweep, cfg.data_dir, self.referenced_files_sync())
        self.started = True
        log.info("horizon backend ready (data=%s, test_mode=%s)", cfg.data_dir, cfg.test_mode)

    async def stop(self) -> None:
        await self._stop_m4()
        await self._stop_m3()
        await self._stop_m2()
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
        if self._sessions is not None:  # seed sessions are replay-only, but drop any actor that read their old events
            for sid in [s.session["id"] for s in data.sessions]:
                await self._sessions.release(sid)
        if self._jobs is not None:  # M4: user jobs on seed characters are cancelled; overlay jobs are re-adopted below
            await self._jobs.before_reset({c["id"] for c in data.characters}, {j["id"] for j in data.jobs})
        async with self.db.write() as tx:
            sids = await seeding.apply_seed(tx.conn, data, energy_day=self.energy_day, local_day=self.local_day)
            if sids:
                await tx.conn.execute(t.ai_purge_queue.insert().values(scope="session", ids=sids, created_at=self.now_iso(),
                                                                       attempts=0, done_at=None))
            tx.publish(GLOBAL, {"type": "mock.reset"})
        if self._jobs is not None:
            await self._jobs.recover()

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


def load_palettes(seed_dir: Path) -> dict[str, tuple[str, str, str]]:
    doc = json.loads((seed_dir / "palettes.json").read_text(encoding="utf-8"))
    return {str(p["id"]): (str(p.get("stage", "#1A1A22")), str(p["primary"]), str(p["secondary"])) for p in doc["data"]}


def load_style_presets(seed_dir: Path) -> list[dict[str, Any]]:
    doc = json.loads((seed_dir / "style-presets.json").read_text(encoding="utf-8"))
    return list(doc["data"])


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


def wipe_data_dir(data_dir: Path, *, attempts: int = 10, delay: float = 0.2) -> None:
    """Delete everything in `data/` except `models/`, retrying for Windows file locks (doc 02 §4). The back-off grows
    (≈ 11 s in all): a virus scan or the indexer can hold `horizon.db` for a moment after a burst of writes."""
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
                time.sleep(delay * (i + 1))
