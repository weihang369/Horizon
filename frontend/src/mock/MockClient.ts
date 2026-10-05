// MockClient: the UI-phase HorizonClient (doc 05 §7, EE paper §2.3, R1/R15/R16). Owner: EE.
// In-memory DB loaded from seed/, snapshotted to localStorage by fixture hash. Live turns are generated event
// scripts played through ScriptPlayer on a virtual clock (demo speed ×1/×2/×4). Demo mode (R15): `sk-or-*` is a
// valid mock key, `sk-or-bad…` an invalid one; live actions without a key reject with missing_key (→ O05).
import type {
  AppSettings, Character, DebateConfig, Emotion, Energy, GroupConfig, MusicPolicy, Participant, Session,
  SessionEvent, StreamEvent, UsageRecord, WatchConfig, WatchState, World,
  SessionSettingsPatch,
} from "../contract/types";
import { CREATION_STEPS, EMOTIONS } from "../contract/types";
import { HorizonError } from "../contract/errors";
import type {
  CharacterPatch, CreateSessionInput, DeepPartial, GlobalEvent, HorizonClient, JobEvent, SessionSnapshot,
  StartJobInput, Unsubscribe, UsageSummary, WorldInput,
} from "../client/HorizonClient";
import { chatCostUsd, round6 } from "../domain/cost";
import {
  canTopUp, energyDay, energyState, EST_REPLY_POINTS, fullAt, makeEnergy, pointsForCost, regenAt, settle, topUp, toWireEnergy, withMax,
} from "../domain/energy";
import { MODELS } from "./pricing.config";
import { pricePeriod, rushHourInfo } from "../domain/rushHour";
import type { PricePeriod } from "../domain/rushHour";
import { ScriptPlayer } from "../engine/ScriptPlayer";
import type { TimelineEntry } from "../engine/ScriptPlayer";
import { applyEvent, initialRuntime, orderedMessages } from "../engine/sessionReducer";
import { forkEvents } from "../engine/fork";
import { shadowDataUrl, specFromAppearance } from "../vfx/shadow";
import type { Dataset } from "./db/dataset";
import { cloneDataset } from "./db/dataset";
import { loadSeedDataset } from "./db/loadSeed";
import type { KV } from "./db/persist";
import { defaultStorage, loadSnapshot, saveSnapshot } from "./db/persist";
import * as debateEngine from "./engines/debate";
import { DEFAULT_RUBRIC } from "./engines/debate";
import * as groupEngine from "./engines/group";
import type { EngineHost, LiveSession } from "./engines/host";
import { clearLive, systemNote } from "./engines/host";
import { estimateJob, JobRunner } from "./engines/jobs";
import type { JobHost } from "./engines/jobs";
import type { KnowledgeHost, Prepared } from "./engines/knowledge";
import * as knowledgeEngine from "./engines/knowledge";
import * as oneEngine from "./engines/oneOnOne";
import * as watchEngine from "./engines/watch";
import { footnoteCitations } from "./script/citations";
import { createRng, iso, makeId } from "./rng";
import type { Faults, Scenario, ScenarioId } from "./scenarios";
import { SCENARIO_BY_ID, isScenarioId } from "./scenarios";
import type { Clock } from "./time/Clock";
import { realClock } from "./time/Clock";
import { Scheduler } from "./time/Scheduler";
import type { DemoSpeed, TimingConfig } from "./timing.config";
import { DEFAULT_TIMING } from "./timing.config";

export interface MockClientOptions {
  /** Base clock (ManualClock in tests). */
  clock?: Clock;
  /** Snapshot storage; null disables persistence. Default: localStorage. */
  storage?: KV | null;
  /** Preloaded seed dataset (tests); default loads seed/ lazily. */
  dataset?: Dataset;
  speed?: DemoSpeed;
  scenario?: ScenarioId;
}

export interface MockDevState { scenario: ScenarioId; speed: DemoSpeed; ready: boolean }

/** Dev-only controls for the O18 switcher (not part of HorizonClient). */
export interface MockDevApi {
  readonly ready: Promise<void>;
  getState(): MockDevState;
  subscribe(cb: (s: MockDevState) => void): Unsubscribe;
  setScenario(id: ScenarioId): Promise<void>;
  setSpeed(speed: DemoSpeed): void;
  resetDemoData(): Promise<void>;
  setMockKey(): Promise<void>;
}

const DEV_KEY = "horizon.mock.dev.v1";
const clone = <T>(x: T): T => structuredClone(x);

const isEnergy = (x: object): x is Energy => "regenPerHour" in x && "current" in x && "asOf" in x;
/** The wire form of a result (doc backend/04 §4): energy is stored REAL, but `current` / `spentToday` leave floored. */
function toWire<T>(x: T): T {
  const out = clone(x);
  const fix = (v: unknown): void => {
    if (!v || typeof v !== "object") return;
    if (Array.isArray(v)) { v.forEach(fix); return; }
    const o = v as Record<string, unknown>;
    if (isEnergy(o)) Object.assign(o, toWireEnergy(o));
    else if (o.energy && typeof o.energy === "object" && isEnergy(o.energy)) o.energy = toWireEnergy(o.energy);
    else if (o.character && typeof o.character === "object") fix(o.character);
  };
  fix(out);
  return out;
}

// rev 1.3 error helpers (doc backend/03 §2): 404 not_found · 400/413/422 validation · 409 conflict. Never retryable.
const notFound = (what: string) => new HorizonError("not_found", `${what} not found.`, { retryable: false });
const invalid = (message: string, details?: Record<string, unknown>) => new HorizonError("validation", message, { retryable: false, details });
const conflict = (message: string, details?: Record<string, unknown>) => new HorizonError("conflict", message, { retryable: false, details });

/** rev 1.3 cover upload: PNG / JPEG / WebP ≤ 5 MB (checked by MIME and magic bytes, like the backend). */
const COVER_MAGIC: Record<string, number[]> = { "image/png": [0x89, 0x50, 0x4e, 0x47], "image/jpeg": [0xff, 0xd8, 0xff], "image/webp": [0x52, 0x49, 0x46, 0x46] };
const COVER_MAX_BYTES = 5 * 1024 * 1024;
/** Small covers become a data URL (kept in the snapshot); larger ones an object URL for this tab only. */
const COVER_INLINE_BYTES = 512 * 1024;
async function coverUrl(file: File): Promise<string> {
  const magic = COVER_MAGIC[file.type];
  if (!magic) throw invalid("Covers must be PNG, JPEG or WebP.", { field: "file", accepted: Object.keys(COVER_MAGIC) });
  if (file.size > COVER_MAX_BYTES) throw invalid("Covers can be at most 5 MB.", { field: "file", limit: COVER_MAX_BYTES, bytes: file.size });
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!magic.every((b, i) => bytes[i] === b)) throw invalid("That file isn't a valid image.", { field: "file" });
  if (file.size > COVER_INLINE_BYTES) return URL.createObjectURL(file);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return `data:${file.type};base64,${btoa(bin)}`;
}

/** D-70 tombstone: identity, palette and the active neutral portrait survive; everything else is emptied. */
function tombstone(c: Character, deletedAt: string): Character {
  const p = c.profile;
  const emotions = Object.fromEntries(Object.keys(c.emotions).map((e) => [e, null])) as Character["emotions"];
  emotions.neutral = c.emotions.neutral;
  return {
    ...c,
    profile: {
      name: p.name, ...(p.title ? { title: p.title } : {}), role: p.role, age: p.age, ...(p.pronouns ? { pronouns: p.pronouns } : {}),
      tagline: p.tagline, personality: { summary: "", traits: p.personality.traits }, backstory: "",
      speakingStyle: { summary: "", tone: "", formality: p.speakingStyle.formality, quirks: [], catchphrases: [] },
      expertise: [], boundaries: [], greeting: "",
    },
    profileMeta: undefined,
    appearance: { ...c.appearance, candidates: [] },
    emotions,
    blink: null,
    themeSongId: undefined,
    activeJobId: undefined,
    deletedAt,
    updatedAt: deletedAt,
  };
}

function deepMerge<T>(base: T, patch: DeepPartial<T> | undefined): T {
  if (!patch) return base;
  const out = { ...base } as Record<string, unknown>;
  for (const [k, v] of Object.entries(patch as Record<string, unknown>)) {
    if (v === undefined) continue;
    const cur = out[k];
    out[k] = v && typeof v === "object" && !Array.isArray(v) && cur && typeof cur === "object" && !Array.isArray(cur)
      ? deepMerge(cur, v as DeepPartial<typeof cur>)
      : v;
  }
  return out as T;
}

