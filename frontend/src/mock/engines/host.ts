// Live-session infrastructure shared by the mock engines (R1). Owner: EE.
// Every live turn is a generated event script (buildLineScript) appended to the session's ScriptPlayer, the same
// player class Replay uses. Turns run through a per-session task queue, so steering (Ask…, Interject, Step in)
// lands at the next boundary and never overlaps a streaming reply.
import type {
  Character, Emotion, Message, Session, StreamEvent, TurnTrace,
} from "../../contract/types";
import type { PricingTable } from "../../domain/cost";
import {
  decisionCostUsd, estimateTokens, FACE_CHECK_DECISION_TOKENS, REACTION_DECISION_TOKENS, round6, TURN_PLAN_DECISION_TOKENS,
} from "../../domain/cost";
import { EST_REPLY_POINTS, liveEnergy } from "../../domain/energy";
import type { PricePeriod } from "../../domain/rushHour";
import type { ScriptPlayer, TimelineEntry } from "../../engine/ScriptPlayer";
import type { SessionRuntimeState } from "../../engine/sessionReducer";
import { pickChatLine } from "../banks";
import type { BankLine } from "../banks";
import type { Dataset } from "../db/dataset";
import type { Rng } from "../rng";
import { liveCitations } from "../script/citations";
import { fixtureRow } from "../system1";
import type { ChunkRef } from "../script/citations";
import { buildLineScript } from "../script/turnScript";
import type { EmotionTiming, LineScript, LineSpec } from "../script/turnScript";
import type { TimingConfig } from "../timing.config";

export type Task = ((done: () => void) => void) & { epoch?: number };

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
  /** M10 (doc 07 G5; group-watch D12): bumped by each group send and Step in. A reply task captures it when queued;
   *  a stale task is skipped, and a stale turn never emits `turn.next`. */
  replyEpoch?: number;
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
export function enqueue(live: LiveSession, task: Task, front = false, epoch?: number): void {
  if (epoch !== undefined) task.epoch = epoch;
  if (front) live.queue.unshift(task);
  else live.queue.push(task);
  pump(live);
}

function pump(live: LiveSession): void {
  if (live.busy) return;
  let next = live.queue.shift();
  while (next && !isCurrent(live, next.epoch)) next = live.queue.shift(); // G5: a stale reply task never runs
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

/** G5: a user message (a group send, a Step in) arrives. Stale queued reply tasks are dropped; returns the new epoch. */
export function supersede(live: LiveSession): number {
  live.replyEpoch = (live.replyEpoch ?? 0) + 1;
  live.queue = live.queue.filter((t) => isCurrent(live, t.epoch));
  return live.replyEpoch;
}

export const isCurrent = (live: LiveSession, epoch: number | undefined): boolean =>
  epoch === undefined || epoch === (live.replyEpoch ?? 0);

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
  const e = liveEnergy(c.energy, h.wallNow(), { estReplyPoints: EST_REPLY_POINTS[h.period()] });
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
  dropReactions(h.live(sid));   // M9 D20 (E5): a user message drops every pending listener reaction
  return systemNote(h, sid, text, kind, { type: "user" }, extra);
}

// ── Listener reactions (M9: turn-plan-emotion D20, D21; the backend's sessions/after_turn.py) ─────────────────────
const REACT_TAG = "react:";
const FADE = new Set<string>(["surprised", "embarrassed"]);

/** D20: drop pending reactions: all of them, or one listener's (their own turn is starting). */
export function dropReactions(live: LiveSession, characterId?: string): void {
  live.player.cancel((e) => !!e.tag?.startsWith(REACT_TAG) && (characterId === undefined || e.tag.endsWith(`:${characterId}`)));
}

type ReactionEvent = Extract<StreamEvent, { type: "reaction" }>;

/** D20's re-check, run when the reaction is due (the backend runs it under its writer lock). */
export function reactionStillValid(s: SessionRuntimeState, r: ReactionEvent["payload"]): boolean {
  const session = s.session;
  if (session.emotionMode === "user" || session.status !== "active") return false;
  const part = session.participants.find((p) => p.characterId === r.characterId);
  if (!part || (r.source === "classifier" && part.mutedByUser)) return false;
  const streaming = s.streamingId ? s.messages[s.streamingId] : undefined;
  if (streaming?.author.type === "character" && streaming.author.characterId === r.characterId) return false;
  const reacted = s.messages[r.messageId];
  if (reacted && s.order.some((id) => {
    const m = s.messages[id];
    return !!m && m.author.type === "character" && m.author.characterId === r.characterId && m.seq > reacted.seq;
  })) return false;
  const face = part.currentEmotion ?? "neutral";
  return r.source === "default" ? FADE.has(face) : face !== r.emotion;
}

/** Live turns only (the seed build plays scripts as recorded): each reaction becomes a cancellable, re-checked
 *  callback, and a completed AUTO reply with listeners charges one simulated `reaction` decision at turn.end (D21). */
