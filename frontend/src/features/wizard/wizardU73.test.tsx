// U-73 (the user's character-wizard review): the summary names a hair length as a phrase, the theme credit drops its
// decision-log reference, and the energy bar shows energy topped up past max instead of capping the number.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import hana from "@seed/characters/chr_seedHana.json";
import type { Appearance } from "@/contract/types";
import { EnergyBar } from "@/character/EnergyBar";
import { songCredit } from "@/features/profile/songCredit";
import { compileSummary } from "./options";

const attrs = (hana as unknown as { data: { appearance: Appearance } }).data.appearance.attributes;

describe("compileSummary", () => {
  it("says chin-length, shoulder-length and buzz-cut, not the bare chip", () => {
    for (const [chip, phrase] of [["chin", "chin-length"], ["shoulder", "shoulder-length"], ["buzz", "buzz-cut"], ["long", "long"]]) {
      const s = compileSummary({ ...attrs, hair: { ...attrs.hair, length: chip, color: "black", style: "straight" } }, "");
      expect(s).toContain(`${phrase} black hair`);
    }
  });
});

describe("songCredit", () => {
  it("drops the decision reference and names the model once", () => {
    const note = "Composed by google/lyria-3-clip-preview through OpenRouter (D-87).";
    expect(songCredit({ licenseNote: note, generation: undefined })).toBe("Composed by google/lyria-3-clip-preview through OpenRouter");
    expect(songCredit({ licenseNote: "Placeholder: procedural WebAudio sketch (D-52).", generation: undefined })).toBe("Placeholder: procedural WebAudio sketch");
  });
  it("names the composer before a song exists", () => {
    expect(songCredit(null)).toBe("Composed by google/lyria-3-clip-preview through OpenRouter");
    expect(songCredit(null, true)).toBe("Placeholder: procedural WebAudio sketch");
  });
});

describe("EnergyBar past max", () => {
  it("shows the real energy in the label; the fill stops at full", () => {
    const html = renderToStaticMarkup(<EnergyBar energy={{ current: 2500, max: 1000, state: "active" }} showLabel />);
    expect(html.replace(/<[^>]*>/g, "")).toContain("2500 / 1000");
    expect(html).toContain("scaleX(1)");
    expect(html).toContain('aria-valuenow="2500"');
  });
});
