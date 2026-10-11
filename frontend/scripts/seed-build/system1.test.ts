// The System 1 fixture holds one row per question a turn can ask, and none for evaluation-only judges
// (demo-data "The System 1 fixture is generated and checked"; persona-context D26).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { BANK_DIR, system1Fixture } from "./system1";

describe("system1Fixture", () => {
  it("skips eval_judge entries and keeps every turn question", () => {
    const entries = readdirSync(BANK_DIR).filter((f) => f.endsWith(".json") && !f.startsWith("_") && f !== "questions.lock.json")
      .map((f) => JSON.parse(readFileSync(path.join(BANK_DIR, f), "utf8")) as { id: string; purpose: string });
    const judges = entries.filter((e) => e.purpose === "eval_judge").map((e) => e.id);
    expect(judges.length).toBeGreaterThanOrEqual(13);
    const rows = Object.keys(system1Fixture().rows);
    expect(rows).toEqual(entries.filter((e) => e.purpose !== "eval_judge").map((e) => e.id).sort());
    for (const j of judges) expect(rows).not.toContain(j);
  });
});
