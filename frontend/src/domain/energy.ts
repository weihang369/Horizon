// Character energy (⚡), doc 05 `Energy` + ENG-01..06. The same formulas as the backend:
//   regen (lazy):  current = min(max, current + regenPerHour × hoursSince(asOf))
//   drain:         ceil(costUsd / usdPerPoint)
//   state:         exhausted if current < estimated reply cost; tired if < 20 % of max
import type { Energy, EnergyState } from "../contract/types";

export const USD_PER_POINT = 0.0001;
export const TIRED_PCT = 0.2;
export const AMBER_PCT = 0.4;
/** Estimated reply cost in ⚡ (NFR-34: ≈ 4 off-peak, 8 at peak). */
export const EST_REPLY_POINTS = { off_peak: 4, peak: 8 } as const;

export function pointsForCost(costUsd: number, usdPerPoint = USD_PER_POINT): number {
  if (costUsd <= 0) return 0;
  // Tolerate float noise (0.0005 / 0.0001 = 5.000000001).
  return Math.ceil(costUsd / usdPerPoint - 1e-9);
}

export function energyState(current: number, max: number, estReplyPoints: number = EST_REPLY_POINTS.off_peak): EnergyState {
  if (current < estReplyPoints) return "exhausted";
  if (current < max * TIRED_PCT) return "tired";
  return "active";
}

/** Lazily regenerated value at `nowMs` (never above max by regeneration; top-ups may exceed max). */
export function regenAt(e: Pick<Energy, "current" | "max" | "asOf" | "regenPerHour">, nowMs: number): number {
  const since = Math.max(0, nowMs - Date.parse(e.asOf)) / 3600_000;
  if (e.current >= e.max) return e.current;
  return Math.min(e.max, e.current + e.regenPerHour * since);
}

/** When the bar will be full again (undefined if already full or no regen). */
export function fullAt(current: number, max: number, regenPerHour: number, nowMs: number): string | undefined {
  if (current >= max || regenPerHour <= 0) return undefined;
  return new Date(nowMs + ((max - current) / regenPerHour) * 3600_000).toISOString();
}

export interface LiveEnergy {
  current: number; max: number; state: EnergyState; fullAt?: string; pct: number; regenerating: boolean;
}

/** Energy snapshot at `nowMs`. `frozen` = demo mode (ENG-07: nothing regenerates live). */
export function liveEnergy(e: Energy, nowMs: number, opts?: { frozen?: boolean; estReplyPoints?: number }): LiveEnergy {
  const current = opts?.frozen ? e.current : regenAt(e, nowMs);
  const state = energyState(Math.floor(current), e.max, opts?.estReplyPoints);
  return {
    current: Math.floor(current),
    max: e.max,
    state,
    fullAt: opts?.frozen ? e.fullAt : fullAt(current, e.max, e.regenPerHour, nowMs),
    pct: e.max > 0 ? Math.min(1, current / e.max) : 0,
    regenerating: !opts?.frozen && current < e.max && e.regenPerHour > 0,
  };
}

/** Materialise regen into a new Energy record at `nowMs`. */
export function settle(e: Energy, nowMs: number, opts?: { frozen?: boolean; estReplyPoints?: number }): Energy {
  const live = liveEnergy(e, nowMs, opts);
  return { ...e, current: live.current, asOf: new Date(nowMs).toISOString(), state: live.state, fullAt: live.fullAt };
}

/** Drain `points` (a character's own reply, D-42). */
export function drain(e: Energy, points: number, nowMs: number, opts?: { frozen?: boolean; estReplyPoints?: number }): Energy {
  const s = settle(e, nowMs, opts);
  const current = Math.max(0, s.current - points);
  return {
    ...s,
    current,
    state: energyState(current, e.max, opts?.estReplyPoints),
    fullAt: fullAt(current, e.max, e.regenPerHour, nowMs),
    spentToday: e.spentToday + points,
  };
}

/** Top-up (ENG-05): may exceed max for today. */
export function topUp(e: Energy, points: number, nowMs: number, opts?: { estReplyPoints?: number }): Energy {
  const s = settle(e, nowMs, opts);
  const current = s.current + points;
  return { ...s, current, state: energyState(current, e.max, opts?.estReplyPoints), fullAt: fullAt(current, e.max, e.regenPerHour, nowMs) };
}

export function withMax(e: Energy, max: number, nowMs: number): Energy {
  const s = settle(e, nowMs);
  return { ...s, max, regenPerHour: max / 24, state: energyState(s.current, max), fullAt: fullAt(s.current, max, max / 24, nowMs) };
}

export function makeEnergy(current: number, max: number, asOf: string, spentToday = 0): Energy {
  const now = Date.parse(asOf);
  return {
    max, current, asOf, regenPerHour: max / 24,
    state: energyState(current, max), fullAt: fullAt(current, max, max / 24, now), spentToday,
  };
}

/** Bar colour band (doc 04 §6.1): primary ≥ 40 %, amber < 40 %, red < 20 %. */
export function energyBand(pct: number): "primary" | "amber" | "red" {
  if (pct < TIRED_PCT) return "red";
  if (pct < AMBER_PCT) return "amber";
  return "primary";
}
