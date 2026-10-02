import { describe, expect, it } from "vitest";
import type { SessionEvent } from "../../contract/types";
import { formatClock, replayMarkers, stepTurn } from "./replayMarkers";

const ev = (seq: number, sec: number, type: SessionEvent["type"], payload: unknown): SessionEvent =>
  ({ id: `e${seq}`, sessionId: "s", seq, at: new Date(Date.UTC(2026, 0, 1, 0, 0, sec)).toISOString(), type, payload } as SessionEvent);

const events: SessionEvent[] = [
  ev(1, 0, "phase", { phase: "opening", round: 1, iteration: 1 }),
  ev(2, 1, "turn.start", { messageId: "m1", author: { type: "character", characterId: "a" } }),
  ev(3, 1, "emotion", { messageId: "m1", characterId: "a", emotion: "neutral", source: "llm" }),
  ev(4, 20, "turn.start", { messageId: "m2", author: { type: "character", characterId: "b" } }),
  ev(5, 21, "emotion", { messageId: "m1", characterId: "a", emotion: "angry", source: "llm" }),
];

describe("replay markers (O23)", () => {
  it("marks rounds, turns and emotion changes on the trimmed timeline", () => {
    const m = replayMarkers(events, true, (id) => id.toUpperCase());
    expect(m.map((x) => x.kind)).toEqual(["round", "turn", "turn", "emotion"]);
    expect(m[2].t).toBe(1000 + 2500);
    expect(m[3].label).toBe("A → angry");
  });

  it("untrimmed keeps real gaps", () => {
    expect(replayMarkers(events, false)[2].t).toBe(20_000);
  });

  it("steps between turns", () => {
    const m = replayMarkers(events, true);
    expect(stepTurn(m, 0, 1)).toBe(1000);
    expect(stepTurn(m, 1000, 1)).toBe(3500);
    expect(stepTurn(m, 3500, -1)).toBe(1000);
    expect(formatClock(65_400)).toBe("1:05");
  });
});
