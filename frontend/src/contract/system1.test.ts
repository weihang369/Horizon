// Contract rev 1.4 (docs/ai/13 W1; client-contract "Contract revision 1.4 is additive"): `TurnTrace.system1`.
import { describe, expect, it } from "vitest";
import { TurnTraceSchema } from "./schemas";
import type { System1Row, TurnTrace } from "./types";

// W1's deep 1:1 example, as rows.
const ROWS: System1Row[] = [
  { purpose: "turn_plan", id: "needs_docs", version: 1, label: "needs documents?", about: "chr_seedAmara", answer: "yes", p: 0.81,
    compared: [{ name: "p", value: 0.81, threshold: 0.35 }], result: "used", action: "deep" },
  { purpose: "turn_plan", id: "needs_earlier", version: 1, label: "needs something earlier?", answer: "no", p: 0.12,
    compared: [{ name: "p", value: 0.12, threshold: 0.4 }], result: "used", action: "no recall" },
  { purpose: "turn_plan", id: "emotion", version: 1, label: "emotion", about: "chr_seedAmara", answer: "thinking", confidence: 0.62,
    compared: [{ name: "confidence", value: 0.62, threshold: 0.6 }], result: "used", action: "shown" },
  { purpose: "deep_check", id: "passage", version: 1, label: "does this passage answer it?", about: "kch_a1", answer: "answers",
    confidence: 0.88, compared: [{ name: "p_answers+p_partly", value: 0.95, threshold: 0.6 }], result: "used", action: "kept [1]" },
  { purpose: "guardrail", id: "output", version: 1, label: "breaks the content rules?", answer: "no", p: 0.02, result: "used", action: "pass" },
  { purpose: "face_check", id: "face", version: 1, label: "face and words agree?", answer: "yes", p: 0.66, result: "shown_only" },
  { purpose: "route", id: "route", version: 2, label: "who replies?", answer: "chr_seedHana", result: "fallback", action: "least recent" },
];
const trace: TurnTrace = { messageId: "msg_a1", system1: { seed: "2026-10-10|1:1|chr_seedAmara:4", questions: ROWS } };

describe("TurnTrace.system1 (rev 1.4)", () => {
  it("accepts W1's rows", () => {
    expect(TurnTraceSchema.safeParse(trace).success).toBe(true);
  });

  it("stays optional: a rev 1.3 trace still validates", () => {
    expect(TurnTraceSchema.safeParse({ messageId: "msg_a1", calls: [] }).success).toBe(true);
  });

  it("rejects 65 rows", () => {
    const many = Array.from({ length: 65 }, (_, i) => ({ ...ROWS[0], about: `chr_x${i}` }));
    expect(TurnTraceSchema.safeParse({ messageId: "msg_a1", system1: { questions: many } }).success).toBe(false);
  });

  it("rejects text in `about`, a p over 1 and an unknown result", () => {
    const bad = (row: Partial<System1Row>) => TurnTraceSchema.safeParse({ messageId: "msg_a1", system1: { questions: [{ ...ROWS[0], ...row }] } }).success;
    expect(bad({ about: "the user's memory text" })).toBe(false);
    expect(bad({ p: 1.2 })).toBe(false);
    expect(bad({ result: "maybe" as System1Row["result"] })).toBe(false);
  });
});
