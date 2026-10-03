// Debate engine (MULTI-05..08): walks the DebateConfig phases, alternating sides, with steering inserted at turn
// boundaries. Verdict scores come from the PRNG and honour arbiter / You decide / none / panel. Owner: EE.
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

function setState(h: EngineHost, sid: string, patch: Partial<DebateState>): void {
  const live = h.live(sid);
  h.emit(sid, { type: "session.state", payload: { state: { ...stateOf(live), ...patch } } });
}

function beginPhase(h: DebateHost, sid: string, phase: DebateTurnPhase, iteration = 1): void {
  const live = h.live(sid);
  const cfg = cfgOf(live);
  const round = cfg.phases.indexOf(phase) + 1;
  const cast = live.state.session.participants.map((p) => p.characterId);
  live.debate = { order: phaseOrder(cfg, cast), idx: 0 };
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

export function start(h: DebateHost, sid: string): void {
  const live = h.live(sid);
  const cfg = cfgOf(live);
  enqueue(live, (done) => h.after(sid, h.timing.debateStartMs, () => {
    beginPhase(h, sid, cfg.phases[0] ?? "opening");
    done();
    step(h, sid);
  }));
}

/** Rebuild the cursor for a resumed/forked debate from the messages already in the current phase. */
function ensureCursor(h: DebateHost, sid: string): void {
  const live = h.live(sid);
  if (live.debate) return;
  const st = stateOf(live);
  const cfg = cfgOf(live);
  const cast = live.state.session.participants.map((p) => p.characterId);
  const spoken = live.state.order.map((id) => live.state.messages[id])
    .filter((m): m is Message => !!m && m.author.type === "character" && m.kind === "chat" && m.debate?.phase === st.phase && m.debate.iteration === st.iteration && !m.forcedSpeaker).length;
  live.debate = { order: phaseOrder(cfg, cast), idx: spoken };
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
    ensureCursor(h, sid);
    const cur = live.debate!;
    const cfg = cfgOf(live);
    if (cur.skipToClosing && stateOf(live).phase !== "closing") {
      beginPhase(h, sid, "closing");
      live.debate!.skipToClosing = false;
      done();
      return scheduleNext(h, sid);
    }
    if (cur.idx >= cur.order.length) {
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
    const cid = cur.order[cur.idx++];
    if (isAsleep(h, cid)) {
      asleepNote(h, sid, cid, true);
      done();
      return scheduleNext(h, sid, 200);
    }
    const now = stateOf(live);
    const side = sideOf(live, cid);
    speakThen(h, sid, cid, {
      line: debateLine(now.phase as DebateTurnPhase, cfg.motion, side, live.turn + cur.idx),
      forcedBy: "round_order",
      message: { debate: { phase: now.phase, round: now.round, iteration: now.iteration, ...(side ? { side } : {}) } },
    }, () => {
      done();
      const after = live.debate!;
      const upcoming = after.idx < after.order.length ? after.order[after.idx] : undefined;
      if (upcoming) h.emit(sid, { type: "turn.next", payload: { nextSpeakerId: upcoming } });
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
    ? verdict.strongerCase ? `STRONGER CASE: ${verdict.strongerCase === "prop" ? "PROPOSITION" : "OPPOSITION"}` : verdict.decidedBy === "none" ? "SUMMARY" : "TOO CLOSE TO CALL"
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
  if (cfg.verdictBy === "user") return; // waits for pickStrongerCase
  enqueue(live, (done) => h.after(sid, 1800, () => {
    h.charge(sid, "decision", chatCostUsd({ tokensIn: 6200, tokensCached: 2400, tokensOut: 420 }, h.pricing.decision, h.period()));
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
  if (live.debate) live.debate.extend = true;
}

export function skipToClosing(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  live.debate ??= { order: [], idx: 0 };
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
