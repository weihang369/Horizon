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

/** MULTI-05: with 5 debaters the default turn length is Short, else Medium (an explicit pick always wins). */
export function defaultTurnLength(castSize: number): "short" | "medium" {
  return castSize >= 5 ? "short" : "medium";
}

/** MULTI-05: Panel offers only Arbiter summary / None; a "You decide" pick falls back to the arbiter. */
export function verdictOptionsFor(format: "two_sided" | "panel"): ("arbiter" | "user" | "none")[] {
  return format === "panel" ? ["arbiter", "none"] : ["arbiter", "user", "none"];
}

export interface SetupDraft {
  motion: string;
  format: "two_sided" | "panel";
  cast: string[];
  sides: Record<string, Side>;
  premise: string;
}

/**
 * Step 3 gate. Debate (MULTI-05 AC1): a motion ≤ 200 chars and, two-sided, ≥ 1 debater per side.
 * Watch (MULTI-09): a premise ≤ 300 chars. Group has nothing required.
 */
export function setupConfigOk(mode: "group" | "debate" | "watch" | undefined, d: SetupDraft): boolean {
  if (mode === "group") return true;
  if (mode === "debate") {
    const m = d.motion.trim();
    if (!m || d.motion.length > 200) return false;
    if (d.format === "panel") return true;
    const prop = d.cast.filter((id) => d.sides[id] === "prop").length;
    const opp = d.cast.filter((id) => d.sides[id] === "opp").length;
    return prop >= 1 && opp >= 1;
  }
  if (mode === "watch") return d.premise.trim().length > 0 && d.premise.length <= 300;
  return false;
}
