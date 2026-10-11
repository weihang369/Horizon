import { describe, expect, it } from "vitest";
import { splitBubbles } from "./bubbles";

describe("splitBubbles (reply-display spec, design D21)", () => {
  it("splits on line breaks and collapses blank lines", () => {
    expect(splitBubbles("Haha. Yeah, I know.\n\nLong shift.\nYou?")).toEqual(["Haha. Yeah, I know.", "Long shift.", "You?"]);
  });

  it("joins lines past the fourth into the fourth", () => {
    expect(splitBubbles("a\nb\nc\nd\ne\nf")).toEqual(["a", "b", "c", "d\ne\nf"]);
  });

  it("never splits inside a fenced code block", () => {
    expect(splitBubbles("Look:\n```\nx = 1\n\ny = 2\n```\nDone.")).toEqual(["Look:", "```\nx = 1\n\ny = 2\n```", "Done."]);
  });

  it("keeps consecutive list lines together", () => {
    expect(splitBubbles("Bring:\n- tea\n- socks\nSee you")).toEqual(["Bring:", "- tea\n- socks", "See you"]);
  });

  it("works for Chinese text with line breaks, and keeps full stops inside a line", () => {
    expect(splitBubbles("好的。我明白了。\n你呢？")).toEqual(["好的。我明白了。", "你呢？"]);
    expect(splitBubbles("Dr. Lee said 3.5 hours.")).toEqual(["Dr. Lee said 3.5 hours."]);
  });

  it("handles CRLF, empty text and a trailing break while streaming", () => {
    expect(splitBubbles("one\r\ntwo")).toEqual(["one", "two"]);
    expect(splitBubbles("")).toEqual([]);
    expect(splitBubbles("one\n")).toEqual(["one"]);
  });
});
