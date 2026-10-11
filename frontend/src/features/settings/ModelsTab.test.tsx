// docs/ai/03 C9 (llm-parameters "Tuned for one model set"): Settings → Models is read-only, and each role shows its
// price from the bundled table and a Test button. Rendered to static markup in the node test environment.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import seedSettings from "../../../../seed/settings.json";
import type { AppSettings } from "../../contract/types";
import { ModelsTab } from "./ModelsTab";

const settings = { ...(seedSettings.data as unknown as AppSettings), modelOverrides: { chat: "other/model" } } as AppSettings;

describe("Models tab", () => {
  const html = renderToStaticMarkup(createElement(ModelsTab, { settings }));

  it("has no editable model field and no save", () => {
    expect(html).not.toMatch(/<input/);
    expect(html).not.toMatch(/Save models|Reset to defaults/);
    expect(html).toContain("Tuned for these models. Custom models are planned for v2.");
  });

  it("shows each role's model in use (never the override), its price and Test", () => {
    for (const role of ["chat", "decision", "image", "music", "embedding"]) expect(html).toContain(`data-role="${role}"`);
    expect(html).toContain(settings.models.chat);
    expect(html).not.toContain("other/model");
    expect(html.match(/data-price/g)?.length).toBe(5);
    expect(html.match(/>Test</g)?.length).toBe(5);
  });
});