interface Sub { cb: (e: SessionEvent) => void; last: number }

export class MockClient implements HorizonClient {
  readonly kind = "mock" as const;
  readonly ready: Promise<void>;
  readonly dev: MockDevApi;

  private seed!: Dataset;
  private db!: Dataset;
  private storage: KV | null;
  private sched: Scheduler;
  private scenario: Scenario = SCENARIO_BY_ID.default;
  private faultLeft: { command?: number; stream?: number } = {};
  private lives = new Map<string, LiveSession>();
  private subs = new Map<string, Set<Sub>>();
  private globals = new Set<(e: GlobalEvent) => void>();
  private jobSubs = new Map<string, Set<(e: JobEvent) => void>>();
  private devSubs = new Set<(s: MockDevState) => void>();
  private runner!: JobRunner;
  private host: EngineHost;
  private persistTimer: ReturnType<typeof setTimeout> | null = null;
  private knowledgePending = new Map<string, Prepared>();
  private isReady = false;

  constructor(opts: MockClientOptions = {}) {
    this.storage = opts.storage === undefined ? defaultStorage() : opts.storage;
    const dev = this.readDev();
    this.sched = new Scheduler(opts.clock ?? realClock, opts.speed ?? dev?.speed ?? 1);
    const self = this;
    this.host = {
      get db() { return self.db; },
      get timing() { return self.timing; },
      get pricing() { return self.db.pricing; },
      period: () => this.period(),
      wallNow: () => this.sched.wallNow(),
      iso: () => this.iso(),
      newId: (p) => this.newId(p),
      rng: (s) => createRng(s),
      live: (sid) => this.liveOf(sid),
      emit: (sid, ...events) => {
        this.liveOf(sid);
        for (const e of events) this.deliver(sid, e);
      },
      play: (sid, entries, tag) => this.play(sid, entries, tag),
      after: (sid, ms, fn) => this.liveOf(sid).player.appendRelative([{ t: ms, run: fn, tag: "chain" }]),
      takeStreamFault: () => this.takeStreamFault(),
      dailyCapReached: () => this.dailyCapReached(),
      charge: (sid, category, costUsd) => this.chargeSession(sid, category, costUsd),
    };
    this.ready = this.init(opts, dev?.scenario);
    this.dev = this.makeDev();
  }

  // ── Boot ──────────────────────────────────────────────────────────────────
  private async init(opts: MockClientOptions, devScenario?: ScenarioId): Promise<void> {
    this.seed = opts.dataset ? cloneDataset(opts.dataset) : await loadSeedDataset();
    this.runner = new JobRunner(this.jobHost());
    const scenarioId = opts.scenario ?? devScenario ?? "default";
    const snap = loadSnapshot(this.storage, this.seed);
    if (snap) {
      this.db = snap;
      this.applyScenarioState(SCENARIO_BY_ID[scenarioId] ?? SCENARIO_BY_ID.default);
    } else {
      this.reseed(SCENARIO_BY_ID[scenarioId] ?? SCENARIO_BY_ID.default);
    }
    this.resumeJobs();
    knowledgeEngine.resumeIndexing(this.knowledgeHost());
    this.isReady = true;
    this.notifyDev();
  }

  private reseed(s: Scenario): void {
    this.db = cloneDataset(this.seed);
    // Fixture energy values hold at load time and regenerate from there (Rin stays Tired on first open).
    const now = this.sched.wallNow();
    for (const c of Object.values(this.db.characters)) {
      c.energy = { ...c.energy, asOf: iso(now), fullAt: fullAt(c.energy.current, c.energy.max, c.energy.regenPerHour, now) };
    }
    s.overlay?.(this.db);
    this.applyScenarioState(s);
    if (s.settingsPatch) this.db.settings = deepMerge(this.db.settings, s.settingsPatch);
  }

  private applyScenarioState(s: Scenario): void {
    this.scenario = s;
    this.faultLeft = { command: s.faults?.command?.times, stream: s.faults?.stream?.times };
  }

  private resumeJobs(): void {
    for (const j of Object.values(this.db.jobs)) if (j.status === "running" || j.status === "queued") this.runner.resume(j);
  }

  private get timing(): TimingConfig {
    return { ...DEFAULT_TIMING, ...this.scenario.timingPatch };
  }

  private period(): PricePeriod {
    return this.scenario.pricePeriod ?? pricePeriod(this.sched.wallNow());
  }

  /** D-78: the one Exhausted threshold for the current price period (= AppSettings.energy.estReplyPoints). */
  private est(): { estReplyPoints: number } { return { estReplyPoints: EST_REPLY_POINTS[this.period()] }; }

  private iso(): string { return iso(this.sched.wallNow()); }
  private newId(prefix: string): string { return makeId(prefix, this.sched.wallNow()); }

  // ── Guards ────────────────────────────────────────────────────────────────
  private async query<T>(fn: () => T): Promise<T> {
    await this.ready;
    const f = this.scenario.faults?.command;
    if (f?.queries) throw new HorizonError(f.code);
    return toWire(fn());
  }

  /** Non-AI command (rename, mute, archive…): only the network can fail it. */
  private async command<T>(fn: () => T): Promise<T> {
    await this.ready;
    const f = this.scenario.faults?.command;
    if (f?.queries) throw new HorizonError(f.code);
    const r = fn();
    this.persistSoon();
    return toWire(r);
  }

  /** AI action: needs a key (O05), honours command faults and the daily cap. */
  private async live<T>(fn: () => T, opts: { costs?: boolean } = { costs: true }): Promise<T> {
    await this.ready;
    const s = this.db.settings;
    if (s.openRouterKeyStatus === "missing") throw new HorizonError("missing_key");
    if (s.openRouterKeyStatus === "invalid") throw new HorizonError("invalid_key");
    const f = this.scenario.faults?.command;
    if (f && (this.faultLeft.command === undefined || this.faultLeft.command > 0)) {
      if (this.faultLeft.command !== undefined) this.faultLeft.command -= 1;
      throw new HorizonError(f.code, undefined, { retryAfterSec: f.retryAfterSec });
    }
    if (opts.costs && this.dailyCapReached()) throw new HorizonError("daily_budget_exceeded");
    const r = fn();
    this.persistSoon();
    return toWire(r);
  }

  private takeStreamFault() {
    const f = this.scenario.faults?.stream;
    if (!f) return null;
    if (this.faultLeft.stream !== undefined) {
      if (this.faultLeft.stream <= 0) return null;
      this.faultLeft.stream -= 1;
    }
    return f.kind === "cut" ? { kind: "cut" as const, afterTokens: f.afterTokens } : { kind: "refuse" as const };
  }

  private dailyCapReached(): boolean {
    const s = this.db.settings;
    return s.spentTodayUsd >= s.budget.dailyCapUsd - 1e-9;
  }

  // ── Global events & persistence ───────────────────────────────────────────
  private global(e: GlobalEvent): void {
    for (const cb of this.globals) {
      try { cb(e); } catch (err) { console.error("[mock] global listener", err); }
    }
  }

  private changed(kind: Extract<GlobalEvent, { type: "entity.changed" }>["kind"], id?: string, worldId?: string): void {
    this.global({ type: "entity.changed", kind, id, worldId });
    this.persistSoon();
  }

  private persistSoon(): void {
    if (!this.storage || this.persistTimer) return;
    this.persistTimer = setTimeout(() => {
      this.persistTimer = null;
      saveSnapshot(this.storage, this.db, this.seed);
    }, 500);
  }

  private ledger(row: Omit<UsageRecord, "id" | "at">): void {
    const rec: UsageRecord = { id: this.newId("use"), at: this.iso(), ...row };
    this.db.ledger.push(rec);
    this.spend(row.costUsd, row.sessionId);
  }

