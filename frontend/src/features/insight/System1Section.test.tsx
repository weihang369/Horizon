// O08's "System 1 · Jev" section (docs/ai/13 W1; system1-trace "The Insight section"). Static markup in node.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { System1Row, TurnTrace } from "../../contract/types";
import { groupSystem1, passageResult, resolveId, showSystem1, System1Rows } from "./System1Section";

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
    expect(html).toContain("not used this turn (1)");
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

  it("says when the search matched nothing after needs documents? said yes (U-34)", () => {
    const t: TurnTrace = { messageId: "msg_a3", knowledge: { retrieved: [] }, system1: { questions: [
      { purpose: "turn_plan", id: "docs", version: 2, label: "needs documents?", about: "chr_seedHana", answer: "yes", p: 0.86,
        compared: [{ name: "t_gate", value: 0.86, threshold: 0.45 }], result: "used", action: "search the documents" },
    ] } };
    const html = renderToStaticMarkup(createElement(System1Rows, { trace: t, nameOf }));
    expect(html).toContain("The search matched nothing in Hana&#x27;s documents");
    expect(renderToStaticMarkup(createElement(System1Rows, { trace, nameOf }))).not.toContain("matched nothing");
  });

  it("names the plan PLAN in every mode with a tag, says what each panel is, and uses plain row labels (U-35)", () => {
    const t: TurnTrace = { messageId: "msg_a4", system1: { questions: [
      { purpose: "debate_plan", id: "docs", version: 2, label: "needs documents?", about: "chr_seedHana", answer: "yes", p: 0.8, result: "used", action: "search the documents" },
      { purpose: "turn_plan", id: "english", version: 1, label: "English?", answer: "yes", p: 0.97, result: "used", action: "no rewrite needed" },
      { purpose: "face_check", id: "face_check", version: 1, label: "face and words agree?", answer: "yes", p: 0.82, result: "shown_only" },
    ] } };
    const g = groupSystem1(t);
    expect(g.map((x) => [x.label, x.tag])).toEqual([["plan", "made ahead"], ["plan", "before the reply"], ["after the reply", undefined]]);
    const html = renderToStaticMarkup(createElement(System1Rows, { trace: t, nameOf }));
    expect(html).toContain("message in English?");
    expect(html).not.toContain(">English?");
    expect(html).toContain("every question in one request");
    expect(html).toContain(">for Insight only</span>");
  });

  it("labels a passage's usable and found lines, keeps a usable-not-found passage bright, and heads Passages with the result (U-36)", () => {
    const pass = (about: string, use: number, ans: number, action: string): System1Row => ({
      purpose: "deep_check", id: "passage", version: 2, label: "does this passage answer it?", about, answer: ans >= 0.5 ? "answers" : "partly", p: use,
      compared: [{ name: "t_keep", value: use, threshold: 0.9 }, { name: "t_found", value: ans, threshold: 0.5 }],
      result: action === "kept" ? "used" : "below_threshold", action,
    });
    const found: TurnTrace = { messageId: "msg_a5", knowledge: trace.knowledge, system1: { questions: [
      pass("kch_p1", 0.95, 0.65, "kept"), pass("kch_p1", 0.97, 0.3, "kept"), pass("kch_p1", 0.4, 0.1, "dropped"),
    ] } };
    const html = renderToStaticMarkup(createElement(System1Rows, { trace: found, nameOf }));
    expect(html).toContain("usable 0.95 ≥ 0.90 · answers 0.65 ≥ 0.50");
    expect(html).toContain("usable 0.97 ≥ 0.90 · answers 0.30 &lt; 0.50");
    expect(html.match(/data-tone="pass"/g)).toHaveLength(2);           // the second is kept though not "found"
    expect(html).toContain('data-outcome="found"');
    expect(html).toContain("the reply gets the best 2 passages");
    expect(html.indexOf("data-outcome")).toBeLessThan(html.indexOf("usable 0.95"));   // at the top of Passages

    const qs = (...q: System1Row[]) => q;
    const partly = qs(pass("kch_p1", 0.95, 0.3, "kept"));
    expect(passageResult(partly)?.outcome).toBe("partly");
    expect(passageResult(partly)?.text).toContain("the 1 usable passage");
    const set: System1Row = { purpose: "deep_check", id: "passage_set", version: 1, label: "do these together answer it?", answer: "yes", result: "used", action: "found together" };
    expect(passageResult(qs(pass("kch_p1", 0.95, 0.3, "kept"), pass("kch_p1", 0.92, 0.2, "kept"), set))?.outcome).toBe("found_together");
    expect(passageResult(qs(pass("kch_p1", 0.4, 0.1, "dropped")))?.outcome).toBe("not_found");
    expect(passageResult(qs(pass("kch_p1", 0.95, 0.3, "kept"),
      { purpose: "deep_check", id: "passage", version: 2, label: "does this passage answer it?", about: "kch_p1", answer: "missing", compared: [], result: "fallback", action: "not checked" },
    ))?.outcome).toBe("fallback");
    // a turn saved before t_found: two usable and no set check means one was found; one usable can't be told apart
    const old = (use: number): System1Row => ({ ...pass("kch_p1", use, 0, "kept"), compared: [{ name: "t_keep", value: use, threshold: 0.9 }] });
    expect(passageResult(qs(old(0.99), old(0.95)))?.outcome).toBe("found");
    expect(passageResult(qs(old(0.99)))).toBeNull();
    expect(passageResult(qs(old(0.99), old(0.95), { ...set, answer: "no", action: "partly" }))?.outcome).toBe("partly");
    expect(passageResult(qs({ ...old(0.5), action: "dropped" }))?.outcome).toBe("not_found");
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
