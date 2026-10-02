// Energy + cost maths (ENG-01..06, doc 05 §8). Owner: EE.
import { describe, expect, it } from "vitest";
import { PRICING } from "../mock/pricing.config";
import { chatCostUsd, chatEnergy } from "./cost";
import { drain, energyBand, energyState, liveEnergy, makeEnergy, pointsForCost, regenAt, topUp, withMax } from "./energy";

const H = 3600_000;
const T0 = Date.parse("2026-10-01T00:00:00Z");

describe("energy", () => {
  it("doc 05 §8: 2,000 uncached + 7,800 cached + 168 out ≈ $0.00042 → 5 ⚡", () => {
    const usage = { tokensIn: 9800, tokensCached: 7800, tokensOut: 168 };
    expect(chatCostUsd(usage, PRICING.chat, "off_peak")).toBeCloseTo(0.000424, 6);
    expect(chatEnergy(usage, PRICING.chat, "off_peak")).toBe(5);
    expect(chatEnergy(usage, PRICING.chat, "peak")).toBe(9); // rush hour = 2× cost
  });

  it("drain rounds up and tolerates float noise", () => {
    expect(pointsForCost(0.0005)).toBe(5);
    expect(pointsForCost(0.00041)).toBe(5);
    expect(pointsForCost(0)).toBe(0);
  });

  it("regenerates max/24 per hour lazily, never above max", () => {
    const e = makeEnergy(0, 1000, new Date(T0).toISOString());
    expect(regenAt(e, T0 + 12 * H)).toBeCloseTo(500);
    expect(regenAt(e, T0 + 30 * H)).toBe(1000);
    expect(liveEnergy(e, T0 + 6 * H).current).toBe(250);
  });

  it("demo mode freezes regen (ENG-07)", () => {
    const e = makeEnergy(180, 1000, new Date(T0).toISOString());
    expect(liveEnergy(e, T0 + 10 * H, { frozen: true }).current).toBe(180);
  });

  it("states: exhausted below one reply, tired below 20 %", () => {
    expect(energyState(0, 1000)).toBe("exhausted");
    expect(energyState(3, 1000)).toBe("exhausted");
    expect(energyState(180, 1000)).toBe("tired");
    expect(energyState(200, 1000)).toBe("active");
    expect(energyState(7, 1000, 8)).toBe("exhausted"); // peak estimate
    expect(energyBand(0.39)).toBe("amber");
    expect(energyBand(0.19)).toBe("red");
  });

  it("drain, top-up (may exceed max) and max change", () => {
    const e = makeEnergy(747, 1000, new Date(T0).toISOString());
    const d = drain(e, 5, T0);
    expect(d.current).toBe(742);
    expect(d.spentToday).toBe(5);
    expect(topUp(makeEnergy(900, 1000, new Date(T0).toISOString()), 500, T0).current).toBe(1400);
    const m = withMax(e, 2000, T0);
    expect(m.max).toBe(2000);
    expect(m.regenPerHour).toBeCloseTo(2000 / 24);
  });
});