  /** Add to today's spend; warn at warnAtPct, pause at 100 % (STATE-06). */
  private spend(costUsd: number, sessionId?: string): void {
    const s = this.db.settings;
    const before = s.spentTodayUsd;
    s.spentTodayUsd = round6(before + costUsd);
    const cap = s.budget.dailyCapUsd;
    const warnAt = (cap * s.budget.warnAtPct) / 100;
    if (before < warnAt && s.spentTodayUsd >= warnAt && s.spentTodayUsd < cap) {
      this.global({ type: "budget.warning", scope: "daily", spentUsd: s.spentTodayUsd, capUsd: cap });
      if (sessionId) this.host.emit(sessionId, { type: "budget.warning", payload: { scope: "daily", spentUsd: s.spentTodayUsd, capUsd: cap } });
    }
    if (before < cap && s.spentTodayUsd >= cap) {
      this.global({ type: "budget.reached", scope: "daily", spentUsd: s.spentTodayUsd, capUsd: cap, sessionId });
      for (const live of this.lives.values()) {
        if (live.state.session.status !== "active") continue;
        clearLive(live, { keepCurrentTurn: true });
        live.held = true;
        this.host.emit(live.id, { type: "session.paused", payload: { reason: "daily_budget" } });
      }
    }
    this.changed("usage");
  }

  private chargeSession(sid: string, category: "decision" | "summary", costUsd: number): void {
    const model = category === "decision" ? this.db.pricing.decision : this.db.pricing.chat;
    this.ledger({ category, model: model.model, provider: model.provider, pricePeriod: this.period(), sessionId: sid, costUsd: round6(costUsd) });
  }

  // ── Live sessions (R1) ────────────────────────────────────────────────────
  private liveOf(sid: string): LiveSession {
    let live = this.lives.get(sid);
    if (live) return live;
    const rec = this.db.sessions[sid];
    if (!rec) throw notFound("Session");
    const state = { ...initialRuntime(rec.session, rec.messages), lastSeq: rec.events.at(-1)?.seq ?? 0 };
    const player = new ScriptPlayer<StreamEvent>([], { clock: this.sched.clock, onEntry: (e) => this.deliver(sid, e) });
    live = { id: sid, player, state, turn: rec.messages.length, queue: [], busy: false, held: false, recent: [] };
    this.lives.set(sid, live);
    player.play();
    return live;
  }

  private play(sid: string, entries: TimelineEntry<StreamEvent>[], tag?: string): void {
    this.liveOf(sid).player.appendRelative(entries.map((e) => ({ ...e, tag: e.tag ?? tag })));
  }

  /** One event: log it, reduce it, apply side effects, broadcast it. */
  private deliver(sid: string, evt: StreamEvent): void {
    const rec = this.db.sessions[sid];
    const live = this.lives.get(sid);
    if (!rec || !live) return;
    const se: SessionEvent = {
      id: this.newId("evt"), sessionId: sid, seq: (rec.events.at(-1)?.seq ?? 0) + 1, at: this.iso(), type: evt.type, payload: evt.payload,
    };
    rec.events.push(se);
    live.state = applyEvent(live.state, se);
    rec.session = live.state.session;
    if (evt.type !== "token") rec.messages = orderedMessages(live.state);

    for (const sub of this.subs.get(sid) ?? []) {
      if (se.seq <= sub.last) continue;
      sub.last = se.seq;
      try { sub.cb(se); } catch (err) { console.error("[mock] session listener", err); }
    }
    switch (evt.type) {
      case "energy": {
        const c = this.db.characters[evt.payload.characterId];
        if (c) {
          const now = this.sched.wallNow();
          const s = settle(c.energy, now, this.est());
          c.energy = {
            ...s, current: evt.payload.current, state: evt.payload.state,
            fullAt: fullAt(evt.payload.current, s.max, s.regenPerHour, now), spentToday: s.spentToday + (evt.payload.spent ?? 0),
          };
          this.changed("character", c.id, c.worldId);
        }
        break;
      }
      case "turn.end": {
        const u = evt.payload.usage;
        const m = live.state.messages[evt.payload.messageId];
        if (u && u.costUsd > 0) {
          this.ledger({
            category: "chat", model: this.db.pricing.chat.model, provider: this.db.pricing.chat.provider, pricePeriod: this.period(),
            sessionId: sid, characterId: m?.author.characterId, tokensIn: u.tokensIn, tokensCached: u.tokensCached, tokensOut: u.tokensOut,
            costUsd: u.costUsd, energyPoints: u.energySpent, latencyMs: u.totalMs,
          });
        }
        if (live.current?.messageId === evt.payload.messageId) live.current = undefined;
        this.changed("session", sid, rec.session.worldId);
        break;
      }
      case "message": case "session.state": case "session.paused": case "session.resumed": case "phase":
        this.changed("session", sid, rec.session.worldId);
        break;
    }
    if (evt.type !== "token") this.persistSoon();
  }

  private snapshot(sid: string): SessionSnapshot {
    const rec = this.db.sessions[sid];
    if (!rec) throw notFound("Session");
    return { session: rec.session, messages: rec.messages, lastSeq: rec.events.at(-1)?.seq ?? 0 };
  }

  /** One streaming session at a time (doc backend/03 §4): a session the user left (held) doesn't count. */
  private assertNoOtherStreaming(sid?: string): void {
    for (const live of this.lives.values()) {
      if (live.id !== sid && live.current && !live.held) {
        throw conflict("Another session is live. Leave it first.", { activeSessionId: live.id });
      }
    }
  }

  private liveSession(sid: string): LiveSession {
    const rec = this.db.sessions[sid];
    if (!rec) throw notFound("Session");
    if (rec.session.isSeed) throw conflict("Seed sessions are replay-only. Use Continue live.");
    if (rec.session.status === "ended") throw conflict("This session has ended.");
    this.assertNoOtherStreaming(sid);
    const live = this.liveOf(sid);
    if (live.state.session.status === "paused" && live.state.session.pausedReason !== "turn_cap") {
      if (live.state.session.pausedReason === "daily_budget" && this.dailyCapReached()) throw new HorizonError("daily_budget_exceeded");
      if (live.state.session.mode === "one_on_one" || live.state.session.mode === "group") {
        live.held = false;
        this.host.emit(sid, { type: "session.resumed", payload: { reason: "user" } });
      }
    }
    return live;
  }

  /** Mid-session settings change: a `session.state` settings event (D-57), plus entity.changed for lists. */
  private patchSession(sid: string, patch: SessionSettingsPatch): void {
    const live = this.liveOf(sid);
    if (Object.keys(patch).length) this.deliver(sid, { type: "session.state", payload: { settings: patch } });
    this.changed("session", sid, live.state.session.worldId);
  }

  // ── Settings ──────────────────────────────────────────────────────────────
  private settingsView(): AppSettings {
    const r = rushHourInfo(this.sched.wallNow(), this.scenario.pricePeriod);
    const s = this.db.settings;
    return {
      ...s,
      // Config-owned (rev 1.3): older snapshots may lack them; the client can never change them.
      models: { ...s.models, embedding: s.models.embedding ?? MODELS.embedding },
      energy: { ...s.energy, estReplyPoints: { ...EST_REPLY_POINTS } },
      pricing: { period: r.period, nextChangeAt: r.nextChangeAt },
    };
  }

  settings: HorizonClient["settings"] = {
    get: () => this.query(() => this.settingsView()),
    update: (patch) => this.command(() => {
      // estReplyPoints is read-only config (D-78): a patch can't move the energy threshold.
      const { estReplyPoints: _ignored, ...energy } = patch.energy ?? {};
      this.db.settings = deepMerge(this.db.settings, { ...patch, ...(patch.energy ? { energy } : {}) });
      this.changed("settings");
      return this.settingsView();
    }),
    setKey: (key) => this.command(() => {
      const k = key?.trim() ?? "";
      const status: AppSettings["openRouterKeyStatus"] = !k ? "missing" : k.startsWith("sk-or-bad") || !k.startsWith("sk-or-") ? "invalid" : "set";
      this.db.settings = { ...this.db.settings, openRouterKeyStatus: status, demoMode: status !== "set" };
      this.changed("settings");
      return this.settingsView();
    }),
    testConnection: () => this.live(() => ({ ok: true as const, latencyMs: 412, creditsUsd: 4.21 }), { costs: false }),
    testModel: (role) => this.live(() => ({ ok: true as const, latencyMs: 380 + role.length * 20, model: this.db.settings.modelOverrides?.[role] ?? this.db.settings.models[role] }), { costs: false }),
  };

  // ── Worlds ────────────────────────────────────────────────────────────────
  private worldView(w: World): World {
    const count = Object.values(this.db.characters).filter((c) => c.worldId === w.id && c.status === "approved" && !c.deletedAt).length;
    return { ...w, characterCount: count };
  }

