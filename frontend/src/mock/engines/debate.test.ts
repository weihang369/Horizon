// M11 (debate design D3, D4; task 2.7): the mock's slot rules, the same cases as the backend's
// tests/sessions/test_debate_slots.py.
import { describe, expect, it } from "vitest";
import type { DebateConfig, Message } from "../../contract/types";
import { cursorOf, fillSlot, phaseSlots } from "./debate";

const two = (prop: string[], opp: string[]) => ({ format: "two_sided", sides: { prop, opp } }) as unknown as DebateConfig;
const m = (seq: number, author: string, kind = "chat", content = "x", extra: Partial<Message> = {}): Message =>
  ({ seq, kind, content, author: author.startsWith("chr") ? { type: "character", characterId: author } : { type: author }, ...extra }) as unknown as Message;

describe("debate slots (mock)", () => {
  it("alternates sides, and a panel has one slot per panellist", () => {
    expect(phaseSlots(two(["a", "b"], ["c", "d"]), ["a", "b", "c", "d"])).toEqual(["prop", "opp", "prop", "opp"]);
    expect(phaseSlots(two(["a", "b"], ["c"]), ["a", "b", "c"])).toEqual(["prop", "opp", "prop"]);
    expect(phaseSlots({ format: "panel" } as unknown as DebateConfig, ["a", "b", "c"])).toEqual([null, null, null]);
  });

  it("fills a slot: speak, skip or pause", () => {
    const all = () => true;
    expect(fillSlot(["a", "b"], [], all)).toEqual({ action: "speak", who: "a", asleep: [] });
    expect(fillSlot(["a", "b"], ["a"], all).who).toBe("b");
    expect(fillSlot(["a", "b"], ["a"], (c) => c === "a")).toEqual({ action: "skip", who: "b", asleep: ["b"] });
    expect(fillSlot(["a", "b"], [], (c) => c === "b").who).toBe("b");
    expect(fillSlot(["a", "b"], [], () => false)).toEqual({ action: "pause", asleep: ["a", "b"] });
  });

  it("counts arguments and skip notes since the banner, never an Ask answer", () => {
    const log = [m(1, "system", "system_note", "ROUND 1 · OPENING"), m(2, "chr_a"), m(3, "chr_v"),
      m(4, "system", "system_note", "ROUND 2 · CLOSING"), m(5, "chr_a"), m(6, "user", "steer", "Why?"),
      m(7, "chr_v", "chat", "Because.", { forcedSpeaker: true }),
      m(8, "system", "system_note", "Mei is asleep, skipping.", { targetCharacterId: "chr_m" })];
    expect(cursorOf(log)).toEqual({ used: 2, heard: ["chr_a"] });
  });
});
