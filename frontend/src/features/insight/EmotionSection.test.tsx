// Insight's Emotion section (turn-plan-emotion D15; speaker-emotion "Kept face in Insight"). Static markup in node.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EmotionBody } from "./EmotionSection";
import { emotionChip } from "./emotionView";

/** The "chosen" line only (the bars below print their own bands). */
const chosenLine = (html: string) => html.slice(0, html.indexOf("</p>"));

describe("Emotion section", () => {
  it("a kept face: the chip says kept, no band, and the bars list Jev's top candidate first", () => {
    const e = { chosen: "thinking" as const, source: "default" as const,
      candidates: [{ label: "thinking" as const, p: 0.3 }, { label: "angry" as const, p: 0.41 }] };
    expect(emotionChip(e)).toBe("kept");
    const html = renderToStaticMarkup(createElement(EmotionBody, { emotion: e, armed: true, manual: false }));
    expect(chosenLine(html)).toContain("Thinking");
    expect(chosenLine(html)).not.toMatch(/HIGH|MED|LOW/);
    expect(html.indexOf("Angry")).toBeLessThan(html.indexOf("Thinking", html.indexOf("Angry")));
  });

  it("a shown pick keeps its source chip and band", () => {
    const e = { chosen: "sad" as const, source: "classifier" as const, candidates: [{ label: "sad" as const, p: 0.82 }] };
    expect(emotionChip(e)).toBe("classifier");
    expect(chosenLine(renderToStaticMarkup(createElement(EmotionBody, { emotion: e, armed: true, manual: false })))).toContain("HIGH");
  });

  it("no candidates: the source label as before (AI for llm), and no band", () => {
    expect(emotionChip({ chosen: "happy", source: "llm" })).toBe("AI");
    expect(emotionChip({ chosen: "neutral", source: "default", candidates: [] })).toBe("default");
    expect(chosenLine(renderToStaticMarkup(createElement(EmotionBody, { emotion: { chosen: "happy", source: "llm" }, armed: true, manual: false }))))
      .not.toMatch(/HIGH|MED|LOW/);
  });
});