  private world(id: string): World {
    const w = this.db.worlds[id];
    if (!w) throw notFound("World");
    return w;
  }

  /** World names (worlds spec): trimmed, ≤ 40 chars, unique case-insensitively; shipped seed names are reserved
   * for their own world, so "Reset demo data" can always restore them (demo-data spec, like the backend). */
  private worldName(name: string, selfId?: string): string {
    const clean = name.trim().slice(0, 40) || "New World";
    const key = clean.toLowerCase();
    for (const s of Object.values(this.seed.worlds)) {
      if (s.name.trim().toLowerCase() === key && s.id !== selfId) throw conflict("That name belongs to a demo world.", { field: "name", reserved: true });
    }
    for (const w of Object.values(this.db.worlds)) {
      if (w.id !== selfId && w.name.trim().toLowerCase() === key) throw conflict("A world with that name already exists.", { field: "name" });
    }
    return clean;
  }

  worlds: HorizonClient["worlds"] = {
    list: () => this.query(() => Object.values(this.db.worlds).map((w) => this.worldView(w)).sort((a, b) => b.lastActiveAt.localeCompare(a.lastActiveAt))),
    get: (id) => this.query(() => this.worldView(this.world(id))),
    uploadCover: async (id, file) => {
      await this.query(() => this.world(id));
      const url = await coverUrl(file);
      return this.command(() => {
        const w = this.world(id);
        w.cover = { kind: "upload", url };
        w.updatedAt = this.iso();
        this.changed("world", w.id, w.id);
        return this.worldView(w);
      });
    },
    create: (input: WorldInput) => this.command(() => {
      const now = this.iso();
      const w: World = {
        id: this.newId("wld"), name: this.worldName(input.name), cover: input.cover,
        ...(input.you ? { you: input.you } : {}), characterCount: 0, isSeed: false, createdAt: now, updatedAt: now, lastActiveAt: now,
      };
      this.db.worlds[w.id] = w;
      this.changed("world", w.id, w.id);
      return w;
    }),
    update: (id, patch) => this.command(() => {
      const w = this.world(id);
      const name = patch.name !== undefined ? this.worldName(patch.name, id) : w.name;
      Object.assign(w, patch, { name, updatedAt: this.iso() });
      this.changed("world", id, id);
      return this.worldView(w);
    }),
    delete: (id) => this.command(() => {
      this.world(id);
      delete this.db.worlds[id];
      for (const c of Object.values(this.db.characters)) if (c.worldId === id) delete this.db.characters[c.id];
      for (const [sid, r] of Object.entries(this.db.sessions)) if (r.session.worldId === id) this.dropSession(sid);
      for (const m of Object.values(this.db.memory)) if (m.worldId === id) delete this.db.memory[m.id];
      for (const k of Object.values(this.db.knowledge)) if (k.worldId === id) knowledgeEngine.removeSource(this.knowledgeHost(), k.id);
      this.dropOrphanChunks();
      this.changed("world", id, id);
    }),
  };

  // ── Characters ────────────────────────────────────────────────────────────
  private char(id: string): Character {
    const c = this.db.characters[id];
    if (!c || c.deletedAt) throw notFound("Character");
    return c;
  }

  /** Read view: `energy.state` is derived at read time for the current price period (D-78), like the backend. */
  private charView(c: Character): Character {
    const e = c.energy;
    const current = this.db.settings.demoMode ? e.current : regenAt(e, this.sched.wallNow());
    return { ...c, energy: { ...e, state: energyState(current, e.max, this.est().estReplyPoints) } };
  }

  private touchChar(c: Character, bump = false): Character {
    c.updatedAt = this.iso();
    if (bump && c.status === "approved") c.version += 1;
    this.changed("character", c.id, c.worldId);
    return c;
  }

