// D-89 (budget-caps "No setting pre-authorises generation spend"): the Cost tab doesn't offer autoGenerateMissingEmotions,
// even when the stored value is on. Rendered to static markup in the node test environment.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import seedSettings from "../../../../seed/settings.json";
import type { AppSettings } from "../../contract/types";
import { CostTab } from "./CostTab";

const settings = { ...(seedSettings.data as unknown as AppSettings), autoGenerateMissingEmotions: true };

describe("Cost tab", () => {
  it("does not show the auto-generate missing emotions control", () => {
    const html = renderToStaticMarkup(createElement(CostTab, { settings }));
    expect(html).toContain("Generation mode");
    expect(html).toContain("Confirm before generating");
    expect(html).not.toMatch(/auto-generate missing emotions/i);
  });
});