function liveReactions(h: EngineHost, sid: string, script: LineScript, messageId: string, charge: boolean): TimelineEntry<StreamEvent>[] {
  const out = script.entries.map((e): TimelineEntry<StreamEvent> => {
    if (e.item?.type !== "reaction") return e;
    const ev = e.item;
    return { t: e.t, tag: `${REACT_TAG}${messageId}:${ev.payload.characterId}`, run: () => {
      if (reactionStillValid(h.live(sid).state, ev.payload)) h.emit(sid, ev);
    } };
  });
  if (charge) out.push({ t: script.endMs, tag: messageId, run: () => h.charge(sid, "decision", decisionCostUsd(REACTION_DECISION_TOKENS, h.pricing.decision)) });
  return out;
}

// ── The 1:1 plan row and the face check (M9: turn-plan-emotion D24, D25; doc 13 W2; the scripted backend) ─────────
/** Jev's measured p50 (group A): the scripted backend's simulated decision latency. */
const DECISION_LATENCY_MS = 420;

function decisionCall(h: EngineHost, purpose: string, tokens: number): NonNullable<TurnTrace["calls"]>[number] {
  return { purpose, model: h.pricing.decision.model, costUsd: round6(decisionCostUsd(tokens, h.pricing.decision)), latencyMs: DECISION_LATENCY_MS };
}

/** After `faceCheckMs`: charge the check and add the fixture row ("yes") with a second insight, unless the message
 *  moved on to another variant (append_system1's guard). Stop, leave, a cap pause and the end cancel it (clearLive). */
function faceCheck(h: EngineHost, sid: string, messageId: string, variantId: string | undefined): void {
  const m = h.live(sid).state.messages[messageId];
  if (!m?.trace || (m.activeVariantId ?? `${messageId}_v1`) !== (variantId ?? `${messageId}_v1`)) return;
  h.charge(sid, "decision", decisionCostUsd(FACE_CHECK_DECISION_TOKENS, h.pricing.decision));
  const rows = (m.trace.system1?.questions ?? []).filter((q) => q.purpose !== "face_check");
  const trace: TurnTrace = {
    ...m.trace,
    system1: { ...m.trace.system1, questions: [...rows, fixtureRow("face_check", "yes")] },
    calls: [...(m.trace.calls ?? []), decisionCall(h, "face_check", FACE_CHECK_DECISION_TOKENS)],
  };
  h.emit(sid, { type: "insight", payload: { messageId, trace } });
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
  system1?: TurnTrace["system1"];
  /** Regenerate: stream a new variant into this message. */
  variantOf?: string;
  /** M9 (D25): a generated 1:1 greeting, planned with `emotion_greeting`. */
  greeting?: boolean;
  /** docs/ai/04 P9: say `line` word for word at no cost (the first chat's approved greeting). */
  verbatim?: boolean;
  /** G5: the reply epoch this turn's task captured; the turn announces only while it is current. */
  epoch?: number;
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
  const pool = opts.verbatim ? [] : knowledgePool(h.db, cid);
  const cited = pool.length ? liveCitations(`${sid}:${messageId}`, line.text, opts.prompt ?? "", pool, h.rng(`${sid}:${live.turn}:cite`)) : null;
  const text = cited?.text ?? line.text;
  // M9 D25: a 1:1 turn (not the verbatim greeting) is planned: one `turn_plan` charge and the emotion row, its answer
  // the face the reply shows. The face check follows a completed AUTO reply whose face isn't neutral (D24).
  const planned = session.mode === "one_on_one" && !opts.verbatim;
  if (planned) h.charge(sid, "decision", decisionCostUsd(TURN_PLAN_DECISION_TOKENS, h.pricing.decision));
  const planRow = planned
    ? fixtureRow(opts.greeting ? "emotion_greeting" : "emotion_reply", line.emotion, cid) : undefined;
  const system1 = planRow ? { questions: [planRow, ...(opts.system1?.questions ?? [])] } : opts.system1;
  const spec: LineSpec = {
    sessionId: sid,
    messageId,
    characterId: cid,
    text,
    emotion: line.emotion,
    emotionSource: opts.verbatim ? "default" : "llm",
    verbatim: opts.verbatim,
    message: variantOf ? undefined : { kind: "chat", ...opts.message },
    variantId,
    forcedBy: opts.forcedBy,
    skipped: opts.skipped,
    routing: opts.routing,
    system1,
    planCalls: planned ? [decisionCall(h, "turn_plan", TURN_PLAN_DECISION_TOKENS)] : undefined,
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
  const entries = liveReactions(h, sid, script, messageId, script.status === "complete" && !manual && listeners.length > 0);
  if (script.status === "complete" && !manual && !opts.verbatim && line.emotion !== "neutral") {
    entries.push({ t: script.endMs + h.timing.faceCheckMs, tag: `face:${messageId}`, run: () => faceCheck(h, sid, messageId, variantId) });
  }
  h.play(sid, entries, messageId);
  return { messageId, endMs: script.endMs, status: script.status };
}

/** Speak, then call `done` once the turn has ended (+ the turn gap). Skipped speakers call done at once. */
export function speakThen(h: EngineHost, sid: string, cid: string, opts: SpeakOpts, done: (r: SpeakResult | null) => void): void {
  if (!isCurrent(h.live(sid), opts.epoch)) {
    done(null); // G5: superseded before it announced, so no turn.next
    return;
  }
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