  characters: HorizonClient["characters"] = {
    list: (worldId, opts) => this.query(() => Object.values(this.db.characters)
      .filter((c) => c.worldId === worldId && !c.deletedAt && (opts?.includeArchived || c.status !== "archived"))
      .sort((a, b) => Number(b.isSeed) - Number(a.isSeed) || a.createdAt.localeCompare(b.createdAt))
      .map((c) => this.charView(c))),
    // Tombstones (deletedAt) stay readable so old transcripts render; every command on them is not_found.
    get: (id) => this.query(() => {
      const c = this.db.characters[id];
      if (!c) throw notFound("Character");
      return this.charView(c);
    }),
    createDraft: (worldId, input) => this.live(() => {
      this.world(worldId);
      const now = this.iso();
      const max = this.db.settings.energy.defaultMaxPoints;
      const name = input.seedPrompt.match(/^\s*([A-Z][a-z]+)/)?.[1] ?? "";
      const c: Character = {
        id: this.newId("chr"), worldId, status: "draft", creationStep: "seed", seedPrompt: input.seedPrompt.slice(0, 300), intent: input.intent,
        advisory: input.intent === "expert",
        profile: {
          name, role: "", age: 30, tagline: "", personality: { summary: "", traits: [] }, backstory: "",
          speakingStyle: { summary: "", tone: "", formality: "neutral", quirks: [], catchphrases: [] },
          expertise: [], boundaries: [], greeting: "",
        },
        appearance: {
          attributes: {
            body: { ageBand: "adult", build: "average", height: "average", skinTone: "beige" },
            face: { shape: "oval", baseline: "neutral", marks: [] },
            eyes: { shape: "almond", color: "brown", glasses: "none" },
            hair: { length: "short", style: "straight", color: "black", fringe: "none" },
            outfit: { archetype: "casual", primaryColor: "#2F5D8A", secondaryColor: "#F5F2EA" },
            accessories: [], vibe: [],
          },
          appearanceSummary: "", candidates: [],
          stylePresetId: this.db.stylePresets[0]?.id ?? "style_horizon_anime", stylePresetVersion: this.db.stylePresets[0]?.version ?? 1,
        },
        paletteId: this.db.palettes[0]?.id ?? "pal_ocean_clinic",
        emotionSet: [...EMOTIONS],
        emotions: Object.fromEntries(EMOTIONS.map((e) => [e, null])) as Character["emotions"],
        energy: makeEnergy(max, max, now, 0, this.est()),
        version: 1, isSeed: false, createdAt: now, updatedAt: now,
      };
      this.db.characters[c.id] = c;
      const job = this.runner.start({ characterId: c.id, kind: "profile_draft" });
      this.changed("character", c.id, worldId);
      return { character: c, job };
    }),
    update: (id, patch: CharacterPatch) => this.command(() => {
      const c = this.char(id);
      const { profile, appearance, ...rest } = patch;
      Object.assign(c, rest);
      if (profile) c.profile = { ...c.profile, ...profile } as Character["profile"];
      if (appearance) c.appearance = deepMerge(c.appearance, appearance as DeepPartial<Character["appearance"]>);
      return this.touchChar(c, true);
    }),
    lockPortrait: (id, candidateId) => this.command(() => {
      const c = this.char(id);
      const cand = c.appearance.candidates.find((x) => x.id === candidateId);
      if (!cand) throw notFound("Candidate");
      if (cand.status !== "ready") throw conflict("That candidate isn't ready.");
      c.appearance.candidates = c.appearance.candidates.map((x) => ({ ...x, selected: x.id === candidateId }));
      c.appearance.basePortraitUrl = cand.url;
      const asset = { id: this.newId("emo"), characterId: c.id, emotion: "neutral" as Emotion, variant: "default" as const, status: "ready" as const, url: cand.url, vfxPreset: "none" as const, version: 1, isActive: true };
      for (const a of Object.values(this.db.assets)) if (a.characterId === c.id && a.emotion === "neutral" && a.variant === "default") a.isActive = false;
      this.db.assets[asset.id] = asset;
      c.emotions.neutral = { assetId: asset.id, url: cand.url, vfxPreset: "none" };
      if (c.status === "draft" && CREATION_STEPS.indexOf(c.creationStep ?? "seed") < CREATION_STEPS.indexOf("emotions")) c.creationStep = "emotions";
      return this.touchChar(c);
    }),
    approve: (id) => this.command(() => {
      const c = this.char(id);
      const p = c.profile;
      if (!p.name || !p.role || p.age < 18 || !c.appearance.basePortraitUrl) {
        throw invalid("Approval needs a valid profile (adult age) and a locked base portrait.");
      }
      c.status = "approved";
      c.approvedAt = this.iso();
      c.creationStep = undefined;
      return this.touchChar(c);
    }),
    archive: (id) => this.command(() => {
      const c = this.char(id);
      c.status = "archived";
      c.archivedAt = this.iso();
      return this.touchChar(c);
    }),
    restore: (id) => this.command(() => {
      const c = this.char(id);
      c.status = c.approvedAt || c.isSeed ? "approved" : "draft";
      c.archivedAt = undefined;
      return this.touchChar(c);
    }),
    // D-70 / rev 1.3: delete leaves a tombstone (name, palette, neutral portrait) so transcripts keep rendering.
    delete: (id) => this.command(() => {
      const c = this.char(id);
      for (const live of this.lives.values()) {
        if (live.current && !live.held && live.state.session.participants.some((p) => p.characterId === id)) {
          throw conflict(`${c.profile.name} is in the live session. Stop or leave it first.`, { activeSessionId: live.id });
        }
      }
      for (const j of Object.values(this.db.jobs)) {
        if (j.characterId !== id) continue;
        if (j.status === "queued" || j.status === "running") this.runner.cancel(j.id);
        delete this.db.jobs[j.id];
      }
      for (const m of Object.values(this.db.memory)) if (m.characterId === id) delete this.db.memory[m.id];
      for (const k of Object.values(this.db.knowledge)) if (k.characterId === id) knowledgeEngine.removeSource(this.knowledgeHost(), k.id);
      for (const s of Object.values(this.db.songs)) if (s.characterId === id) delete this.db.songs[s.id];
      const neutral = c.emotions.neutral;
      for (const a of Object.values(this.db.assets)) if (a.characterId === id && a.id !== neutral?.assetId) delete this.db.assets[a.id];
      this.dropOrphanChunks();
      this.db.characters[id] = tombstone(c, this.iso());
      this.changed("character", id, c.worldId);
    }),
    assets: (id) => this.query(() => Object.values(this.db.assets).filter((a) => a.characterId === id).sort((a, b) => a.emotion.localeCompare(b.emotion) || a.version - b.version)),
    acceptAssetVersion: (assetId) => this.command(() => {
      const a = this.db.assets[assetId];
      if (!a) throw notFound("Asset");
      const c = this.char(a.characterId);
      for (const x of Object.values(this.db.assets)) if (x.characterId === c.id && x.emotion === a.emotion && x.variant === a.variant) x.isActive = x.id === assetId;
      const ref = { assetId: a.id, url: a.url ?? "", vfxPreset: a.vfxPreset };
      if (a.variant === "blink") c.blink = ref;
      else c.emotions[a.emotion] = ref;
      return this.touchChar(c, true);
    }),
    song: (id) => this.query(() => {
      const c = this.char(id);
      return c.themeSongId ? this.db.songs[c.themeSongId] ?? null : null;
    }),
    topUpEnergy: (id, points) => this.live(() => {
      const c = this.char(id);
      const s = this.db.settings;
      const nowMs = this.sched.wallNow();
      const today = energyDay(nowMs);
      const todayTopUpPoints = this.db.ledger
        .filter((r) => r.category === "energy_topup" && energyDay(Date.parse(r.at)) === today)
        .reduce((n, r) => n + (r.energyPoints ?? 0), 0);
      // D-76: top-ups are bounded by today's budget headroom, but cost $0 (the replies they fund are the spend).
      const gate = { spentTodayUsd: s.spentTodayUsd, todayTopUpPoints, points, usdPerPoint: s.energy.usdPerPoint, dailyCapUsd: s.budget.dailyCapUsd };
      if (!canTopUp(gate)) throw new HorizonError("daily_budget_exceeded", undefined, { details: { todayTopUpPoints, points } });
      c.energy = topUp(c.energy, points, nowMs, this.est());
      this.ledger({ category: "energy_topup", characterId: id, costUsd: 0, energyPoints: points });
      this.broadcastEnergy(c);
      this.touchChar(c);
      return c.energy;
    }),
    setEnergyMax: (id, points) => this.command(() => {
      const c = this.char(id);
      c.energy = withMax(c.energy, points, this.sched.wallNow(), this.est());
      this.broadcastEnergy(c);
      this.touchChar(c);
      return c.energy;
    }),
    memory: (id) => this.query(() => Object.values(this.db.memory).filter((m) => m.characterId === id).sort((a, b) => b.createdAt.localeCompare(a.createdAt))),
    forgetMemory: (memoryItemId) => this.command(() => {
      const m = this.db.memory[memoryItemId];
      delete this.db.memory[memoryItemId];
      if (m) this.changed("memory", m.characterId, m.worldId);
    }),
    knowledge: (id) => this.query(() => Object.values(this.db.knowledge).filter((k) => k.characterId === id)),
    // D-59: a source and its indexed passages, in order (seed/knowledge/chunks).
    knowledgeSource: (sourceId) => this.query(() => {
      const source = this.db.knowledge[sourceId];
      if (!source) throw notFound("Source");
      const chunks = Object.values(this.db.knowledgeChunks).filter((c) => c.sourceId === sourceId).sort((a, b) => a.index - b.index);
      return { source, chunks };
    }),
    // rev 1.3 (D-65): ingestion is local and free (Docling); only the embedding step needs a key and budget.
    addKnowledge: async (id, input) => {
      const c = await this.query(() => this.char(id));
      const accepted = await knowledgeEngine.acceptInput(this.knowledgeHost(), c.id, input);
      return this.command(() => {
        const src = knowledgeEngine.startSource(this.knowledgeHost(), c.id, c.worldId, accepted);
        this.changed("knowledge", src.id, src.worldId);
        return src;
      });
    },
    deleteKnowledge: (sourceId) => this.command(() => {
      const s = this.db.knowledge[sourceId];
      if (!s) throw notFound("Source");
      knowledgeEngine.removeSource(this.knowledgeHost(), sourceId);
      this.changed("knowledge", sourceId, s.worldId);
    }),
    reindexKnowledge: (sourceId) => this.command(() => {
      const s = this.db.knowledge[sourceId];
      if (!s) throw notFound("Source");
      const out = knowledgeEngine.reindex(this.knowledgeHost(), s);
      this.changed("knowledge", sourceId, s.worldId);
      return out;
    }),
  };

  private knowledgeHost(): KnowledgeHost {
    const self = this;
    return {
      get db() { return self.db; },
      get sched() { return self.sched; },
      get pricing() { return self.db.pricing; },
      pending: this.knowledgePending,
      newId: (p) => this.newId(p),
      iso: () => this.iso(),
      canEmbed: () => this.db.settings.openRouterKeyStatus === "set" && !this.dailyCapReached(),
      ledger: (row) => this.ledger(row),
      progress: (s, progress) => {
        this.global({ type: "entity.changed", kind: "knowledge", id: s.id, worldId: s.worldId, ...(progress ? { progress } : {}) });
        this.persistSoon();
      },
    };
  }

  /** D-59: passages whose source is gone (world/character deleted) go with it. */
  private dropOrphanChunks(): void {
    for (const c of Object.values(this.db.knowledgeChunks)) if (!this.db.knowledge[c.sourceId]) delete this.db.knowledgeChunks[c.id];
  }

  /** Energy changed outside a turn (top-up, max): live sessions with that character get an `energy` event. */
  private broadcastEnergy(c: Character): void {
    const e: Energy = c.energy;
    for (const live of this.lives.values()) {
      if (!live.state.session.participants.some((p) => p.characterId === c.id)) continue;
      this.host.emit(live.id, { type: "energy", payload: { characterId: c.id, current: Math.floor(e.current), max: e.max, state: energyState(e.current, e.max, this.est().estReplyPoints), ...(e.fullAt ? { fullAt: e.fullAt } : {}) } });
    }
  }

  // ── Jobs ──────────────────────────────────────────────────────────────────
  private jobHost(): JobHost {
    const self = this;
    return {
      get db() { return self.db; },
      get timing() { return self.timing; },
      get pricing() { return self.db.pricing; },
      get sched() { return self.sched; },
      newId: (p) => this.newId(p),
      iso: () => this.iso(),
      jobFault: () => this.scenario.faults?.job as Faults["job"],
      emitJob: (e, characterName) => {
        for (const cb of this.jobSubs.get(e.type === "task.update" ? e.jobId : e.job.id) ?? []) cb(clone(e));
        // rev 1.3: the global stream mirrors every job event (the backend has no per-job stream).
        if (e.type === "job.done") this.global({ type: "job.done", job: clone(e.job), characterName });
        else if (e.type === "job.progress") this.global({ type: "job.progress", job: clone(e.job) });
        else this.global({ type: "task.update", jobId: e.jobId, task: clone(e.task) });
      },
      ledger: (row) => this.ledger(row),
      changed: (kind, id) => this.changed(kind, id, kind === "character" ? this.db.characters[id]?.worldId : undefined),
    };
  }

