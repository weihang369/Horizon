// Doc 11 S8 (safety D18, task 6.5): the notice under the key field and in the Knowledge drop zone. The components are
// shared by the mock and the HTTP client, so both show the same fixed text. Rendered to static markup (node env).
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import seedSettings from "../../../../seed/settings.json";
import type { AppSettings } from "../../contract/types";
import { ConnectionTab } from "./ConnectionTab";
import { CONNECTION_NOTICE, KNOWLEDGE_NOTICE } from "./privacyNotice";

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/'/g, "&#x27;").replace(/"/g, "&quot;");

describe("the privacy notice", () => {
  it("shows under the key field, naming training and what is sent", () => {
    const html = renderToStaticMarkup(createElement(ConnectionTab, { settings: seedSettings.data as unknown as AppSettings }));
    expect(html).toContain(esc(CONNECTION_NOTICE));
    expect(CONNECTION_NOTICE).toContain("These providers may use what they receive for training");
    for (const what of ["your messages", "passages from your documents", "memories"]) expect(CONNECTION_NOTICE).toContain(what);
  });

  it("the Knowledge drop zone renders its line", async () => {
    const src = (await import("node:fs")).readFileSync(new URL("../profile/tabs.tsx", import.meta.url), "utf8");
    expect(src).toContain("<span>{KNOWLEDGE_NOTICE}</span>");
    expect(KNOWLEDGE_NOTICE).toBe("Each document is sent once to the embedding provider when you add it; passages a character uses go to DeepSeek, which may train on them.");
  });
});
