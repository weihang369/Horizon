// Debate engine (MULTI-05..08): walks the DebateConfig phases, alternating sides, with steering inserted at turn
// boundaries. Verdict scores come from the PRNG and honour arbiter / You decide / none / panel.
import type {
  DebateConfig, DebatePhase, DebateState, DebateTurnPhase, Message, Side, StreamEvent, Verdict,
} from "../../contract/types";
import { chatCostUsd } from "../../domain/cost";
import { answerTo, debateLine } from "../banks";
import type { EngineHost, LiveSession } from "./host";
import { asleepNote, clearLive, enqueue, isAsleep, speakThen, systemNote, userMessage } from "./host";

const LABEL: Record<DebatePhase, string> = { setup: "SETUP", opening: "OPENING", rebuttal: "REBUTTAL", closing: "CLOSING", verdict: "VERDICT", ended: "ENDED" };
export const DEFAULT_RUBRIC = [
  { id: "evidence", label: "Evidence" }, { id: "rebuttal", label: "Rebuttal" },
  { id: "clarity", label: "Clarity" }, { id: "persuasion", label: "Persuasion" },
];

export type DebateHost = EngineHost;

const cfgOf = (live: LiveSession) => live.state.session.config as DebateConfig;
const stateOf = (live: LiveSession): DebateState => (live.state.session.state as DebateState | null) ?? { phase: "setup", round: 0, iteration: 1 };
const sideOf = (live: LiveSession, cid: string): Side | undefined => live.state.session.participants.find((p) => p.characterId === cid)?.side ?? undefined;

/** Speaking order for one phase: alternate prop/opp (two-sided) or cast order (panel). */
export function phaseOrder(cfg: DebateConfig, cast: string[]): string[] {
  if (cfg.format !== "two_sided" || !cfg.sides) return [...cast];
  const { prop, opp } = cfg.sides;
  const out: string[] = [];
  for (let i = 0; i < Math.max(prop.length, opp.length); i++) {
    if (prop[i]) out.push(prop[i]);
    if (opp[i]) out.push(opp[i]);
  }
  return out;
}

// ── Slots (M11; doc 08 V1, V3, V5; debate design D3, D4): the backend's `sessions/debate_slots.py`, line for line ──
type Slot = Side | null;
type Fill = { action: "speak" | "skip" | "pause"; who?: string; asleep: string[] };

const twoSided = (cfg: DebateConfig): boolean => cfg.format === "two_sided" && !!cfg.sides;

/** The side of each slot in a phase (`null` for a panel's). */
export function phaseSlots(cfg: DebateConfig, cast: string[]): Slot[] {
  if (!twoSided(cfg)) return cast.map(() => null);
  const { prop, opp } = cfg.sides!;
  const out: Slot[] = [];
  for (let i = 0; i < Math.max(prop.length, opp.length); i++) {
    if (i < prop.length) out.push("prop");
    if (i < opp.length) out.push("opp");
  }
  return out;
}

const membersOf = (cfg: DebateConfig, cast: string[], side: Slot): string[] =>
  side === null || !twoSided(cfg) ? [...cast] : [...cfg.sides![side]];

const isBanner = (m: Message) => m.author.type === "system" && m.kind === "system_note" && m.content.startsWith("ROUND ");
const isArgument = (m: Message) => m.author.type === "character" && m.kind === "chat" && !m.forcedSpeaker;
const isSkip = (m: Message) => m.author.type === "system" && !!m.targetCharacterId && m.content.endsWith(" is asleep, skipping.");

/** The current phase's cursor from the log: slots used (arguments and skip notes since the banner), and who was heard. */
export function cursorOf(msgs: Message[]): { used: number; heard: string[] } {
  let start = 0;
  for (const m of msgs) if (isBanner(m)) start = m.seq;
  let used = 0;
  const heard: string[] = [];
  for (const m of msgs) {
    if (m.seq <= start) continue;
    if (isArgument(m)) {
      used++;
      const cid = m.author.characterId ?? "";
      if (!heard.includes(cid)) heard.push(cid);
    } else if (isSkip(m)) used++;
  }
  return { used, heard };
}

/** V3 and V5: the first awake, unheard member speaks; none but someone awake skips the slot; nobody awake pauses. */
export function fillSlot(members: string[], heard: string[], awake: (cid: string) => boolean): Fill {
  const eligible = members.filter((c) => !heard.includes(c) && awake(c));
  if (eligible.length) return { action: "speak", who: eligible[0], asleep: [] };
  const asleep = members.filter((c) => !awake(c));
  if (asleep.length < members.length) {
    const unheard = asleep.filter((c) => !heard.includes(c));
    return { action: "skip", who: unheard[0] ?? asleep[0], asleep };
  }
  return { action: "pause", asleep };
}