  jobs: HorizonClient["jobs"] = {
    estimate: (input: StartJobInput) => this.query(() => {
      this.char(input.characterId);
      return { estimatedCostUsd: estimateJob(this.jobHost(), input) };
    }),
    start: (input) => this.live(() => {
      this.char(input.characterId);
      return this.runner.start(input);
    }),
    get: (jobId) => this.query(() => {
      const j = this.db.jobs[jobId];
      if (!j) throw notFound("Job");
      return j;
    }),
    cancel: (jobId) => this.command(() => this.runner.cancel(jobId)),
    retryTask: (jobId, taskId) => this.live(() => this.runner.retryTask(jobId, taskId)),
    listActive: () => this.query(() => Object.values(this.db.jobs).filter((j) => j.status === "queued" || j.status === "running")),
    subscribe: (jobId, cb) => {
      if (!this.jobSubs.has(jobId)) this.jobSubs.set(jobId, new Set());
      this.jobSubs.get(jobId)!.add(cb);
      void this.ready.then(() => {
        const j = this.db.jobs[jobId];
        if (j) cb({ type: j.status === "queued" || j.status === "running" ? "job.progress" : "job.done", job: clone(j) });
      });
      return () => { this.jobSubs.get(jobId)?.delete(cb); };
    },
  };


  // ── Sessions ──────────────────────────────────────────────────────────────
  private dropSession(sid: string): void {
    const live = this.lives.get(sid);
    if (live) {
      clearLive(live);
      live.player.dispose();
      this.lives.delete(sid);
    }
    delete this.db.sessions[sid];
  }

  private defaultTitle(input: CreateSessionInput, cast: Character[]): string {
    const first = (c: Character) => c.profile.name.split(" ").find((w) => !/^(dr|prof)\.?$/i.test(w)) ?? c.profile.name;
    switch (input.mode) {
      case "one_on_one": return `Chat with ${first(cast[0])}`;
      case "group": return cast.map(first).join(", ");
      case "debate": return `Debate: ${(input.config as DebateConfig | undefined)?.motion?.replace(/^this house (would|believes)\s*/i, "").slice(0, 48) ?? "Untitled"}`;
      case "watch": return (input.config as WatchConfig | undefined)?.premise?.split(/[.!?]/)[0].slice(0, 40) ?? "Scene";
    }
  }

  private createSession(input: CreateSessionInput): SessionSnapshot {
    const w = this.world(input.worldId);
    const cast = input.characterIds.map((id) => this.char(id));
    // NFR-23: a character from another world is reported as missing, never as existing elsewhere.
    if (cast.some((c) => c.worldId !== w.id)) throw notFound("Character");
    if (cast.some((c) => c.status !== "approved")) throw invalid("Drafts and archived characters can't join sessions.");
    const min = input.mode === "one_on_one" ? 1 : 2;
    const max = input.mode === "one_on_one" ? 1 : 5;
    if (cast.length < min || cast.length > max) {
      throw invalid(`This mode needs ${min}–${max} characters.`, { field: "characterIds", min, max, got: cast.length });
    }
    this.assertNoOtherStreaming();
    const s = this.db.settings;
    const now = this.iso();
    let config: Session["config"] = null;
    let state: Session["state"] = null;
    let musicPolicy: MusicPolicy = input.musicPolicy ?? "character_theme";
    if (input.mode === "group") {
      config = { responderPolicy: s.chat.responderDefault, maxAutoResponders: 2, ...(input.config as Partial<GroupConfig> | undefined) } as GroupConfig;
      musicPolicy = input.musicPolicy ?? "follow_speaker";
    } else if (input.mode === "debate") {
      const c = (input.config ?? {}) as Partial<DebateConfig>;
      const roundsPreset = c.roundsPreset ?? "standard";
      const sides = c.sides ?? (input.sides ? {
        prop: cast.filter((x) => input.sides![x.id] === "prop").map((x) => x.id),
        opp: cast.filter((x) => input.sides![x.id] === "opp").map((x) => x.id),
      } : undefined);
      config = {
        motion: c.motion ?? "This house would adopt a four-day work week", format: c.format ?? "two_sided", ...(sides ? { sides } : {}),
        roundsPreset, phases: c.phases ?? (roundsPreset === "quick" ? ["opening", "closing"] : ["opening", "rebuttal", "closing"]),
        turnLength: c.turnLength ?? (cast.length >= 5 ? "short" : "medium"), moderator: c.moderator ?? "user",
        verdictBy: c.format === "panel" && c.verdictBy === "user" ? "arbiter" : c.verdictBy ?? "arbiter",
        rubric: c.rubric?.length ? c.rubric : DEFAULT_RUBRIC, autoAdvance: c.autoAdvance ?? s.chat.debateAutoAdvance, pauseMs: c.pauseMs ?? 1500,
      };
      state = { phase: "setup", round: 0, iteration: 1 };
      musicPolicy = input.musicPolicy ?? "arena";
    } else if (input.mode === "watch") {
      const c = (input.config ?? {}) as Partial<WatchConfig>;
      config = { premise: c.premise ?? "An ordinary afternoon.", maxTurns: c.maxTurns ?? 20, paceMs: c.paceMs ?? 1500, openingSpeaker: c.openingSpeaker ?? "auto" };
      state = { status: "paused", turnsTaken: 0, turnLimit: config.maxTurns };
      musicPolicy = input.musicPolicy ?? "follow_speaker";
    }
    const dc = config as DebateConfig | null;
    const participants: Participant[] = cast.map((c) => ({
      characterId: c.id, role: input.mode === "debate" ? "debater" : "speaker",
      side: input.mode === "debate" && dc?.format === "two_sided" ? (dc.sides?.prop.includes(c.id) ? "prop" : dc.sides?.opp.includes(c.id) ? "opp" : null) : null,
      currentEmotion: "neutral", mutedByUser: false,
    }));
    const session: Session = {
      id: this.newId("ses"), worldId: w.id, title: input.title?.trim() || this.defaultTitle(input, cast), titleIsCustom: Boolean(input.title?.trim()),
      mode: input.mode, status: "active", participants, emotionMode: input.emotionMode ?? s.chat.defaultEmotionMode, musicPolicy,
      readableMode: s.chat.readableDefault, config, state, ...(input.continuedFrom ? { continuedFrom: input.continuedFrom } : {}),
      isSeed: false, costUsd: 0, messageCount: 0, createdAt: now, updatedAt: now,
    };
    this.db.sessions[session.id] = { session, messages: [], events: [] };
    w.lastActiveAt = now;
    const sid = session.id;
    const open: StreamEvent[] = [{ type: "session.state", payload: { status: "active", ...(state ? { state } : {}), participants } }];
    for (const c of cast) {
      const e = settle(c.energy, this.sched.wallNow(), this.est());
      open.push({ type: "energy", payload: { characterId: c.id, current: Math.floor(e.current), max: e.max, state: e.state } });
    }
    if (input.seedSummary) open.push({ type: "message", payload: { message: systemNote(this.host, sid, input.seedSummary, "summary") } });
    // Deliver the opening snapshot synchronously so the returned snapshot already reflects it.
    this.liveOf(sid);
    for (const e of open) this.deliver(sid, e);
    if (input.mode === "one_on_one") oneEngine.greet(this.host, sid);
    else if (input.mode === "debate") debateEngine.start(this.host, sid);
    else if (input.mode === "watch") watchEngine.start(this.host, sid);
    this.changed("session", sid, w.id);
    return this.snapshot(sid);
  }

  private fork(id: string, atSeq?: number): SessionSnapshot {
    const rec = this.db.sessions[id];
    if (!rec) throw notFound("Session");
    const sid = this.newId("ses");
    const { events: reEvents, state: final } = forkEvents(rec.events, rec.session, atSeq, sid, this.iso());
    const base = final.session;
    const multi = base.mode === "debate" || base.mode === "watch";
    const ended = final.session.status === "ended";
    this.db.sessions[sid] = { session: final.session, messages: orderedMessages(final), events: reEvents };
    const live = this.liveOf(sid);
    live.held = multi;
    if (!ended) {
      this.deliver(sid, multi
        ? { type: "session.state", payload: { status: "paused", pausedReason: "user", ...(base.mode === "watch" && final.session.state ? { state: { ...(final.session.state as WatchState), status: "paused" as const } } : {}) } }
        : { type: "session.state", payload: { status: "active" } });
    }
    this.changed("session", sid, base.worldId);
    return this.snapshot(sid);
  }

