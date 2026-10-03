// Live-session infrastructure shared by the mock engines (R1). Owner: EE.
// Every live turn is a generated event script (buildLineScript) appended to the session's ScriptPlayer, the same
// player class Replay uses. Turns run through a per-session task queue, so steering (Ask…, Interject, Step in)
// lands at the next boundary and never overlaps a streaming reply.
import type {
  Character, Emotion, Message, Session, StreamEvent, TurnTrace,
} from "../../contract/types";
import type { PricingTable } from "../../domain/cost";
import { estimateTokens } from "../../domain/cost";
import { EST_REPLY_POINTS, liveEnergy } from "../../domain/energy";
import type { PricePeriod } from "../../domain/rushHour";
import type { ScriptPlayer, TimelineEntry } from "../../engine/ScriptPlayer";
import type { SessionRuntimeState } from "../../engine/sessionReducer";
import { pickChatLine } from "../banks";
import type { BankLine } from "../banks";
import type { Dataset } from "../db/dataset";
import type { Rng } from "../rng";
import { liveCitations } from "../script/citations";
import type { ChunkRef } from "../script/citations";
import { buildLineScript } from "../script/turnScript";
import type { EmotionTiming, LineScript, LineSpec } from "../script/turnScript";
import type { TimingConfig } from "../timing.config";

export type Task = (done: () => void) => void;

export interface LiveSession {
  id: string;
  player: ScriptPlayer<StreamEvent>;
  /** Server-side truth: the reducer over every event this session has emitted. */
  state: SessionRuntimeState;
  turn: number;
  queue: Task[];
  busy: boolean;
  /** Debate/watch auto-run is held (❚❚, daily cap, leaving). */
  held: boolean;
  recent: string[];
  current?: { messageId: string; characterId: string; script: LineScript; startPos: number; text: string };
  /** Watch: director's note colours the next turns. */
  direction?: { note: string; turnsLeft: number };
  /** Watch: nudged next speaker. Debate: forced next speaker. */
  nudge?: string;
  /** Debate cursor. */
  debate?: { order: string[]; idx: number; skipToClosing?: boolean; extend?: boolean };
  /** Watch round-robin cursor. */
  watchIdx?: number;
}

export interface EngineHost {
  db: Dataset;
  timing: TimingConfig;
  pricing: PricingTable;
  period(): PricePeriod;
  wallNow(): number;
  iso(): string;
  newId(prefix: string): string;
  rng(seed: string): Rng;
  live(sessionId: string): LiveSession;
  /** Deliver events now (t = 0) through the session's player. */
  emit(sessionId: string, ...events: StreamEvent[]): void;
  /** Append a timed script relative to now. */
  play(sessionId: string, entries: TimelineEntry<StreamEvent>[], tag?: string): void;
  /** Run `fn` after `ms` of mock time (cancelled by Stop/leave). */
  after(sessionId: string, ms: number, fn: () => void): void;
  /** The next scripted fault for a character turn (consumed). */
  takeStreamFault(): LineSpec["fault"];
  /** True when today's spend has reached the daily cap. */
  dailyCapReached(): boolean;
  /** Ledger + daily spend for non-reply AI calls (verdict, summary, routing). Never drains energy (D-42). */
  charge(sessionId: string, category: "decision" | "summary", costUsd: number): void;
}

// ── Queue ────────────────────────────────────────────────────────────────────
export function enqueue(live: LiveSession, task: Task, front = false): void {
  if (front) live.queue.unshift(task);
  else live.queue.push(task);
  pump(live);
}

function pump(live: LiveSession): void {
  if (live.busy) return;
  const next = live.queue.shift();
  if (!next) return;
  live.busy = true;
  let finished = false;
  next(() => {
    if (finished) return;
    finished = true;
    live.busy = false;
    pump(live);
  });
}

