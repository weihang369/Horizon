// Rush hour (ENG-06): Mon–Fri 09:00–12:00 and 14:00–18:00 MYT (UTC+8). Owner: EE.
import { describe, expect, it } from "vitest";
import { isPeak, nextPeriodChange, periodMultiplier, rushHourInfo } from "./rushHour";

// 2026-10-01 is a Thursday.
const myt = (iso: string) => Date.parse(`${iso}+08:00`);

describe("rushHour", () => {
  it("peak windows on weekdays only", () => {
    expect(isPeak(myt("2026-10-01T08:59:59"))).toBe(false);
    expect(isPeak(myt("2026-10-01T09:00:00"))).toBe(true);
    expect(isPeak(myt("2026-10-01T11:59:00"))).toBe(true);
    expect(isPeak(myt("2026-10-01T12:00:00"))).toBe(false);
    expect(isPeak(myt("2026-10-01T14:30:00"))).toBe(true);
    expect(isPeak(myt("2026-10-01T18:00:00"))).toBe(false);
    expect(isPeak(myt("2026-10-03T10:00:00"))).toBe(false); // Saturday
  });

  it("next change is the next window edge, skipping weekends", () => {
    expect(nextPeriodChange(myt("2026-10-01T08:00:00"))).toBe(myt("2026-10-01T09:00:00"));
    expect(nextPeriodChange(myt("2026-10-01T10:00:00"))).toBe(myt("2026-10-01T12:00:00"));
    expect(nextPeriodChange(myt("2026-10-01T12:30:00"))).toBe(myt("2026-10-01T14:00:00"));
    expect(nextPeriodChange(myt("2026-10-02T19:00:00"))).toBe(myt("2026-10-05T09:00:00")); // Fri evening → Mon
  });

  it("override and multiplier", () => {
    expect(rushHourInfo(myt("2026-10-03T10:00:00"), "peak").peak).toBe(true);
    expect(periodMultiplier("peak")).toBe(2);
    expect(periodMultiplier("off_peak")).toBe(1);
  });
});
