// The Insight changes the user chose after the pilot review (U-62): skipped rows (U-49), the search's waits and the
// passage preview (U-58, U-59), one path per kind of turn (U-57), and a kept face's chip. Static markup in node.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { TurnTrace } from "../../contract/types";
import { emotionChip } from "./emotionView";
import { MoreList } from "./InsightDrawer";
import { citingSentence, focusSnippet } from "./passagePreview";
import { searchWaits, System1Rows } from "./System1Section";
import { turnPath } from "./turnPath";

const nameOf = (id: string) => ({ chr_seedRin: "Rin" } as Record<string, string>)[id] ?? id;

const NOTEBOOK = `p. 6. Fishing-day rice balls: pack them the night before, wrap them in a cloth, and give the biggest one to whoever drives.

p. 7. Tamagoyaki: three eggs, a spoon of sugar, a little dashi. Roll it in thin layers.

p. 12. A good dinner has one dish everyone loves and one dish someone has never tried. Arguments about the second one are part of the meal.`;

describe("passage preview (U-59)", () => {
  it("starts at the sentence the reply cited, not at the passage's first line", () => {
    const reply = "She did! One dish everybody loves and one nobody's tried, and the arguing is half the meal [1]. So papaya salad.";
    const probe = citingSentence(reply, 1);
    expect(probe).toContain("everybody loves");
    expect(focusSnippet(NOTEBOOK, probe).startsWith("…p. 12. A good dinner has one dish everyone loves")).toBe(true);
  });

  it("keeps the passage as it is when nothing matches, or when the best match is its start", () => {
    expect(focusSnippet(NOTEBOOK, "quantum chromodynamics")).toBe(NOTEBOOK);
    expect(focusSnippet(NOTEBOOK, "fishing rice balls cloth")).toBe(NOTEBOOK);
    expect(citingSentence("No marker here.", 1)).toBe("");
  });
});

describe("System 1 rows (U-49, U-58)", () => {
  const trace: TurnTrace = {
    messageId: "msg_a1",
    search: { vectorMs: 2210, rewriteMs: 3375 },
    system1: {
      questions: [
        { purpose: "turn_plan", id: "emotion_line", version: 1, label: "emotion", about: "chr_seedRin", answer: "happy", p: 0.57, confidence: 0.51,
          compared: [{ name: "confidence", value: 0.51, threshold: 0.2 }], result: "used", action: "shown" },
        { purpose: "turn_plan", id: "docs", version: 1, label: "needs documents?", about: "chr_seedRin", answer: "—", compared: [],
          result: "skipped", action: "skipped: no searchable documents" },
        { purpose: "guardrail", id: "output_rules", version: 1, label: "reply breaks the rules?", answer: "no", compared: [],
          result: "fallback", action: "flagged: Jev late" },
      ],
    },
  };
  const html = renderToStaticMarkup(createElement(System1Rows, { trace, nameOf }));

  it("a question this turn didn't ask is a greyed row with its reason, and no meter", () => {
    expect(html).toContain('data-result="skipped"');
    expect(html).toContain("skipped: no searchable documents");
    const row = html.slice(html.indexOf('data-result="skipped"'), html.indexOf("</li>", html.indexOf('data-result="skipped"')));
    expect(row).not.toContain("s1Meter");
  });

  it("says which number a row tests (Jev's confidence, not the p beside it)", () => {
    expect(html).toContain("confidence 0.51 ≥ 0.20");
    expect(html).toMatch(/p 0\.57/);
  });

  it("a late check shows a dash, not an answer Jev never gave", () => {
    const at = html.indexOf("flagged: Jev late");
    expect(html.slice(at, at + 200)).toContain("—");
  });

  it("the search's waits are their own group after the plan", () => {
    expect(searchWaits(trace).map((w) => w.label)).toEqual(["meaning vector of the query", "rewritten query"]);
    expect(html).toContain('data-purpose="search"');
    expect(html.indexOf('data-purpose="search"')).toBeGreaterThan(html.indexOf('data-purpose="turn_plan"'));
    expect(html).toContain("waited 2.2 s");
    expect(html).toContain("waited 3.4 s");
  });
});

describe("one path per kind of turn (U-57)", () => {
  const plan = { purpose: "debate_plan", id: "emotion_line", version: 1, label: "emotion", answer: "thinking", result: "used" as const };
  it("a plan made ahead gets its plan steps back, and a search always starts with deep", () => {
    const t: TurnTrace = { messageId: "msg_a", graph: { path: ["gather", "search", "check", "keep"] }, system1: { questions: [plan] } };
    expect(turnPath(t)).toEqual(["state", "ask", "decide", "route", "deep", "gather", "search", "check", "keep"]);
  });

  it("a path already whole is left as it is; no plan rows: no plan steps added", () => {
    const whole = ["state", "ask", "decide", "route", "deep", "gather", "search", "check", "keep"];
    expect(turnPath({ messageId: "msg_a", graph: { path: whole }, system1: { questions: [plan] } })).toEqual(whole);
    expect(turnPath({ messageId: "msg_a", graph: { path: ["recall"] } })).toEqual(["deep", "recall"]);
    expect(turnPath({ messageId: "msg_a" })).toEqual([]);
  });
});

describe("a kept face (U-57)", () => {
  it("says kept when Jev didn't pick the face, even when it is the top candidate", () => {
    expect(emotionChip({ chosen: "angry", source: "default", candidates: [{ label: "angry", p: 0.35 }, { label: "neutral", p: 0.09 }] })).toBe("kept");
  });

  it("a face Jev picked is never kept, even under a higher bar (Takeshi's happy at 0.45 under neutral's 0.55)", () => {
    expect(emotionChip({ chosen: "happy", source: "classifier", candidates: [{ label: "neutral", p: 0.55 }, { label: "happy", p: 0.45 }] })).toBe("classifier");
  });
});

describe("a long memory list folds (the user's ask, 2026-10-22)", () => {
  const li = (x: string) => createElement("li", { key: x }, x);
  const html = (n: number) => renderToStaticMarkup(createElement(MoreList<string>, {
    items: Array.from({ length: n }, (_, i) => `memory ${i + 1}`), render: li,
  }));

  it("ten memories show the first three and a \"show all (10)\" button", () => {
    const h = html(10);
    expect(h.match(/<li>/g)).toHaveLength(3);
    expect(h).toContain("show all (10)");
    expect(h).toContain('aria-expanded="false"');
  });

  it("four or fewer show whole: no button just to hide one", () => {
    expect(html(4).match(/<li>/g)).toHaveLength(4);
    expect(html(4)).not.toContain("show all");
  });
});
