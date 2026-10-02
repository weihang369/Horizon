// S08 pure helpers (Builder D): cast limits, side auto-assign, round-time estimate, motion suggestions. Tested.
import type { Side } from "../../contract/types";

/** 2–4 characters, a 5th seat under "Advanced" (MULTI-01 AC2). */
export function castLimits(advanced: boolean): { min: number; max: number } {
  return { min: 2, max: advanced ? 5 : 4 };
}

/**
 * Keep existing side picks for characters still in the cast; new picks go to the smaller side (ties → PROP).
 * Uneven sides are allowed (MULTI-05).
 */
export function autoAssign(cast: string[], current: Record<string, Side>): Record<string, Side> {
  const out: Record<string, Side> = {};
  let prop = 0;
  let opp = 0;
  for (const id of cast) {
    const s = current[id];
    if (s) {
      out[id] = s;
      if (s === "prop") prop++;
      else opp++;
    }
  }
  for (const id of cast) {
    if (out[id]) continue;
    const side: Side = prop <= opp ? "prop" : "opp";
    out[id] = side;
    if (side === "prop") prop++;
    else opp++;
  }
  return out;
}

/** Rough seconds for one round (every cast member speaks once) — the "wait-time estimate". */
export function estimateRoundSec(castSize: number, mode: "group" | "debate" | "watch"): number {
  const perTurn = mode === "debate" ? 7 : mode === "watch" ? 5 : 6;
  return Math.round(castSize * perTurn);
}

const MOTIONS = [
  "This house would adopt a nationwide four-day work week.",
  "This house would ban smartphones in schools.",
  "This house would make voting compulsory.",
  "This house believes remote work does more harm than good.",
  "This house would tax sugary drinks.",
  "This house would replace exams with continuous assessment.",
];

/** Three motion suggestions (MULTI-05 "Suggest motions", mock: deterministic per world). */
export function suggestMotions(seed: string | undefined): string[] {
  let h = 0;
  for (const ch of seed ?? "horizon") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const start = h % MOTIONS.length;
  return [0, 2, 4].map((k) => MOTIONS[(start + k) % MOTIONS.length]);
}
