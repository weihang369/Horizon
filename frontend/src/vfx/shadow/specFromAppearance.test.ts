// A hair streak colour lands in an SVG attribute: only a colour word or a real hex colour passes through, so free text
// that starts with "#" can't break the silhouette (a data URL in an <img>).
import { describe, expect, it } from "vitest";
import type { Appearance } from "../../contract/types";
import { identityFromAppearance } from "./specFromAppearance";

const withStreak = (streakColor: string): Appearance => ({
  attributes: {
    body: { ageBand: "adult", build: "average", height: "average", skinTone: "medium" },
    face: { shape: "oval", baseline: "neutral", marks: [] },
    eyes: { shape: "almond", color: "brown", glasses: "none" },
    hair: { length: "long", style: "long straight", color: "black", streakColor, fringe: "none" },
    outfit: { archetype: "casual", primaryColor: "navy", secondaryColor: "white" },
    accessories: [],
    vibe: [],
  },
  appearanceSummary: "",
  candidates: [],
  stylePresetId: "p",
  stylePresetVersion: 1,
} as unknown as Appearance);

describe("identityFromAppearance streak", () => {
  it("keeps colour words and real hex colours", () => {
    expect(identityFromAppearance(withStreak("Teal")).streak).toBe("#2EC4B6");
    expect(identityFromAppearance(withStreak("#FF0000")).streak).toBe("#ff0000");
    expect(identityFromAppearance(withStreak("#abc")).streak).toBe("#abc");
  });

  it("free text starting with # falls back to the default streak", () => {
    for (const bad of ["#c00 & gold", '#000" stroke-width="999', "#ff0000 at the tips", "#12345"]) {
      expect(identityFromAppearance(withStreak(bad)).streak).toBe("#C9CED6");
    }
  });
});
