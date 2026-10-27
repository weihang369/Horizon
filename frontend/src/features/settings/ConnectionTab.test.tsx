// D-106: a key from OPENROUTER_API_KEY (.env) can't be saved over or cleared in Settings, so Connection shows where it
// comes from and how to change it instead of a form and Clear that would only fail. Test connection stays. Rendered to
// static markup in the node test environment. The mock build (the online demo) never uses a key, so it shows a notice
// instead of the key field (the user's call, 2026-10-20); each test picks its build.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import seedSettings from "../../../../seed/settings.json";
import type { AppSettings } from "../../contract/types";
import { ONLINE_DEMO_NOTICE, RUN_LOCALLY_URL } from "../shell/onlineDemo";
import { ConnectionTab } from "./ConnectionTab";

const build = vi.hoisted(() => ({ mock: false }));
vi.mock("../shell/onlineDemo", async (original) => ({
  ...(await original<typeof import("../shell/onlineDemo")>()),
  get NO_BACKEND() {
    return build.mock;
  },
}));
beforeEach(() => {
  build.mock = false; // the HTTP build unless a test says otherwise
});

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

  it("the HTTP build keeps the key field and Test, with no online-demo notice", () => {
    const html = render({ openRouterKeyStatus: "missing", demoMode: true });
    expect(html).toMatch(/<input/);
    expect(html).toContain("Test connection");
    expect(html).toContain("openrouter.ai/keys");
    expect(html).not.toContain("never uses a key");
  });

  it("the mock build (online demo): a notice and a link to run it locally, no key field, Save or Test", () => {
    build.mock = true;
    const html = render({ openRouterKeyStatus: "missing", demoMode: true });
    expect(html).toContain(ONLINE_DEMO_NOTICE);
    expect(html).toContain("This online demo never uses a key: everything here was recorded.");
    expect(html).toContain(`href="${RUN_LOCALLY_URL}"`);
    expect(RUN_LOCALLY_URL).toBe("https://github.com/weihang369/Horizon#run-it-locally");
    expect(html).toContain("Browsing recorded data.");
    expect(html).not.toMatch(/<input|Save key|Test connection|Clear key|openrouter\.ai\/keys|Add your OpenRouter key/);
  });

  it("the mock build still offers Clear for a key an earlier visit saved", () => {
    build.mock = true;
    const html = render({ openRouterKeyStatus: "set", openRouterKeySource: "app", demoMode: false });
    expect(html).toContain("Clear key");
    expect(html).not.toMatch(/<input|Test connection/);
  });
});