const logOf = (live: LiveSession): Message[] =>
  live.state.order.map((id) => live.state.messages[id]).filter((m): m is Message => !!m);

function nextSlot(h: EngineHost, live: LiveSession): { idx: number; side: Slot; fill: Fill } | null {
  const cfg = cfgOf(live);
  const cast = live.state.session.participants.map((p) => p.characterId);
  const slots = phaseSlots(cfg, cast);
  const cur = cursorOf(logOf(live));
  if (cur.used >= slots.length) return null;
  const side = slots[cur.used];
  return { idx: cur.used, side, fill: fillSlot(membersOf(cfg, cast, side), cur.heard, (c) => !isAsleep(h, c)) };
}

const SIDE_NAME: Record<Side, string> = { prop: "Proposition", opp: "Opposition" };

function pauseSide(h: EngineHost, sid: string, side: Slot, asleep: string[]): void {
  const live = h.live(sid);
  for (const cid of asleep) asleepNote(h, sid, cid, false, meta(live));
  live.held = true;
  h.emit(sid,
    { type: "message", payload: { message: systemNote(h, sid, side === null ? "Everyone on the panel is asleep. Top someone up to continue the debate." : `The ${SIDE_NAME[side]} is asleep. Top someone up to continue the debate.`) } },
    { type: "session.paused", payload: { reason: "user" } },
  );
}

function setState(h: EngineHost, sid: string, patch: Partial<DebateState>): void {
  const live = h.live(sid);
  h.emit(sid, { type: "session.state", payload: { state: { ...stateOf(live), ...patch } } });
}

function beginPhase(h: DebateHost, sid: string, phase: DebateTurnPhase, iteration = 1): void {
  const live = h.live(sid);
  const cfg = cfgOf(live);
  const round = cfg.phases.indexOf(phase) + 1;
  live.debate = {};
  const events: StreamEvent[] = [
    { type: "phase", payload: { phase, round, iteration } },
    { type: "message", payload: { message: systemNote(h, sid, `ROUND ${round} · ${LABEL[phase]}${iteration > 1 ? " · EXTENDED" : ""}`) } },
  ];
  if (cfg.moderator === "auto_host") {
    events.push({ type: "message", payload: { message: systemNote(h, sid, hostLine(phase, cfg.motion), "narration", { type: "host" }) } });
  }
  h.emit(sid, ...events);
}

const hostLine = (phase: DebateTurnPhase, motion: string): string =>
  phase === "opening" ? `Welcome. Tonight's motion: "${motion}". Opening statements, please.`
    : phase === "rebuttal" ? "Thank you. Rebuttals now: engage with what you actually heard."
      : "Closing statements. Make them count.";

// M11 (debate D11): the verdict lead-in after the VERDICT banner with Auto host, one per verdict mode (the scripted
// host's fixed lines; naive and agent write theirs).
export const LEAD_INS: Record<string, string> = {
  arbiter: "Thank you all. The arbiter is weighing the arguments.",
  user: "Thank you all. Now it's your call.",
  none: "Thank you all. Here is the summary.",
};

export function start(h: DebateHost, sid: string): void {
  const live = h.live(sid);
  const cfg = cfgOf(live);
  enqueue(live, (done) => h.after(sid, h.timing.debateStartMs, () => {
    beginPhase(h, sid, cfg.phases[0] ?? "opening");
    done();
    step(h, sid);
  }));
}