/** Cancel everything pending for a session (Stop, end, mock reset). */
export function clearLive(live: LiveSession, opts?: { keepCurrentTurn?: boolean }): void {
  live.queue = [];
  live.busy = false;
  if (opts?.keepCurrentTurn && live.current) {
    const mid = live.current.messageId;
    live.player.cancel((e) => e.tag !== mid);
  } else {
    live.player.cancel(() => true);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
export const sessionOf = (h: EngineHost, sid: string): Session => h.live(sid).state.session;
export const charOf = (h: EngineHost, id: string): Character | undefined => h.db.characters[id];
export const firstName = (c: Character): string =>
  c.profile.name.split(" ").find((w) => !/^(dr|prof|mr|ms|mrs)\.?$/i.test(w)) ?? c.profile.name;

/** Settled live energy for a character (regen applied). */
export function energyNow(h: EngineHost, cid: string): { current: number; max: number } {
  const c = h.db.characters[cid];
  if (!c) return { current: 0, max: 1000 };
  const e = liveEnergy(c.energy, h.wallNow());
  return { current: e.current, max: e.max };
}

export function isAsleep(h: EngineHost, cid: string): boolean {
  return energyNow(h, cid).current < EST_REPLY_POINTS[h.period()];
}

export function systemNote(h: EngineHost, sid: string, content: string, kind: Message["kind"] = "system_note", author: Message["author"] = { type: "system" }, extra?: Partial<Message>): Message {
  const live = h.live(sid);
  const seq = Math.max(0, ...live.state.order.map((id) => live.state.messages[id]?.seq ?? 0)) + 1;
  return { id: h.newId("msg"), sessionId: sid, seq, author, kind, content, status: "complete", createdAt: h.iso(), ...extra };
}

export function userMessage(h: EngineHost, sid: string, text: string, kind: Message["kind"] = "chat", extra?: Partial<Message>): Message {
  return systemNote(h, sid, text, kind, { type: "user" }, extra);
}

function pickEmotionTiming(h: EngineHost, rng: Rng): EmotionTiming {
  const { before, early } = h.timing.emotionTiming;
  const r = rng.next();
  return r < before ? "before" : r < before + early ? "early" : "late";
}

function historyTokens(live: LiveSession): number {
  let n = 0;
  for (const id of live.state.order) n += estimateTokens(live.state.messages[id]?.content ?? "");
  return n;
}

export interface SpeakOpts {
  /** Explicit line; otherwise picked from the bank for `prompt`. */
  line?: BankLine;
  prompt?: string;
  message?: Partial<Message>;
  forcedBy?: LineSpec["forcedBy"];
  skipped?: LineSpec["skipped"];
  routing?: TurnTrace["routing"];
  /** Regenerate: stream a new variant into this message. */
  variantOf?: string;
}

export interface SpeakResult { messageId: string; endMs: number; status: Message["status"] }

/** D-59: the character's indexed passages (sources still present). */
export function knowledgePool(db: Dataset, cid: string): ChunkRef[] {
  const sources = Object.values(db.knowledge).filter((k) => k.characterId === cid && k.status === "indexed");
  if (!sources.length) return [];
  const byId = Object.fromEntries(sources.map((k) => [k.id, k]));
  return Object.values(db.knowledgeChunks ?? {})
    .filter((c) => byId[c.sourceId])
    .sort((a, b) => a.sourceId.localeCompare(b.sourceId) || a.index - b.index)
    .map((chunk) => ({ chunk, source: byId[chunk.sourceId] }));
}

/** Queue one character turn on the player. Returns null when the character can't afford it (asleep). */
export function speak(h: EngineHost, sid: string, cid: string, opts: SpeakOpts = {}): SpeakResult | null {
  const live = h.live(sid);
  const c = h.db.characters[cid];
  if (!c) return null;
  const energy = energyNow(h, cid);
  if (energy.current < EST_REPLY_POINTS[h.period()]) return null;
  const rng = h.rng(`${sid}:${live.turn++}`);
  const line = opts.line ?? pickChatLine(c, opts.prompt ?? "", rng, live.recent);
  live.recent = [line.text, ...live.recent].slice(0, 8);
  const session = live.state.session;
  const manual = session.emotionMode === "user";
  const variantOf = opts.variantOf;
  const existing = variantOf ? live.state.messages[variantOf] : undefined;
  const messageId = variantOf ?? h.newId("msg");
  const variantId = variantOf ? `${messageId}_v${(existing?.variants?.length || 1) + 1}` : undefined;
  const listeners = session.participants
    .filter((p) => p.characterId !== cid && !p.mutedByUser && !isAsleep(h, p.characterId))
    .map((p) => p.characterId);
  const prior = live.state.order.map((id) => live.state.messages[id]).filter((m): m is Message => !!m && m.author.type === "character" && m.author.characterId !== cid);
  const recall = prior.length ? prior[prior.length - 1] : undefined;
  // Separate rng stream: characters without knowledge replay exactly as before.
  const pool = knowledgePool(h.db, cid);
  const cited = pool.length ? liveCitations(`${sid}:${messageId}`, line.text, opts.prompt ?? "", pool, h.rng(`${sid}:${live.turn}:cite`)) : null;
  const text = cited?.text ?? line.text;
  const spec: LineSpec = {
    sessionId: sid,
    messageId,
    characterId: cid,
    text,
    emotion: line.emotion,
    emotionSource: "llm",
    message: variantOf ? undefined : { kind: "chat", ...opts.message },
    variantId,
    forcedBy: opts.forcedBy,
    skipped: opts.skipped,
    routing: opts.routing,
    listeners,
    reactions: manual ? null : undefined,
    energyBefore: energy,
    period: h.period(),
    historyTokens: historyTokens(live),
    emotionTiming: pickEmotionTiming(h, rng),
    contextInSession: recall ? [{ text: `${recall.content.slice(0, 60)}…`, messageId: recall.id }] : undefined,
    fault: h.takeStreamFault(),
    ...(cited ? { citations: cited.citations, knowledge: cited.knowledge } : {}),
  };
  const script = buildLineScript(spec, h.timing, h.pricing, rng);
  live.current = { messageId, characterId: cid, script, startPos: live.player.position, text };
  h.play(sid, script.entries, messageId);
  return { messageId, endMs: script.endMs, status: script.status };
}

/** Speak, then call `done` once the turn has ended (+ the turn gap). Skipped speakers call done at once. */
export function speakThen(h: EngineHost, sid: string, cid: string, opts: SpeakOpts, done: (r: SpeakResult | null) => void): void {
  const r = speak(h, sid, cid, opts);
  if (!r) {
    done(null);
    return;
  }
  h.after(sid, r.endMs + h.timing.turnGapMs, () => done(r));
}

/** "{name} is asleep" note (+ energy_exhausted error so the UI can offer Top up). */
export function asleepNote(h: EngineHost, sid: string, cid: string, skipping: boolean): void {
  const c = h.db.characters[cid];
  if (!c) return;
  const name = firstName(c);
  const msg = systemNote(h, sid, skipping ? `${name} is asleep, skipping.` : `${name} is asleep (⚡ ${energyNow(h, cid).current}).`, "system_note", { type: "system" }, { targetCharacterId: cid });
  h.emit(sid,
    { type: "message", payload: { message: msg } },
    { type: "error", payload: { code: "energy_exhausted", message: `${name} is asleep (⚡ 0).`, retryable: false, messageId: msg.id } },
  );
}

export const speakingCast = (s: Session): string[] => s.participants.filter((p) => !p.mutedByUser).map((p) => p.characterId);

export function setEmotionEvent(cid: string, emotion: Emotion): StreamEvent {
  return { type: "emotion", payload: { characterId: cid, emotion, source: "user" } };
}
