// The context bar scales to the larger of budget and used, and marks the overflow (docs/ai/05 X1; conversation-context
// "Cache-hit and context figures are true"; persona-context task 5.3).
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StackedBar } from "./Data";

const seg = (key: string, value: number) => ({ key, label: key, value, color: "#123456" });

describe("StackedBar", () => {
  it("under budget: no overflow mark, used / budget", () => {
    const html = renderToStaticMarkup(createElement(StackedBar, { label: "Context budget", total: 10000, segments: [seg("history", 4000), seg("system", 1000)] }));
    expect(html).toContain("width:40%");
    expect(html).toContain("5.0K / 10K");
    expect(html).not.toContain("over");
  });

  it("over budget: every segment shows, scaled to the sum, with the overflow marked", () => {
    const html = renderToStaticMarkup(createElement(StackedBar, { label: "Context budget", total: 10000, segments: [seg("history", 12000), seg("system", 3000)] }));
    expect(html).toContain("width:80%");                  // 12,000 of 15,000: nothing clipped
    expect(html).toContain("width:20%");
    expect(html).toMatch(/left:66\.6+\d*%/);             // the budget marker at 10,000 / 15,000
    expect(html).toContain("15K / 10K (+5.0K)");
    expect(html).toContain("5.0K over");                  // in the accessible label
  });
});