/** One normal debate turn (or a phase boundary), queued behind any steering. */
export function step(h: DebateHost, sid: string): void {
  const live = h.live(sid);
  enqueue(live, (done) => {
    const st = stateOf(live);
    if (st.phase === "verdict" || st.phase === "ended" || live.state.session.status === "ended") return done();
    if (st.phase === "setup") {
      beginPhase(h, sid, cfgOf(live).phases[0] ?? "opening");
    }
    live.debate ??= {};
    const cur = live.debate;
    const cfg = cfgOf(live);
    if (cur.skipToClosing && stateOf(live).phase !== "closing") {
      beginPhase(h, sid, "closing");
      live.debate!.skipToClosing = false;
      done();
      return scheduleNext(h, sid);
    }
    const slot = nextSlot(h, live);
    if (!slot) {
      const phase = stateOf(live).phase as DebateTurnPhase;
      const extend = cur.extend;
      const nextPhase = cfg.phases[cfg.phases.indexOf(phase) + 1];
      if (extend) beginPhase(h, sid, phase, stateOf(live).iteration + 1);
      else if (nextPhase) beginPhase(h, sid, nextPhase);
      else {
        done();
        return goVerdict(h, sid);
      }
      done();
      return scheduleNext(h, sid);
    }
    if (slot.fill.action === "pause") {
      pauseSide(h, sid, slot.side, slot.fill.asleep);
      return done();
    }
    if (slot.fill.action === "skip") {
      asleepNote(h, sid, slot.fill.who!, true, meta(live));
      done();
      return scheduleNext(h, sid, 200);
    }
    const cid = slot.fill.who!;
    const announced = cur.announced;
    cur.announced = undefined;
    const skipped = announced && announced[0] === slot.idx && announced[1] !== cid && isAsleep(h, announced[1])
      ? [{ characterId: announced[1], reason: "exhausted" as const }] : undefined;
    const now = stateOf(live);
    const side = sideOf(live, cid);
    speakThen(h, sid, cid, {
      line: debateLine(now.phase as DebateTurnPhase, cfg.motion, side, live.turn + slot.idx),
      forcedBy: "round_order",
      ...(skipped ? { skipped } : {}),
      message: { debate: { phase: now.phase, round: now.round, iteration: now.iteration, ...(side ? { side } : {}) } },
    }, () => {
      done();
      const after = nextSlot(h, live);
      if (after && after.fill.action === "speak" && after.fill.who) {
        h.emit(sid, { type: "turn.next", payload: { nextSpeakerId: after.fill.who } });
        live.debate = { ...(live.debate ?? {}), announced: [after.idx, after.fill.who] };
      }
      scheduleNext(h, sid);
    });
  });
}

function scheduleNext(h: DebateHost, sid: string, ms?: number): void {
  const live = h.live(sid);
  const cfg = cfgOf(live);
  if (!cfg.autoAdvance || live.held) return;
  h.after(sid, ms ?? cfg.pauseMs, () => {
    if (!live.held && cfgOf(live).autoAdvance) step(h, sid);
  });
}

// ── Verdict ──────────────────────────────────────────────────────────────────
export function makeVerdict(h: EngineHost, live: LiveSession, by: Verdict["decidedBy"], picked?: Side): Verdict {
  const cfg = cfgOf(live);
  const rng = h.rng(`${live.id}:verdict`);
  const rubric = cfg.rubric?.length ? cfg.rubric : DEFAULT_RUBRIC;
  const twoSided = cfg.format === "two_sided";
  const msgs = live.state.order.map((id) => live.state.messages[id]).filter((m): m is Message => !!m && m.author.type === "character");
  const pointsFor = (pred: (m: Message) => boolean) =>
    msgs.filter(pred).slice(0, 4).map((m) => `${m.content.split(/(?<=[.!?])\s/)[0].slice(0, 110)}`);
  const summary = twoSided
    ? (["prop", "opp"] as Side[]).map((s) => ({ subjectId: s, points: pointsFor((m) => m.debate?.side === s) }))
    : live.state.session.participants.map((p) => ({ subjectId: p.characterId, points: pointsFor((m) => m.author.characterId === p.characterId) }));
  if (by === "none" || !twoSided) {
    return { decidedBy: by === "user" ? "none" : by, strongerCase: null, summary, keyDisagreement: "Whether the measured gains generalise beyond the cases that were studied." };
  }
  const arbiterSide: Side | null = rng.chance(0.15) ? null : rng.chance(0.5) ? "prop" : "opp";
  const winner = by === "user" ? picked ?? null : arbiterSide;
  const scores = (["prop", "opp"] as Side[]).flatMap((s) => rubric.map((r) => ({
    subjectId: s, criterionId: r.id,
    value: Math.round(s === arbiterSide ? rng.range(6.5, 9) : arbiterSide === null ? rng.range(6, 8) : rng.range(4.5, 7.5)),
  })));
  return {
    decidedBy: by,
    strongerCase: winner,
    scoresBy: "side",
    scores,
    summary,
    keyDisagreement: "Whether the measured gains generalise beyond the cases that were studied.",
    rationale: arbiterSide === null
      ? "Both sides argued well within their own framing; neither engaged the other's strongest point decisively."
      : `The ${arbiterSide === "prop" ? "proposition" : "opposition"} engaged the other side's evidence directly and kept its claims inside what that evidence supports.`,
  };
}