  sessions: HorizonClient["sessions"] = {
    list: (worldId) => this.query(() => Object.values(this.db.sessions).map((r) => r.session).filter((s) => s.worldId === worldId)
      .sort((a, b) => (b.lastMessageAt ?? b.updatedAt).localeCompare(a.lastMessageAt ?? a.updatedAt))),
    get: (id) => this.query(() => this.snapshot(id)),
    create: (input) => this.live(() => this.createSession(input)),
    rename: (id, title) => this.command(() => {
      const t = title.trim().slice(0, 80);
      if (this.lives.has(id)) this.patchSession(id, { title: t, titleIsCustom: true });
      else {
        const r = this.db.sessions[id];
        if (!r) throw notFound("Session");
        r.session = { ...r.session, title: t, titleIsCustom: true };
        this.changed("session", id, r.session.worldId);
      }
      return this.db.sessions[id].session;
    }),
    delete: (id) => this.command(() => {
      const w = this.db.sessions[id]?.session.worldId;
      this.dropSession(id);
      this.changed("session", id, w);
    }),
    forkSeedSession: (id, atSeq) => this.live(() => this.fork(id, atSeq)),
    messages: (id) => this.query(() => this.snapshot(id).messages),
    trace: (messageId) => this.query(() => {
      for (const r of Object.values(this.db.sessions)) {
        const m = r.messages.find((x) => x.id === messageId);
        if (m) return m.trace ?? null;
      }
      return null;
    }),
    events: (id) => this.query(() => this.db.sessions[id]?.events ?? []),
    export: (id) => this.query(() => this.exportMarkdown(id)),
    subscribe: (id, opts, cb) => {
      const sub: Sub = { cb, last: opts.sinceSeq };
      if (!this.subs.has(id)) this.subs.set(id, new Set());
      this.subs.get(id)!.add(sub);
      void this.ready.then(() => {
        for (const e of this.db.sessions[id]?.events ?? []) {
          if (e.seq <= sub.last) continue;
          sub.last = e.seq;
          cb(e);
        }
      });
      return () => { this.subs.get(id)?.delete(sub); };
    },
    leave: (id) => this.command(() => {
      const r = this.db.sessions[id];
      if (!r || r.session.isSeed || r.session.status !== "active") return;
      const live = this.lives.get(id);
      if (live) {
        clearLive(live, { keepCurrentTurn: true });
        live.held = true;
      }
      this.host.emit(id, { type: "session.paused", payload: { reason: "navigated_away" } });
    }),
    end: (id) => this.command(() => {
      const live = this.liveOf(id);
      clearLive(live, { keepCurrentTurn: true });
      this.host.emit(id, { type: "session.state", payload: { status: "ended" } });
    }),
  };

  private exportMarkdown(id: string): string {
    const { session: s, messages } = this.snapshot(id);
    const name = (cid?: string) => (cid ? this.db.characters[cid]?.profile.name ?? cid : "");
    const lines = [`# ${s.title}`, "", `- Mode: ${s.mode}`, `- Cast: ${s.participants.map((p) => `${name(p.characterId)}${p.side ? ` (${p.side})` : ""}`).join(", ")}`];
    if (s.mode === "debate") lines.push(`- Motion: ${(s.config as DebateConfig).motion}`);
    if (s.mode === "watch") lines.push(`- Premise: ${(s.config as WatchConfig).premise}`);
    lines.push("");
    const notes: string[] = [];
    for (const m of messages) {
      const who = m.author.type === "user" ? (m.kind === "chat" ? "You" : "MODERATOR") : m.author.type === "character" ? name(m.author.characterId) : m.author.type === "host" ? "HOST" : "—";
      lines.push(`**${who}**${m.emotion ? ` [${m.emotion}]` : ""}: ${footnoteCitations(m.content, m.citations, notes)}`, "");
    }
    const v = s.state && "verdict" in s.state ? s.state.verdict : undefined;
    if (v) lines.push("## Verdict", "", `Stronger case: ${v.strongerCase ?? "too close to call"}`, ...(v.rationale ? ["", v.rationale] : []));
    // D-59: cited knowledge as Markdown footnotes (source title, locator, quote).
    if (notes.length) lines.push("", "## Sources", "", ...notes);
    return lines.join("\n");
  }

  // ── Commands (doc 05 §6) ──────────────────────────────────────────────────
  chat: HorizonClient["chat"] = {
    send: (sid, text, opts) => this.live(() => {
      const live = this.liveSession(sid);
      const mode = live.state.session.mode;
      if (mode === "one_on_one") oneEngine.send(this.host, sid, text);
      else if (mode === "group") groupEngine.send(this.host, sid, text, opts?.mentions ?? []);
      else if (mode === "watch") watchEngine.stepIn(this.host, sid, text);
      else debateEngine.interject(this.host, sid, text);
    }),
    stop: (sid) => this.command(() => this.stop(sid)),
    regenerate: (sid, messageId) => this.live(() => {
      this.liveSession(sid);
      oneEngine.regenerate(this.host, sid, messageId);
    }),
    setEmotion: (sid, cid, emotion) => this.command(() => {
      this.liveOf(sid);
      this.host.emit(sid, { type: "emotion", payload: { characterId: cid, emotion, source: "user" } });
    }),
    setEmotionMode: (sid, mode) => this.command(() => this.patchSession(sid, { emotionMode: mode })),
    setResponderPolicy: (sid, policy) => this.command(() => {
      const s = this.liveOf(sid).state.session;
      this.patchSession(sid, { config: { ...(s.config as GroupConfig), responderPolicy: policy } });
    }),
    setMusicPolicy: (sid, policy) => this.command(() => this.patchSession(sid, { musicPolicy: policy })),
    setReadableMode: (sid, on) => this.command(() => this.patchSession(sid, { readableMode: on })),
    everyoneAnswer: (sid) => this.live(() => {
      this.liveSession(sid);
      groupEngine.everyoneAnswer(this.host, sid);
    }),
    nextSpeaker: (sid, cid) => this.live(() => {
      const live = this.liveSession(sid);
      if (live.state.session.mode === "watch") {
        live.nudge = cid;
        if (live.held) watchEngine.stepOnce(this.host, sid);
      } else groupEngine.nextSpeaker(this.host, sid, cid);
    }),
    muteParticipant: (sid, cid, muted) => this.command(() => {
      const live = this.liveOf(sid);
      const participants = live.state.session.participants.map((p) => (p.characterId === cid ? { ...p, mutedByUser: muted } : p));
      this.host.emit(sid, { type: "session.state", payload: { participants } });
    }),
  };

  private stop(sid: string): void {
    const live = this.lives.get(sid);
    if (!live) return;
    const cur = live.current;
    clearLive(live);
    if (!cur) return;
    const msg = live.state.messages[cur.messageId];
    const full = cur.script.usage;
    const shown = msg?.content.length ?? 0;
    const frac = msg ? Math.min(1, shown / Math.max(1, cur.text.length)) : 0;
    const tokensOut = Math.round(full.tokensOut * frac);
    const costUsd = msg ? chatCostUsd({ tokensIn: full.tokensIn, tokensCached: full.tokensCached, tokensOut }, this.db.pricing.chat, this.period()) : 0;
    const usage = { ...full, tokensOut, costUsd, energySpent: pointsForCost(costUsd), totalMs: Math.round(live.player.position - cur.startPos) };
    const events: StreamEvent[] = [{ type: "turn.end", payload: { messageId: cur.messageId, status: "interrupted", interruptedBy: "user", ...(msg ? { usage } : {}) } }];
    if (msg && usage.energySpent > 0) {
      const c = this.db.characters[cur.characterId];
      if (c) {
        const now = settle(c.energy, this.sched.wallNow(), this.est());
        const current = Math.max(0, Math.floor(now.current) - usage.energySpent);
        events.push({ type: "energy", payload: { characterId: c.id, current, max: now.max, state: energyState(current, now.max, this.est().estReplyPoints), spent: usage.energySpent } });
      }
    }
    this.host.emit(sid, ...events);
    live.current = undefined;
  }

