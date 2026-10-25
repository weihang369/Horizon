// Builder D: pure stage maths, verdict copy and setup helpers.
import { describe, expect, it } from "vitest";
import type { Message, Verdict } from "../../contract/types";
import {
  activeSpeakerId, debateColumns, frontFirst, lastSpeakerId, latestReactions, railSteps, recentSpeakerIn, roundBannerLabel,
  rubricRows, splitWings, verdictHeadline,
} from "./shared";
import { autoAssign, castLimits, defaultTurnLength, estimateRoundSec, setupConfigOk, suggestMotions, verdictOptionsFor } from "./setupLogic";

const msg = (id: string, cid?: string, extra: Partial<Message> = {}): Message => ({
  id, sessionId: "ses_x", seq: 1, author: cid ? { type: "character", characterId: cid } : { type: "user" }, kind: "chat",
  content: "", status: "complete", createdAt: "2026-10-01T00:00:00Z", ...extra,
});

describe("stage focus", () => {
  it("streaming speaker wins over thinking", () => {
    const messages = { m1: msg("m1", "a") };
    expect(activeSpeakerId({ streamingId: "m1", thinkingId: "b", messages })).toBe("a");
    expect(activeSpeakerId({ streamingId: undefined, thinkingId: "b", messages })).toBe("b");
  });
  it("front-first keeps cast order for the rest", () => {
    expect(frontFirst(["a", "b", "c"], "c")).toEqual(["c", "a", "b"]);
    expect(frontFirst(["a", "b"], "z")).toEqual(["a", "b"]);
  });
  it("recent / last speaker skip user lines", () => {
    const list = [msg("1", "a"), msg("2", "b"), msg("3")];
    expect(lastSpeakerId(list)).toBe("b");
    expect(recentSpeakerIn(["a"], list)).toBe("a");
  });
  it("latest reactions come from the newest message that has any", () => {
    const r = latestReactions([
      msg("1", "a", { reactions: [{ characterId: "b", emotion: "sad", at: "t1" }] }),
      msg("2", "b", { reactions: [{ characterId: "a", emotion: "happy", at: "t2" }] }),
    ]);
    expect(Object.keys(r)).toEqual(["a"]);
    expect(r.a.emotion).toBe("happy");
  });
});

describe("layouts", () => {
  it("wings: 2 → 1/1, 3 → 2/1, 5 → 3/2", () => {
    expect(splitWings(["a", "b"])).toEqual({ left: ["a"], right: ["b"] });
    expect(splitWings(["a", "b", "c"])).toEqual({ left: ["a", "c"], right: ["b"] });
    expect(splitWings(["a", "b", "c", "d", "e"])).toEqual({ left: ["a", "c", "e"], right: ["b", "d"] });
  });
  it("debate columns by side; panel alternates", () => {
    const ps = [{ characterId: "a", side: "prop" as const }, { characterId: "b", side: "prop" as const }, { characterId: "c", side: "opp" as const }];
    expect(debateColumns(ps, null)).toEqual({ prop: ["a", "b"], opp: ["c"] });
    const panel = ps.map((p) => ({ ...p, side: null }));
    expect(debateColumns(panel, null)).toEqual({ prop: ["a", "c"], opp: ["b"] });
  });
});

describe("debate phases", () => {
  it("banner labels", () => {
    expect(roundBannerLabel({ phase: "rebuttal", round: 2, iteration: 1 })).toBe("ROUND 2: REBUTTAL");
    expect(roundBannerLabel({ phase: "rebuttal", round: 2, iteration: 2 })).toBe("ROUND 2: REBUTTAL ×2");
    expect(roundBannerLabel({ phase: "verdict", round: 4, iteration: 1 })).toBe("VERDICT");
  });
  it("rail marks done / current / todo, ended = all done", () => {
    const st = railSteps(["opening", "rebuttal", "closing"], "rebuttal").map((x) => x.state);
    expect(st).toEqual(["done", "current", "todo", "todo"]);
    expect(railSteps(["opening", "closing"], "ended").every((x) => x.state === "done")).toBe(true);
    expect(railSteps(["opening", "closing"], "setup").every((x) => x.state === "todo")).toBe(true);
  });
});

