// Character energy (⚡), doc 05 `Energy` + ENG-01..07, doc backend/04 §4. The SAME algorithm as the backend's
// domain/energy.py; both are pinned by backend/tests/fixtures/energy/cases.json.
//   regen (lazy):  current = min(max, current + regenPerHour × hoursSince(asOf))   (never lowers a top-up above max)
//   drain:         ceil(costUsd / usdPerPoint − 1e-9)
//   state:         exhausted if current < estReplyPoints[period] (D-78: one threshold); tired if < 20 % of max
//   storage:       current / spentToday are REAL; only the wire floors them (toWireEnergy)
//   day roll:      spentToday resets at local midnight (MYT, UTC+8) the first time energy is settled on a new day
import type { Energy, EnergyState } from "../contract/types";

export const USD_PER_POINT = 0.0001;
export const TIRED_PCT = 0.2;
export const AMBER_PCT = 0.4;
/** Estimated reply cost in ⚡ (NFR-34: ≈ 4 off-peak, 8 at peak). Exposed as AppSettings.energy.estReplyPoints (rev 1.3). */
export const EST_REPLY_POINTS = { off_peak: 4, peak: 8 } as const;
/** Energy day boundary: local midnight in HORIZON_TZ (MYT by default). */
export const DAY_UTC_OFFSET_MIN = 8 * 60;

export interface EnergyOpts { frozen?: boolean; estReplyPoints?: number }

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

/** Local calendar day (YYYY-MM-DD) of an instant, for the energy day boundary. */
export function energyDay(epochMs: number, utcOffsetMin = DAY_UTC_OFFSET_MIN): string {
  return new Date(epochMs + utcOffsetMin * 60_000).toISOString().slice(0, 10);
}

/** Reset `spentToday` when `nowMs` falls on a later local day than `asOf`. */
export function dayRoll(e: Energy, nowMs: number, utcOffsetMin = DAY_UTC_OFFSET_MIN): Energy {
  if (energyDay(Date.parse(e.asOf), utcOffsetMin) === energyDay(nowMs, utcOffsetMin)) return e;
  return { ...e, spentToday: 0 };
}

export interface LiveEnergy {
  current: number; max: number; state: EnergyState; fullAt?: string; pct: number; regenerating: boolean;
}

/** Display snapshot at `nowMs` (floored for the UI). `frozen` = demo mode (ENG-07: nothing regenerates live). */
export function liveEnergy(e: Energy, nowMs: number, opts?: EnergyOpts): LiveEnergy {
  const current = opts?.frozen ? e.current : regenAt(e, nowMs);
  return {
    current: Math.floor(current),
    max: e.max,
    state: energyState(current, e.max, opts?.estReplyPoints),
    fullAt: opts?.frozen ? e.fullAt : fullAt(current, e.max, e.regenPerHour, nowMs),
    pct: e.max > 0 ? Math.min(1, current / e.max) : 0,
    regenerating: !opts?.frozen && current < e.max && e.regenPerHour > 0,
  };
}

/** Materialise regen (and the day roll) into a new Energy record at `nowMs`. Keeps the REAL value. */
export function settle(e: Energy, nowMs: number, opts?: EnergyOpts): Energy {
  if (opts?.frozen) return { ...e, state: energyState(e.current, e.max, opts.estReplyPoints) };
  const rolled = dayRoll(e, nowMs);
  const current = regenAt(rolled, nowMs);
  return {
    ...rolled, current, asOf: new Date(nowMs).toISOString(),
    state: energyState(current, e.max, opts?.estReplyPoints), fullAt: fullAt(current, e.max, e.regenPerHour, nowMs),
  };
}

/** Drain `points` (a character's own reply, D-42). Overdraft clamps at 0; the reply still finishes. */
export function drain(e: Energy, points: number, nowMs: number, opts?: EnergyOpts): Energy {
  const s = settle(e, nowMs, opts);
  const current = Math.max(0, s.current - points);
  return {
    ...s,
    current,
    state: energyState(current, e.max, opts?.estReplyPoints),
    fullAt: fullAt(current, e.max, e.regenPerHour, nowMs),
    spentToday: s.spentToday + points,
  };
}

/** Top-up (ENG-05): may exceed max for today. Gate it with `canTopUp` first (D-76). */
export function topUp(e: Energy, points: number, nowMs: number, opts?: EnergyOpts): Energy {
  const s = settle(e, nowMs, opts);
  const current = s.current + points;
  return { ...s, current, state: energyState(current, e.max, opts?.estReplyPoints), fullAt: fullAt(current, e.max, e.regenPerHour, nowMs) };
}

export interface TopUpGateInput {
  spentTodayUsd: number;
  /** Sum of today's earlier top-ups, in ⚡. */
  todayTopUpPoints: number;
  points: number;
  usdPerPoint: number;
  dailyCapUsd: number;
}

/** D-76: a top-up is allowed while spentToday + (todayTopUpPoints + points) × usdPerPoint ≤ dailyCap. */
export function canTopUp(g: TopUpGateInput): boolean {
  return g.spentTodayUsd + (g.todayTopUpPoints + g.points) * g.usdPerPoint <= g.dailyCapUsd + 1e-9;
}

export function withMax(e: Energy, max: number, nowMs: number, opts?: EnergyOpts): Energy {
  const s = settle(e, nowMs, opts);
  return {
    ...s, max, regenPerHour: max / 24,
    state: energyState(s.current, max, opts?.estReplyPoints), fullAt: fullAt(s.current, max, max / 24, nowMs),
  };
}

export function makeEnergy(current: number, max: number, asOf: string, spentToday = 0, opts?: EnergyOpts): Energy {
  const now = Date.parse(asOf);
  return {
    max, current, asOf, regenPerHour: max / 24,
    state: energyState(current, max, opts?.estReplyPoints), fullAt: fullAt(current, max, max / 24, now), spentToday,
  };
}

/** The wire form (doc backend/04 §4): `current` and `spentToday` floored to integers; everything else as stored. */
export function toWireEnergy(e: Energy): Energy {
  return { ...e, current: Math.floor(e.current), spentToday: Math.floor(e.spentToday) };
}

/** Bar colour band (doc 04 §6.1): primary ≥ 40 %, amber < 40 %, red < 20 %. */
export function energyBand(pct: number): "primary" | "amber" | "red" {
  if (pct < TIRED_PCT) return "red";
  if (pct < AMBER_PCT) return "amber";
  return "primary";
}
