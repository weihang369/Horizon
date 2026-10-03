import { describe, expect, it } from "vitest";
import { parseBlocks, parseInline, plainText, splitMarkers } from "./markdown";

describe("markdown (CHAT-02 AC4)", () => {
  it("parses bold, italics, code and links", () => {
    expect(parseInline("a **b** *c* `d` [e](https://x.io)")).toEqual([
      { type: "text", text: "a " },
      { type: "strong", children: [{ type: "text", text: "b" }] },
      { type: "text", text: " " },
      { type: "em", children: [{ type: "text", text: "c" }] },
      { type: "text", text: " " },
      { type: "code", text: "d" },
      { type: "text", text: " " },
      { type: "link", href: "https://x.io", children: [{ type: "text", text: "e" }] },
    ]);
  });

  it("never turns raw HTML or unsafe links into markup", () => {
    expect(parseInline("<b>hi</b>")).toEqual([{ type: "text", text: "<b>hi</b>" }]);
    expect(parseInline("[x](javascript:alert(1))")).toEqual([{ type: "text", text: "[x](javascript:alert(1))" }]);
  });

  it("keeps snake_case and lone asterisks literal", () => {
    expect(parseInline("snake_case_name")).toEqual([{ type: "text", text: "snake_case_name" }]);
    expect(parseInline("2 * 3 = 6")).toEqual([{ type: "text", text: "2 * 3 = 6" }]);
    expect(parseInline("for *you* to")).toEqual([
      { type: "text", text: "for " }, { type: "em", children: [{ type: "text", text: "you" }] }, { type: "text", text: " to" },
    ]);
  });

  it("splits lists, code fences and paragraphs", () => {
    const b = parseBlocks("Intro\n\n- one\n- two\n\n1. a\n2. b\n\n```\nx < y\n```\n> quoted");
    expect(b.map((x) => x.type)).toEqual(["p", "ul", "ol", "code", "quote"]);
    expect(b[1]).toEqual({ type: "ul", items: ["one", "two"] });
    expect(b[3]).toEqual({ type: "code", text: "x < y" });
  });

  it("plainText strips markers", () => {
    expect(plainText("**Hi** *there*\n- a")).toBe("Hi there\n• a");
  });

  it("citation markers (D-59): only cited [n] become chips; code spans, links and unknown markers stay literal", () => {
    const cites = new Set([1, 2]);
    expect(parseInline("A.[1] B **c[2]** `[1]` [3] [x](https://x.io)", cites)).toEqual([
      { type: "text", text: "A." },
      { type: "cite", n: 1 },
      { type: "text", text: " B " },
      { type: "strong", children: [{ type: "text", text: "c" }, { type: "cite", n: 2 }] },
      { type: "text", text: " " },
      { type: "code", text: "[1]" },
      { type: "text", text: " [3] " },
      { type: "link", href: "https://x.io", children: [{ type: "text", text: "x" }] },
    ]);
    expect(parseInline("A.[1]")).toEqual([{ type: "text", text: "A.[1]" }]);
    expect(splitMarkers("a[1] b[4]", cites)).toEqual(["a", 1, " b[4]"]);
    expect(splitMarkers("a[1] b[4]")).toEqual(["a", 1, " b", 4]);
  });
});
