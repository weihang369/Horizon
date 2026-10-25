// The System 1 fixture holds one row per question a turn can ask, and none for evaluation-only judges
// (demo-data "The System 1 fixture is generated and checked"; persona-context D26), and none for the listener
// reaction (turn-plan-emotion D18: it has no System 1 row).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { BANK_DIR, system1Fixture } from "./system1";

describe("system1Fixture", () => {
  it("skips eval_judge entries and the reaction, and keeps every turn question", () => {
    const entries = readdirSync(BANK_DIR).filter((f) => f.endsWith(".json") && !f.startsWith("_") && f !== "questions.lock.json")
      .map((f) => JSON.parse(readFileSync(path.join(BANK_DIR, f), "utf8")) as { id: string; purpose: string });
    const judges = entries.filter((e) => e.purpose === "eval_judge").map((e) => e.id);
    expect(judges.length).toBeGreaterThanOrEqual(13);
    const rows = Object.keys(system1Fixture().rows);
    expect(rows).toEqual(entries.filter((e) => e.purpose !== "eval_judge" && e.purpose !== "reaction").map((e) => e.id).sort());
    for (const j of judges) expect(rows).not.toContain(j);
    expect(entries.map((e) => e.id)).toContain("reaction");
    expect(rows).not.toContain("reaction");
    expect(rows).toEqual(expect.arrayContaining(["emotion_reply", "emotion_greeting", "face_check"]));
    // M12 (rag D20): the retrieval rows
    expect(rows).toEqual(expect.arrayContaining(["docs", "standalone", "english", "passage", "passage_set"]));
    expect(system1Fixture().rows.face_check).toEqual({ purpose: "face_check", id: "face_check", version: 1,
      label: "face and words agree?", p: 0.72, compared: [], result: "shown_only" });
  });
});