  debate: HorizonClient["debate"] = {
    pause: (sid) => this.command(() => debateEngine.pause(this.host, sid)),
    resume: (sid) => this.live(() => {
      this.liveSession(sid);
      debateEngine.resume(this.host, sid);
    }),
    next: (sid) => this.live(() => {
      this.liveSession(sid);
      debateEngine.step(this.host, sid);
    }),
    setAutoAdvance: (sid, on) => this.command(() => {
      const s = this.liveOf(sid).state.session;
      this.patchSession(sid, { config: { ...(s.config as DebateConfig), autoAdvance: on } });
      if (on && !this.liveOf(sid).held && !this.liveOf(sid).busy) debateEngine.step(this.host, sid);
    }),
    askCharacter: (sid, cid, text) => this.live(() => {
      this.liveSession(sid);
      debateEngine.askCharacter(this.host, sid, cid, text);
    }),
    interject: (sid, text) => this.command(() => debateEngine.interject(this.host, sid, text)),
    extendRound: (sid) => this.live(() => debateEngine.extendRound(this.host, sid)),
    skipToClosing: (sid) => this.command(() => debateEngine.skipToClosing(this.host, sid)),
    endDebate: (sid, withVerdict) => (withVerdict ? this.live(() => debateEngine.endDebate(this.host, sid, true)) : this.command(() => debateEngine.endDebate(this.host, sid, false))),
    pickStrongerCase: (sid, side) => this.command(() => debateEngine.pickStrongerCase(this.host, sid, side)),
  };

  watch: HorizonClient["watch"] = {
    play: (sid) => this.live(() => {
      this.liveSession(sid);
      watchEngine.play(this.host, sid);
    }),
    pause: (sid) => this.command(() => watchEngine.pause(this.host, sid)),
    step: (sid) => this.live(() => {
      this.liveSession(sid);
      watchEngine.stepOnce(this.host, sid);
    }),
    setPace: (sid, paceMs) => this.command(() => {
      watchEngine.setPace(this.host, sid, paceMs);
      this.patchSession(sid, {});
    }),
    direct: (sid, text) => this.command(() => watchEngine.direct(this.host, sid, text)),
    stepIn: (sid, text) => this.live(() => {
      this.liveSession(sid);
      watchEngine.stepIn(this.host, sid, text);
    }),
    extendWatch: (sid, turns) => this.live(() => {
      this.liveOf(sid);
      watchEngine.extendWatch(this.host, sid, turns ?? 10);
    }),
    summarise: (sid) => this.live(() => watchEngine.summarise(this.host, sid)),
  };

  // ── Usage ─────────────────────────────────────────────────────────────────
  // ── Admin (rev 1.3 addendum) ───────────────────────────────────────────────
  admin: HorizonClient["admin"] = {
    resetDemo: () => this.resetDemo(),
  };

  /** D-70: re-seed seed records only (seed copies win by id); user worlds, characters, forks, memories and ledger
   * rows survive, like the backend's POST /admin/reset-demo. Settings and the key aren't seed data: they stay. */
  private async resetDemo(): Promise<void> {
    await this.ready;
    const settings = this.db.settings;
    this.hardReset(SCENARIO_BY_ID.default, true);
    this.db.settings = settings;
    this.persistSoon();
    this.global({ type: "mock.reset" });
    this.notifyDev();
  }

  usage: HorizonClient["usage"] = {
    list: (opts) => this.query(() => {
      const since = opts?.sinceDays ? this.sched.wallNow() - opts.sinceDays * 86_400_000 : -Infinity;
      return this.db.ledger.filter((r) => Date.parse(r.at) >= since);
    }),
    summary: () => this.query((): UsageSummary => {
      const byCategory: UsageSummary["byCategory"] = { chat: 0, decision: 0, image: 0, music: 0, profile: 0, summary: 0, memory: 0, embedding: 0, energy_topup: 0 };
      const byCharacter: Record<string, number> = {};
      const bySession: Record<string, number> = {};
      let total = 0;
      let est = 0;
      for (const r of this.db.ledger) {
        total += r.costUsd;
        est += r.estimatedCostUsd ?? r.costUsd;
        byCategory[r.category] = round6(byCategory[r.category] + r.costUsd);
        if (r.characterId) byCharacter[r.characterId] = round6((byCharacter[r.characterId] ?? 0) + r.costUsd);
        if (r.sessionId) bySession[r.sessionId] = round6((bySession[r.sessionId] ?? 0) + r.costUsd);
      }
      return {
        todayUsd: this.db.settings.spentTodayUsd, totalUsd: round6(total), capUsd: this.db.settings.budget.dailyCapUsd,
        byCategory, byCharacter, bySession, estimatedUsd: round6(est), actualUsd: round6(total),
      };
    }),
  };

  onGlobal(cb: (e: GlobalEvent) => void): Unsubscribe {
    this.globals.add(cb);
    return () => { this.globals.delete(cb); };
  }

  // ── Dev (O18) ─────────────────────────────────────────────────────────────
  private readDev(): { scenario?: ScenarioId; speed?: DemoSpeed } | null {
    try {
      const raw = this.storage?.getItem(DEV_KEY);
      if (!raw) return null;
      const v = JSON.parse(raw) as { scenario?: string; speed?: number };
      return { scenario: isScenarioId(v.scenario) ? v.scenario : undefined, speed: v.speed === 2 || v.speed === 4 ? v.speed : 1 };
    } catch {
      return null;
    }
  }

  private notifyDev(): void {
    const s = this.dev?.getState();
    if (!s) return;
    try { this.storage?.setItem(DEV_KEY, JSON.stringify({ scenario: s.scenario, speed: s.speed })); } catch { /* quota */ }
    this.devSubs.forEach((cb) => cb(s));
  }

  /** `keepUserData` carries user-created records across the reseed, so a scenario lands on the current screen (DoD #2). */
  private hardReset(s: Scenario, keepUserData = false): void {
    const prev = this.db;
    this.runner.stopAll();
    for (const live of this.lives.values()) {
      clearLive(live);
      live.player.dispose();
    }
    this.lives.clear();
    this.sched.cancelAll();
    this.knowledgePending.clear();
    this.reseed(s);
    if (keepUserData && prev) {
      for (const k of ["worlds", "characters", "assets", "songs", "sessions", "memory", "knowledge", "knowledgeChunks", "jobs"] as const) {
        const into = this.db[k] as Record<string, unknown>;
        // A scenario that empties a collection (no_worlds) means it; don't refill it.
        if (!Object.keys(into).length) continue;
        for (const [id, v] of Object.entries(prev[k])) if (!(id in into)) into[id] = v;
      }
      const seen = new Set(this.db.ledger.map((r) => r.id));
      this.db.ledger.push(...prev.ledger.filter((r) => !seen.has(r.id)));
    }
    this.resumeJobs();
    knowledgeEngine.resumeIndexing(this.knowledgeHost());
  }

  private makeDev(): MockDevApi {
    return {
      ready: this.ready,
      getState: () => ({ scenario: this.scenario.id, speed: this.sched.speed as DemoSpeed, ready: this.isReady }),
      subscribe: (cb) => {
        this.devSubs.add(cb);
        return () => { this.devSubs.delete(cb); };
      },
      setScenario: async (id) => {
        await this.ready;
        const s = SCENARIO_BY_ID[id];
        if (s.overlay || id === "default") this.hardReset(s, true);
        else {
          this.applyScenarioState(s);
          if (s.settingsPatch) this.db.settings = deepMerge(this.db.settings, s.settingsPatch);
        }
        this.persistSoon();
        this.global({ type: "mock.reset" });
        this.notifyDev();
      },
      setSpeed: (speed) => {
        this.sched.setSpeed(speed);
        this.notifyDev();
      },
      resetDemoData: () => this.resetDemo(),
      setMockKey: async () => {
        await this.settings.setKey("sk-or-mock-reviewer-0000");
      },
    };
  }

  /** Test helper: the live dataset (read-only use). */
  get _db(): Dataset { return this.db; }
}

/** Shadow placeholder for wizard characters before a portrait exists (UI convenience). */
export const placeholderPortrait = (c: Character, emotion: Emotion = "neutral"): string =>
  shadowDataUrl(specFromAppearance(c.appearance, c.paletteId, emotion, "default"));
