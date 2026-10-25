// Display formatting shared by every feature (money, energy, durations, probabilities).

/** "$0.0042" for tiny values, "$0.06" for cents, "$1.20" above a dollar. */
export function formatUsd(usd: number, opts?: { approx?: boolean }): string {
  const prefix = opts?.approx ? "≈ $" : "$";
  if (usd === 0) return `${prefix}0`;
  const abs = Math.abs(usd);
  const digits = abs >= 1 ? 2 : abs >= 0.01 ? 2 : abs >= 0.001 ? 3 : 4;
  return `${prefix}${usd.toFixed(digits)}`;
}

/** "⚡ 640 / 1000" */
export const formatEnergy = (current: number, max: number): string => `⚡ ${Math.floor(current)} / ${max}`;
/** "−5 ⚡" (uses a true minus sign). */
export const formatDrain = (points: number): string => `−${points} ⚡`;

/** "8 h 38 m", "12 m", "40 s" */
export function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} m`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} m`;
}

/** Time until an ISO date, formatted ("full in 8 h 38 m"). */
export const formatUntil = (iso: string | undefined, nowMs: number): string =>
  iso ? formatDuration(Date.parse(iso) - nowMs) : "";

export type ProbBand = "HIGH" | "MED" | "LOW";
/** doc 04 §8: HIGH ≥ 0.7, MED 0.4–0.7, LOW < 0.4 */
export const probBand = (p: number): ProbBand => (p >= 0.7 ? "HIGH" : p >= 0.4 ? "MED" : "LOW");
/** "0.71 · HIGH" */
export const formatProb = (p: number): string => `${p.toFixed(2)} · ${probBand(p)}`;

/** "3.1k tok" */
export function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k tok` : `${n} tok`;
}

/** Relative date for history rows: "just now", "5 m ago", "yesterday", "28 Sep". */
export function formatRelative(iso: string, nowMs: number): string {
  const diff = nowMs - Date.parse(iso);
  if (diff < 60_000) return "just now";
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3600_000)} h ago`;
  if (diff < 2 * 86_400_000) return "yesterday";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/** Wait-time estimate (doc 06 §8): castSize × turnsPerRound × 6 s. */
export const waitEstimateMs = (castSize: number, turnsPerRound = 1): number => castSize * turnsPerRound * 6000;
