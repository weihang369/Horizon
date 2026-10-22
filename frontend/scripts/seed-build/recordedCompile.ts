// A recorded session (real replies, exported by `horizon demo export --session`) → seed SessionEvents. The screenplay
// keeps owning the seed ids and the start time; the recording brings everything that happened. Messages and the final
// session are produced BY the reducer from the rewritten events, as for screenplays, so replay equivalence holds by
// construction (the backend's seed import re-checks it).
import type { Message, Session, SessionEvent, StreamEvent } from "../../src/contract/types";
import { energyState } from "../../src/domain/energy";
import { initialRuntime, orderedMessages, reduceAll } from "../../src/engine/sessionReducer";
import type { CompiledSession } from "./compile";
import type { RecordedSession } from "./recorded";
import type { Screenplay } from "./types";

const pad = (n: number, w: number) => String(n).padStart(w, "0");
/** SessionEvent keeps `type` and `payload` apart; this view narrows the payload by its type. */
const stream = (e: SessionEvent) => ({ type: e.type, payload: e.payload }) as StreamEvent;
const ISO = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z/g;
const MSG_ID = /^msg_[0-9A-Z]{26}$/;

/** What the build needs to map other recorded rows (memories) onto this session. */
export interface RecordingMap {
  sourceSessionId: string;
  seedSessionId: string;
  shiftMs: number;
  messageIds: Record<string, string>;
}

/** Deep-copy `value`, renaming ids found in `ids` and moving every ISO instant (also inside longer strings) by `shiftMs`. */
export function rewrite<T>(value: T, ids: Record<string, string>, shiftMs: number): T {
  const walk = (v: unknown): unknown => {
    if (typeof v === "string") {
      if (ids[v]) return ids[v];
      return v.replace(ISO, (s) => new Date(Date.parse(s) + shiftMs).toISOString());
    }
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)]));
    return v;
  };
  return walk(value) as T;
}

function messageIdMap(sp: Screenplay, rec: RecordedSession): Record<string, string> {
  const map: Record<string, string> = {};
  for (const m of [...rec.messages].sort((a, b) => a.seq - b.seq)) map[m.id] = `msg_${sp.msgKey}${pad(m.seq, 2)}`;
  // A reply that never became a message (e.g. a blocked one that left the screen) still has events: number it after.
  let next = Math.max(0, ...rec.messages.map((m) => m.seq));
  const visit = (v: unknown): void => {
    if (typeof v === "string") {
      if (MSG_ID.test(v) && !map[v]) map[v] = `msg_${sp.msgKey}${pad(++next, 2)}`;
    } else if (Array.isArray(v)) v.forEach(visit);
    else if (v && typeof v === "object") Object.values(v).forEach(visit);
  };
  for (const e of [...rec.events].sort((a, b) => a.seq - b.seq)) visit(e.payload);
  return map;
}

/**
 * Energy: each character's replay ends at its seed energy (as screenplays do), never starting above its max. The
 * offset applies to `energy` events and to the traces' `energy.remaining`.
 */
function energyOffsets(events: SessionEvent[], endEnergy: Record<string, number>): Record<string, number> {
  const last: Record<string, number> = {};
  const peak: Record<string, { current: number; max: number }> = {};
  for (const e of events) {
    const ev = stream(e);
    if (ev.type !== "energy") continue;
    const { characterId, current, max } = ev.payload;
    last[characterId] = current;
    if (!peak[characterId] || current > peak[characterId].current) peak[characterId] = { current, max };
  }
  const out: Record<string, number> = {};
  for (const [c, cur] of Object.entries(last)) {
    const want = (endEnergy[c] ?? cur) - cur;
    out[c] = Math.min(want, peak[c].max - peak[c].current);
  }
  return out;
}

function adjustEnergy(e: SessionEvent, offsets: Record<string, number>): SessionEvent {
  const ev = stream(e);
  if (ev.type === "energy") {
    const { characterId, max } = ev.payload;
    const current = Math.max(0, Math.round((ev.payload.current + (offsets[characterId] ?? 0)) * 1000) / 1000);
    const { fullAt: _drop, ...rest } = ev.payload;
    return { ...e, payload: { ...rest, current, state: energyState(current, max) } };
  }
  if (ev.type === "insight" && ev.payload.trace.energy) {
    const en = ev.payload.trace.energy;
    const remaining = Math.max(0, en.remaining + (offsets[en.characterId] ?? 0));
    return { ...e, payload: { ...ev.payload, trace: { ...ev.payload.trace, energy: { ...en, remaining } } } };
  }
  return e;
}

export function compileRecorded(
  sp: Screenplay, rec: RecordedSession, endEnergy: Record<string, number>, knowledgeIds: Record<string, string>,
  adjust = true,
): { compiled: CompiledSession; map: RecordingMap } {
  const sorted = [...rec.events].sort((a, b) => a.seq - b.seq);
  if (!sorted.length) throw new Error(`[seed-build] recording for ${sp.session.id} has no events`);
  const shiftMs = Date.parse(sp.startAt) - Date.parse(sorted[0].at);
  const messageIds = messageIdMap(sp, rec);
  const ids = { ...knowledgeIds, ...messageIds, [rec.source]: sp.session.id };

  const moved = sorted.map((e) => rewrite(e, ids, shiftMs));
  // D-110: a story-clock recording of the whole demo carries the real energy (the characters' end state comes from
  // the same run), so nothing is moved; older recordings end at the fixture's energy as before
  const offsets = adjust ? energyOffsets(moved, endEnergy) : {};
  const events: SessionEvent[] = moved.map((e, i) => ({
    ...adjustEnergy(e, offsets), id: `evt_${sp.evtKey}${pad(i + 1, 4)}`, sessionId: sp.session.id, seq: i + 1,
  }) as SessionEvent);

  // The base the backend's import also derives (seed.py `seed_base_session`): the final session with its counters reset.
  const recorded = rewrite(rec.session, ids, shiftMs);
  const { initialState: _s, ...scripted } = sp.session;
  const candidate: Session = { ...recorded, ...scripted, participants: recorded.participants, config: recorded.config };
  const { lastMessageAt: _l, pausedReason: _p, ...rest } = candidate;
  const base: Session = { ...rest, status: "active", state: null, costUsd: 0, messageCount: 0, updatedAt: candidate.createdAt };
  const final = reduceAll(initialRuntime(base), events);

  const spent: Record<string, number> = {};
  for (const e of events) {
    const ev = stream(e);
    if (ev.type === "energy" && ev.payload.spent) spent[ev.payload.characterId] = (spent[ev.payload.characterId] ?? 0) + ev.payload.spent;
  }
  const messages: Message[] = orderedMessages(final);
  return {
    compiled: { session: final.session, messages, events, spent },
    map: { sourceSessionId: rec.source, seedSessionId: sp.session.id, shiftMs, messageIds },
  };
}
