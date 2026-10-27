// O05 in the online demo (mock build) never asks for a key: it says everything was recorded and links to running
// Horizon locally (the user's decision, 2026-10-20). The HTTP build keeps the key prompt. Static markup, node env.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { KeyRequired } from "./KeyRequired";
import { NO_BACKEND, ONLINE_DEMO_NOTICE, RUN_LOCALLY_URL } from "./onlineDemo";

const render = (onlineDemo: boolean) =>
  renderToStaticMarkup(createElement(KeyRequired, {
    layerKey: 0, close: () => {}, reason: "Live replies need your OpenRouter key.", onlineDemo,
  }));

describe("KeyRequired (O05)", () => {
  it("online demo: the notice and the run-locally link, no key ask", () => {
    const html = render(true);
    expect(html).toContain(ONLINE_DEMO_NOTICE.split(":")[0]);
    expect(html).toContain("everything here was recorded");
    expect(html).toContain(`href="${RUN_LOCALLY_URL}"`);
    expect(RUN_LOCALLY_URL).toBe("https://github.com/weihang369/Horizon#run-it-locally");
    expect(html).not.toMatch(/Add key|Add your OpenRouter key|Live replies need/);
  });

  it("HTTP build: today's key prompt, no demo notice", () => {
    const html = render(false);
    expect(html).toContain("Add your OpenRouter key");
    expect(html).toContain("Add key");
    expect(html).toContain("Live replies need your OpenRouter key.");
    expect(html).not.toContain("ONLINE DEMO");
    expect(html).not.toContain(RUN_LOCALLY_URL);
  });

  it("the default follows the build's client (the test env runs the mock client)", () => {
    expect(NO_BACKEND).toBe(true);
    expect(renderToStaticMarkup(createElement(KeyRequired, { layerKey: 0, close: () => {} }))).toContain("ONLINE DEMO");
  });
});
