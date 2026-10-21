// O08's "System 1 · Jev" section (docs/ai/13 W1; system1-trace "The Insight section"). Static markup in node.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { TurnTrace } from "../../contract/types";
import { groupSystem1, resolveId, showSystem1, System1Rows } from "./System1Section";

const nameOf = (id: string) => ({ chr_seedHana: "Hana", chr_seedRin: "Rin" } as Record<string, string>)[id] ?? id;

const trace: TurnTrace = {
  messageId: "msg_a1",
  calls: [{ purpose: "route", model: "typesafe/jev-1.13", costUsd: 0.00002, latencyMs: 412 }],
  knowledge: { retrieved: [{ chunkId: "kch_p1", sourceId: "kno_s1", title: "Shift Fatigue Review", locator: "p. 3", text: "…", score: 0.8, cited: true }] },
  system1: {
    questions: [
      { purpose: "route", id: "route", version: 2, label: "who replies?", answer: "chr_seedHana", p: 0.71, confidence: 0.71, result: "used", action: "answers first" },
      { purpose: "turn_plan", id: "emotion", version: 1, label: "emotion", about: "chr_seedRin", answer: "happy", confidence: 0.5, result: "not_used" },
      { purpose: "turn_plan", id: "needs_docs", version: 1, label: "needs documents?", about: "chr_seedHana", answer: "yes", p: 0.81,
        compared: [{ name: "p", value: 0.81, threshold: 0.35 }], result: "used", action: "deep" },
      { purpose: "deep_check", id: "passage", version: 1, label: "does this passage answer it?", about: "kch_p1", answer: "answers", result: "fallback" },
    ],
  },
};

describe("System 1 section", () => {
  it("groups by purpose in first-seen order, with the slowest call's latency or fallback", () => {
    const g = groupSystem1(trace);
    expect(g.map((x) => x.purpose)).toEqual(["route", "turn_plan", "deep_check"]);
    expect(g[0].latencyMs).toBe(412);
    expect(g[2].fallback).toBe(true);
    expect(g[1].rows).toHaveLength(1);
    expect(g[1].folded).toHaveLength(1);
  });

  it("shows the route row with the speaker's name, p and its band, and comparisons", () => {
    const html = renderToStaticMarkup(createElement(System1Rows, { trace, nameOf }));
    expect(html).toContain("who replies?");
    expect(html).toContain("Hana");
    expect(html).toMatch(/p 0\.71/);
    expect(html).toContain("HIGH");
    expect(html).toContain("0.81 ≥ 0.35");
    expect(html).toContain(">deep</span>");                          // the verdict pill
    expect(html).toContain('data-tone="pass"');                       // 0.81 crossed its line…
    expect(html).toContain("left:35%");                               // …the tick sits at 0.35
    expect(html).toContain("asked about the others (1)");
    expect(html).not.toContain("chr_seedHana");
  });

  it("greys a row under its line and marks a fallback (U-29 meter rows)", () => {
    const t: TurnTrace = { ...trace, system1: { questions: [
      { purpose: "deep_check", id: "passage", version: 1, label: "does this passage answer it?", about: "kch_p1", answer: "partly", p: 0.72,
        compared: [{ name: "p", value: 0.72, threshold: 0.9 }], result: "used", action: "dropped" },
      { purpose: "deep_check", id: "passage", version: 1, label: "does this passage answer it?", about: "kch_p1", answer: "answers", result: "fallback" },
    ] } };
    const html = renderToStaticMarkup(createElement(System1Rows, { trace: t, nameOf }));
    expect(html).toContain('data-tone="miss"');
    expect(html).toContain("0.72 &lt; 0.90");
    expect(html).toContain('data-tone="fallback"');
    expect(html).toContain(">fallback</span>");
  });

  it("resolves IDs to names or titles, never text", () => {
    expect(resolveId("kch_p1", trace, nameOf)).toBe("Shift Fatigue Review (p. 3)");
    expect(resolveId("mem_x", trace, nameOf)).toBe("a memory");
    expect(resolveId("chr_seedRin", trace, nameOf)).toBe("Rin");
  });

  it("groups recall's rows as earlier lines and resolves mem_ and msg_ through what the turn was given (M13 D35)", () => {
    const t: TurnTrace = {
      messageId: "msg_a2",
      calls: [{ purpose: "deep_check", model: "typesafe/jev-1.13", costUsd: 0.00001, latencyMs: 640 }],
      memory: { recalled: [{ memoryItemId: "mem_1", text: "Kai plays the cello every Sunday morning.", score: 0.81 }] },
      contextInSession: [{ text: "Kai: My sister Mia just started nights.", messageId: "msg_9" }],
      system1: {
        questions: [
          { purpose: "deep_check", id: "passage", version: 2, label: "does this passage answer it?", about: "kch_p1", answer: "answers", result: "used" },
          { purpose: "deep_check", id: "recall", version: 1, label: "does this earlier line help?", about: "mem_1", answer: "yes", p: 0.81, result: "used" },
          { purpose: "deep_check", id: "recall", version: 1, label: "does this earlier line help?", about: "msg_9", answer: "yes", p: 0.7, result: "used" },
        ],
      },
    };
    const g = groupSystem1(t);
    expect(g.map((x) => x.label)).toEqual(["passages", "earlier lines"]);
    expect(g[1].latencyMs).toBe(640);
    expect(resolveId("mem_1", t, nameOf)).toBe("“Kai plays the cello every Sunday mornin…”");
    expect(resolveId("msg_9", t, nameOf)).toBe("“Kai: My sister Mia just started nights.”");
    expect(resolveId("msg_404", t, nameOf)).toBe("a message");
  });

  it("is hidden without rows and absent in Compact mode", () => {
    expect(groupSystem1({ messageId: "msg_a1" })).toEqual([]);
    expect(showSystem1({ messageId: "msg_a1" }, false)).toBe(false);
    expect(showSystem1(trace, true)).toBe(false);
    expect(showSystem1(trace, false)).toBe(true);
  });
});
