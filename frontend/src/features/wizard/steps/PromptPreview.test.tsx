// "View as prompt" shows the real `agent` prompt (persona-prompt "The preview is the real prompt"; docs/ai/04 P10).
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import amaraJson from "@seed/characters/chr_seedAmara.json";
import type { Character, CharacterProfile } from "@/contract/types";
import { compilePersona } from "@/domain/personaPrompt";
import { countTokens } from "@/domain/tokens";
import { PromptPreview } from "./PromptPreview";

const amara = (amaraJson as unknown as { data: Character }).data;
const world = { name: "Meridian Council", you: { displayName: "Kai", about: "A policy analyst." } };
const html = (profile: CharacterProfile) => renderToStaticMarkup(createElement(PromptPreview, {
  profile, appearanceSummary: amara.appearance.appearanceSummary, advisory: true, world,
}));
const decode = (x: string) => x.replace(/&quot;/g, "\"").replace(/&#x27;/g, "'").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");

describe("PromptPreview", () => {
  it("shows the compiled prompt and the backend's token count, with no mock label", () => {
    const out = decode(html(amara.profile));
    const want = compilePersona({ profile: amara.profile as unknown as Record<string, unknown>, appearanceSummary: amara.appearance.appearanceSummary, advisory: true,
      worldName: world.name, you: world.you, mode: "one_on_one" });
    expect(out).toContain(want.text);
    expect(out).toContain(`≈ ${countTokens(want.text)} tokens · read-only`);
    expect(out).not.toContain("mock template");
    expect(out).toContain("The user is Kai.");
  });

  it("updates with a long backstory: the cut and the new count", () => {
    const long = Array.from({ length: 400 }, (_, i) => `Night ${i} on the ward changed her mind again.`).join(" ");
    const before = decode(html(amara.profile));
    const after = decode(html({ ...amara.profile, backstory: long }));
    expect(after).toContain("Shortened to fit: backstory.");
    expect(after).toMatch(/Backstory: [^\n]*again\.…/);
    const n = (s: string) => Number(/≈ (\d+) tokens/.exec(s)?.[1]);
    expect(n(after)).toBeGreaterThan(n(before));
  });
});