function finish(h: EngineHost, sid: string, verdict?: Verdict): void {
  const live = h.live(sid);
  const st = stateOf(live);
  const text = verdict
    ? verdict.strongerCase ? `STRONGER CASE: ${verdict.strongerCase === "prop" ? "PROPOSITION" : "OPPOSITION"}` : verdict.decidedBy === "none" || cfgOf(live).format === "panel" ? "SUMMARY" : "TOO CLOSE TO CALL"
    : "";
  const events: StreamEvent[] = [];
  if (verdict) {
    events.push({ type: "message", payload: { message: systemNote(h, sid, text, "verdict") } });
    events.push({ type: "session.state", payload: { state: { ...st, verdict } } });
  }
  events.push({ type: "phase", payload: { phase: "ended", round: st.round, iteration: st.iteration } });
  events.push({ type: "session.state", payload: { status: "ended", state: { ...st, ...(verdict ? { verdict } : {}), phase: "ended", nextSpeakerId: undefined } } });
  h.emit(sid, ...events);
}

export function goVerdict(h: DebateHost, sid: string): void {
  const live = h.live(sid);
  const cfg = cfgOf(live);
  h.emit(sid,
    { type: "phase", payload: { phase: "verdict", round: cfg.phases.length + 1, iteration: 1 } },
    { type: "message", payload: { message: systemNote(h, sid, `ROUND ${cfg.phases.length + 1} · VERDICT`) } },
  );
  if (cfg.moderator === "auto_host") {
    h.emit(sid, { type: "message", payload: { message: systemNote(h, sid, LEAD_INS[cfg.verdictBy] ?? LEAD_INS.arbiter, "narration", { type: "host" }) } });
  }
  if (cfg.verdictBy === "user") return; // waits for pickStrongerCase
  enqueue(live, (done) => h.after(sid, 1800, () => {
    // M11 (debate D15, a parity fix): the scripted verdict is a chat call, purpose `verdict`, as the backend records it
    h.charge(sid, "chat", chatCostUsd({ tokensIn: 6200, tokensCached: 2400, tokensOut: 420 }, h.pricing.chat, h.period()), "verdict");
    finish(h, sid, makeVerdict(h, live, cfg.verdictBy));
    done();
  }));
}

// ── Steering (MULTI-07) ──────────────────────────────────────────────────────
const meta = (live: LiveSession) => {
  const st = stateOf(live);
  return { phase: st.phase, round: st.round, iteration: st.iteration };
};

export function askCharacter(h: DebateHost, sid: string, cid: string, text: string): void {
  const live = h.live(sid);
  h.emit(sid, { type: "message", payload: { message: userMessage(h, sid, text, "steer", { targetCharacterId: cid, debate: meta(live) }) } });
  enqueue(live, (done) => {
    if (isAsleep(h, cid)) {
      asleepNote(h, sid, cid, false);
      return done();
    }
    const side = sideOf(live, cid);
    speakThen(h, sid, cid, {
      line: answerTo(text), forcedBy: "user_ask",
      message: { forcedSpeaker: true, debate: { ...meta(live), ...(side ? { side } : {}) } },
      routing: { question: text, selected: cid, forcedBy: "user_ask" },
    }, () => done());
  }, true);
}

export function interject(h: EngineHost, sid: string, text: string): void {
  const live = h.live(sid);
  h.emit(sid, { type: "message", payload: { message: userMessage(h, sid, text, "interject", { debate: meta(live) }) } });
}

export function extendRound(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  live.debate ??= {};
  live.debate.extend = true;
}

export function skipToClosing(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  live.debate ??= {};
  live.debate.skipToClosing = true;
}

export function pause(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  live.held = true;
  h.emit(sid, { type: "session.paused", payload: { reason: "user" } });
}

export function resume(h: DebateHost, sid: string): void {
  const live = h.live(sid);
  live.held = false;
  h.emit(sid, { type: "session.resumed", payload: { reason: "user" } });
  if (!live.busy && live.queue.length === 0) step(h, sid);
}

export function endDebate(h: DebateHost, sid: string, withVerdict: boolean): void {
  const live = h.live(sid);
  clearLive(live, { keepCurrentTurn: true });
  live.held = false;
  if (withVerdict) goVerdict(h, sid);
  else finish(h, sid);
}

export function pickStrongerCase(h: DebateHost, sid: string, side: Side): void {
  const live = h.live(sid);
  finish(h, sid, makeVerdict(h, live, "user", side));
}

export { setState as setDebateState };
