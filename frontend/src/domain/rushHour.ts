// DeepSeek peak pricing ("rush hour", ENG-06): Mon–Fri 09:00–12:00 and 14:00–18:00 Malaysia time (UTC+8).
// Pure functions over epoch milliseconds, so tests and the mock clock can drive them.

export type PricePeriod = "peak" | "off_peak";

const MYT_OFFSET_MS = 8 * 3600_000;
/** Peak windows in MYT minutes-of-day: [start, end). */
const WINDOWS: [number, number][] = [[9 * 60, 12 * 60], [14 * 60, 18 * 60]];

function mytParts(epochMs: number): { day: number; minutes: number; dayStartMyt: number } {
  const shifted = epochMs + MYT_OFFSET_MS;
  const d = new Date(shifted);
  const day = d.getUTCDay(); // 0 = Sunday, in MYT
  const minutes = d.getUTCHours() * 60 + d.getUTCMinutes() + d.getUTCSeconds() / 60 + d.getUTCMilliseconds() / 60000;
  const dayStartMyt = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - MYT_OFFSET_MS;
  return { day, minutes, dayStartMyt };
}

const isWeekday = (day: number) => day >= 1 && day <= 5;

export function isPeak(epochMs: number): boolean {
  const { day, minutes } = mytParts(epochMs);
  if (!isWeekday(day)) return false;
  return WINDOWS.some(([a, b]) => minutes >= a && minutes < b);
}

export function pricePeriod(epochMs: number): PricePeriod {
  return isPeak(epochMs) ? "peak" : "off_peak";
}

/** Epoch ms of the next peak/off-peak boundary strictly after `epochMs`. */
export function nextPeriodChange(epochMs: number): number {
  const { dayStartMyt } = mytParts(epochMs);
  for (let dayOffset = 0; dayOffset < 8; dayOffset++) {
    const start = dayStartMyt + dayOffset * 86_400_000;
    const { day } = mytParts(start + 3600_000);
    if (!isWeekday(day)) continue;
    for (const [a, b] of WINDOWS) {
      for (const m of [a, b]) {
        const t = start + m * 60_000;
        if (t > epochMs) return t;
      }
    }
  }
  return epochMs + 86_400_000; // unreachable in practice
}

export interface RushHourInfo { peak: boolean; period: PricePeriod; nextChangeAt: string }

export function rushHourInfo(epochMs: number, override?: PricePeriod | null): RushHourInfo {
  const period = override ?? pricePeriod(epochMs);
  return { peak: period === "peak", period, nextChangeAt: new Date(nextPeriodChange(epochMs)).toISOString() };
}

/** Energy/price multiplier for the period (peak = 2×, D-41). */
export const periodMultiplier = (p: PricePeriod): number => (p === "peak" ? 2 : 1);
