// Shared energy fixtures (backend/tests/fixtures/energy/cases.json): energy.ts must match them case for case.
// The Python domain/energy.py runs the same file in M2 (doc backend/04 §4).
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { Energy } from "../contract/types";
import { canTopUp, dayRoll, drain, energyState, pointsForCost, regenAt, settle, topUp, toWireEnergy, withMax } from "./energy";

interface Case { name: string; fn: string; args: Record<string, unknown>; expected: unknown }
const FILE = path.resolve(__dirname, "../../../backend/tests/fixtures/energy/cases.json");
const fixture = JSON.parse(readFileSync(FILE, "utf8")) as { tolerance: number; dayUtcOffsetMin: number; cases: Case[] };

const ms = (iso: unknown) => Date.parse(iso as string);
const opts = (a: Record<string, unknown>) => ({ estReplyPoints: a.estReplyPoints as number, frozen: a.frozen as boolean | undefined });

function run(c: Case): unknown {
  const a = c.args;
  const e = a.energy as Energy;
  switch (c.fn) {
    case "pointsForCost": return pointsForCost(a.costUsd as number, a.usdPerPoint as number);
    case "regenAt": return regenAt(e, ms(a.now));
    case "energyState": return energyState(a.current as number, a.max as number, a.estReplyPoints as number);
    case "drain": return drain(e, a.points as number, ms(a.now), opts(a));
    case "topUp": return topUp(e, a.points as number, ms(a.now), opts(a));
    case "settle": return settle(e, ms(a.now), opts(a));
    case "dayRoll": return dayRoll(e, ms(a.now), fixture.dayUtcOffsetMin);
    case "canTopUp": return canTopUp(a as never);
    case "toWireEnergy": return toWireEnergy(e);
    case "withMax": return withMax(e, a.max as number, ms(a.now), opts(a));
    default: throw new Error(`unknown fn ${c.fn}`);
  }
}

function match(actual: unknown, expected: unknown, at: string): void {
  if (typeof expected === "number") {
    expect(Math.abs((actual as number) - expected), `${at}: ${actual} vs ${expected}`).toBeLessThanOrEqual(fixture.tolerance);
  } else if (typeof expected === "string" && /^\d{4}-\d{2}-\d{2}T/.test(expected)) {
    expect(ms(actual), at).toBe(ms(expected));
  } else if (expected && typeof expected === "object") {
    for (const [k, v] of Object.entries(expected)) match((actual as Record<string, unknown>)[k], v, `${at}.${k}`);
  } else {
    expect(actual, at).toBe(expected);
  }
}

describe("energy fixtures (shared with the backend)", () => {
  it("has cases for every function", () => {
    const fns = new Set(fixture.cases.map((c) => c.fn));
    for (const f of ["pointsForCost", "regenAt", "energyState", "drain", "topUp", "settle", "dayRoll", "canTopUp", "toWireEnergy", "withMax"]) expect(fns, f).toContain(f);
  });
  for (const c of fixture.cases) {
    it(c.name, () => match(run(c), c.expected, c.fn));
  }
});
