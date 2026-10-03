// Watch engine (MULTI-09..11): speakers alternate at the configured pace; a director's note switches the bank
// category for the next turns; Step in pauses and lets up to 2 reply; the turn limit pauses with turn_cap. Owner: EE.
import type { StreamEvent, WatchConfig, WatchState } from "../../contract/types";
import { chatCostUsd } from "../../domain/cost";
import { pickSceneLine } from "../banks";
import { runSpeakers } from "./group";
import type { EngineHost, LiveSession } from "./host";
import { asleepNote, clearLive, enqueue, isAsleep, speakThen, systemNote, userMessage } from "./host";

const cfgOf = (live: LiveSession) => live.state.session.config as WatchConfig;
const stateOf = (live: LiveSession): WatchState =>
  (live.state.session.state as WatchState | null) ?? { status: "paused", turnsTaken: 0, turnLimit: cfgOf(live).maxTurns };

function watchState(h: EngineHost, sid: string, patch: Partial<WatchState>): StreamEvent[] {
  const live = h.live(sid);
  const st = { ...stateOf(live), ...patch };
  return [
    { type: "watch.state", payload: { status: st.status, paceMs: cfgOf(live).paceMs, turnsTaken: st.turnsTaken, turnLimit: st.turnLimit } },
    { type: "session.state", payload: { state: st } },
  ];
}

export function start(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  const cfg = cfgOf(live);
  enqueue(live, (done) => h.after(sid, h.timing.watchStartMs, () => {
    h.emit(sid,
      { type: "message", payload: { message: systemNote(h, sid, cfg.premise, "direction", { type: "system" }) } },
      ...watchState(h, sid, { status: "playing" }),
    );
    done();
    turn(h, sid);
  }));
}

function pickSpeaker(h: EngineHost, live: LiveSession): string | null {
  const s = live.state.session;
  if (live.nudge) {
    const n = live.nudge;
    live.nudge = undefined;
    return n;
  }
  const cast = s.participants.filter((p) => !p.mutedByUser).map((p) => p.characterId);
  if (!cast.length) return null;
  const cfg = cfgOf(live);
  if (live.watchIdx === undefined) {
    const open = cfg.openingSpeaker !== "auto" ? cast.indexOf(cfg.openingSpeaker) : 0;
    live.watchIdx = Math.max(0, open) + stateOf(live).turnsTaken;
  }
  for (let i = 0; i < cast.length; i++) {
    const cid = cast[live.watchIdx++ % cast.length];
    if (!isAsleep(h, cid)) return cid;
  }
  return null;
}

/** One scene turn. `manual` = Step (runs while paused, doesn't chain). */
export function turn(h: EngineHost, sid: string, manual = false): void {
  const live = h.live(sid);
  enqueue(live, (done) => {
    const st = stateOf(live);
    if (!manual && (live.held || st.status !== "playing")) return done();
    if (st.turnsTaken >= st.turnLimit) {
      h.emit(sid, ...watchState(h, sid, { status: "ended", nextSpeakerId: undefined }), { type: "session.paused", payload: { reason: "turn_cap" } });
      return done();
    }
    const cid = pickSpeaker(h, live);
    if (!cid) {
      const sleeper = live.state.session.participants[0]?.characterId;
      if (sleeper) asleepNote(h, sid, sleeper, false);
      h.emit(sid,
        { type: "message", payload: { message: systemNote(h, sid, "Everyone's asleep. Top someone up to continue the scene.") } },
        ...watchState(h, sid, { status: "paused" }),
        { type: "session.paused", payload: { reason: "user" } },
      );
      live.held = true;
      return done();
    }
    const c = h.db.characters[cid]!;
    const rng = h.rng(`${sid}:scene:${live.turn}`);
    const note = live.direction && live.direction.turnsLeft > 0 ? live.direction.note : undefined;
    if (live.direction) live.direction.turnsLeft -= 1;
    const line = pickSceneLine(c, cfgOf(live).premise, rng, live.recent, note);
    speakThen(h, sid, cid, { line }, () => {
      const turnsTaken = stateOf(live).turnsTaken + 1;
      const ended = turnsTaken >= stateOf(live).turnLimit;
      h.emit(sid, ...watchState(h, sid, { turnsTaken, status: ended ? "ended" : stateOf(live).status }));
      if (ended) h.emit(sid, { type: "session.paused", payload: { reason: "turn_cap" } });
      done();
      if (!ended && !manual && !live.held) h.after(sid, cfgOf(live).paceMs, () => turn(h, sid));
    });
  });
}

export function play(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  live.held = false;
  h.emit(sid, ...watchState(h, sid, { status: "playing" }), { type: "session.resumed", payload: { reason: "user" } });
  if (!live.busy && !live.queue.length) turn(h, sid);
}

export function pause(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  live.held = true;
  h.emit(sid, ...watchState(h, sid, { status: "paused" }), { type: "session.paused", payload: { reason: "user" } });
}

export function stepOnce(h: EngineHost, sid: string): void {
  turn(h, sid, true);
}

export function setPace(h: EngineHost, sid: string, paceMs: WatchConfig["paceMs"]): void {
  const live = h.live(sid);
  live.state = { ...live.state, session: { ...live.state.session, config: { ...cfgOf(live), paceMs } } };
  h.emit(sid, ...watchState(h, sid, {}));
}

export function direct(h: EngineHost, sid: string, text: string): void {
  const live = h.live(sid);
  live.direction = { note: text, turnsLeft: 2 };
  h.emit(sid, { type: "message", payload: { message: userMessage(h, sid, text, "direction") } });
}

export function stepIn(h: EngineHost, sid: string, text: string): void {
  const live = h.live(sid);
  if (!live.held) pause(h, sid);
  h.emit(sid, { type: "message", payload: { message: userMessage(h, sid, text) } });
  const cast = live.state.session.participants.filter((p) => !p.mutedByUser && !isAsleep(h, p.characterId)).map((p) => p.characterId);
  runSpeakers(h, sid, h.rng(`${sid}:stepin:${live.turn}`).shuffle(cast).slice(0, 2), text);
}

export function extendWatch(h: EngineHost, sid: string, turns = 10): void {
  const live = h.live(sid);
  const st = stateOf(live);
  live.held = false;
  h.emit(sid, ...watchState(h, sid, { turnLimit: st.turnLimit + turns, status: "playing" }), { type: "session.resumed", payload: { reason: "extend" } });
  turn(h, sid);
}

export function summarise(h: EngineHost, sid: string): void {
  const live = h.live(sid);
  clearLive(live, { keepCurrentTurn: true });
  const names = live.state.session.participants.map((p) => h.db.characters[p.characterId]?.profile.name.split(" ")[0]).filter(Boolean);
  enqueue(live, (done) => h.after(sid, 1200, () => {
    h.charge(sid, "summary", chatCostUsd({ tokensIn: 5200, tokensCached: 3000, tokensOut: 260 }, h.pricing.chat, h.period()));
    h.emit(sid, { type: "message", payload: { message: systemNote(h, sid, `Episode summary: ${names.join(", ")} spent the scene on "${cfgOf(live).premise}". ${stateOf(live).turnsTaken} turns, no one fully got their way, and everyone will remember it differently.`, "summary") } });
    done();
  }));
}