describe("verdict", () => {
  const base: Verdict = { decidedBy: "arbiter", strongerCase: "prop", summary: [] };
  it("headline copy by decidedBy / strongerCase / format (MULTI-08 AC1–AC2b)", () => {
    expect(verdictHeadline(base, "two_sided")).toMatchObject({ kind: "side", text: "STRONGER CASE: PROPOSITION" });
    expect(verdictHeadline(base, "two_sided").sub).toMatch(/argument quality/);
    expect(verdictHeadline({ ...base, decidedBy: "user", strongerCase: "opp" }, "two_sided").sub).toBe("Your call · stronger case: Opposition");
    expect(verdictHeadline({ ...base, strongerCase: null }, "two_sided").text).toBe("TOO CLOSE TO CALL");
    expect(verdictHeadline({ ...base, strongerCase: null }, "panel").kind).toBe("summary");
  });
  it("rubric rows follow rubric order; no scores → no rows (AC4)", () => {
    const v: Verdict = { ...base, scores: [
      { subjectId: "opp", criterionId: "b", value: 6 }, { subjectId: "prop", criterionId: "a", value: 7 }, { subjectId: "prop", criterionId: "b", value: 8 },
    ] };
    const rows = rubricRows(v, [{ id: "a", label: "A" }, { id: "b", label: "B" }], ["prop", "opp"]);
    expect(rows.map((r) => r.id)).toEqual(["a", "b"]);
    expect(rows[1].values).toEqual([{ subjectId: "prop", value: 8 }, { subjectId: "opp", value: 6 }]);
    expect(rubricRows(base, [{ id: "a", label: "A" }], ["prop"])).toEqual([]);
  });
});

describe("setup", () => {
  it("cast limits 2–4, 5 with Advanced", () => {
    expect(castLimits(false)).toEqual({ min: 2, max: 4 });
    expect(castLimits(true).max).toBe(5);
  });
  it("auto-assign balances and keeps existing picks", () => {
    expect(autoAssign(["a", "b", "c"], {})).toEqual({ a: "prop", b: "opp", c: "prop" });
    expect(autoAssign(["a", "b", "c"], { a: "opp" })).toEqual({ a: "opp", b: "prop", c: "prop" });
    expect(autoAssign(["b"], { a: "opp", b: "opp" })).toEqual({ b: "opp" });
  });
  it("estimates and suggestions are deterministic", () => {
    expect(estimateRoundSec(3, "debate")).toBe(21);
    expect(suggestMotions("Meridian")).toEqual(suggestMotions("Meridian"));
    expect(new Set(suggestMotions("x")).size).toBe(3);
  });
  it("turn length defaults to Short with 5 debaters", () => {
    expect(defaultTurnLength(4)).toBe("medium");
    expect(defaultTurnLength(5)).toBe("short");
  });
  it("panel offers no 'You decide'", () => {
    expect(verdictOptionsFor("panel")).toEqual(["arbiter", "none"]);
    expect(verdictOptionsFor("two_sided")).toContain("user");
  });
  it("start gate: motion + one per side (debate), premise (watch), nothing for group (MULTI-05 AC1, MULTI-09)", () => {
    const d = { motion: "THW tax sugar", format: "two_sided" as const, cast: ["a", "b"], sides: { a: "prop" as const, b: "opp" as const }, premise: "" };
    expect(setupConfigOk("debate", d)).toBe(true);
    expect(setupConfigOk("debate", { ...d, motion: "  " })).toBe(false);
    expect(setupConfigOk("debate", { ...d, motion: "x".repeat(201) })).toBe(false);
    expect(setupConfigOk("debate", { ...d, sides: { a: "prop", b: "prop" } })).toBe(false);
    expect(setupConfigOk("debate", { ...d, format: "panel", sides: { a: "prop", b: "prop" } })).toBe(true);
    expect(setupConfigOk("watch", { ...d, premise: "Rainy Sunday" })).toBe(true);
    expect(setupConfigOk("watch", { ...d, premise: "x".repeat(301) })).toBe(false);
    expect(setupConfigOk("group", d)).toBe(true);
    expect(setupConfigOk(undefined, d)).toBe(false);
  });
});
