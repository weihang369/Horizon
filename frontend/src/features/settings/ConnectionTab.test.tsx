// D-106: a key from OPENROUTER_API_KEY (.env) can't be saved over or cleared in Settings, so Connection shows where it
// comes from and how to change it instead of a form and Clear that would only fail. Test connection stays. Rendered to
// static markup in the node test environment.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import seedSettings from "../../../../seed/settings.json";
import type { AppSettings } from "../../contract/types";
import { ConnectionTab } from "./ConnectionTab";

const seed = seedSettings.data as unknown as AppSettings;
const render = (patch: Partial<AppSettings>) => renderToStaticMarkup(createElement(ConnectionTab, { settings: { ...seed, ...patch } }));

describe("Connection tab", () => {
  it("a key from .env: says so, no key field, no Save, no Clear; Test stays", () => {
    const html = render({ openRouterKeyStatus: "set", openRouterKeySource: "env", demoMode: false });
    expect(html).toContain("KEY SET");
    expect(html).toContain("from .env");
    expect(html).toMatch(/edit <code>\.env<\/code> and restart the backend/);
    expect(html).not.toMatch(/<input/);
    expect(html).not.toMatch(/Save key|Clear key/);
    expect(html).toContain("Test connection");
  });

  it("a rejected key from .env points at .env too", () => {
    const html = render({ openRouterKeyStatus: "invalid", openRouterKeySource: "env", demoMode: true });
    expect(html).toContain("KEY REJECTED");
    expect(html).toContain("Change it in .env.");
    expect(html).not.toMatch(/Paste a new one|Clear key/);
  });

  it("a key saved in the app keeps the form and Clear", () => {
    const html = render({ openRouterKeyStatus: "set", openRouterKeySource: "app", demoMode: false });
    expect(html).toMatch(/<input/);
    expect(html).toContain("Save key");
    expect(html).toContain("Clear key");
    expect(html).not.toContain("from .env");
  });

  it("no key: the form, no Clear", () => {
    const html = render({ openRouterKeyStatus: "missing", demoMode: true });
    expect(html).toContain("DEMO MODE");
    expect(html).toContain("Save key");
    expect(html).not.toContain("Clear key");
  });
});
