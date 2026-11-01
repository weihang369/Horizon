// docs/ai/03 C5 (reply-display spec): bubbles in chat, script lines in watch, never split in debate or for the user,
// and auto-Readable per bubble. Rendered to static markup in the node test environment.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Message } from "../../contract/types";
import { MessageRow } from "./MessageRow";
import { SessionContext, type SessionCtx } from "./sessionContext";

const ctx: SessionCtx = {
  replay: true, demo: true, isSeed: false, readable: false, worldId: "wld_x", sessionId: "ses_x", insightOpen: false,
};

function msg(content: string, extra: Partial<Message> = {}): Message {
  return {
    id: "msg_1", sessionId: "ses_x", seq: 2, author: { type: "character", characterId: "chr_a" }, kind: "chat",
    content, status: "complete", createdAt: "2026-10-10T00:00:00.000Z", ...extra,
  } as Message;
}

function render(m: Message, variant: "chat" | "script" = "chat", c: SessionCtx = ctx): string {
  return renderToStaticMarkup(createElement(SessionContext.Provider, { value: c },
    createElement(MessageRow, { m, chars: {}, variant, selected: false, canRegenerate: false, fresh: false })));
}

const count = (html: string, re: RegExp) => (html.match(re) ?? []).length;

describe("MessageRow bubbles (C5)", () => {
  it("shows a 1:1 reply as one bubble per line", () => {
    const html = render(msg("Haha. Yeah, I know.\n\nLong shift.\nYou?"));
    expect(count(html, /data-bubble="/g)).toBe(3);
    expect(html).toContain("Long shift.");
  });

  it("caps a group reply at four bubbles", () => {
    expect(count(render(msg("a\nb\nc\nd\ne\nf")), /data-bubble="/g)).toBe(4);
  });

  it("never splits a debate argument or the user's own message", () => {
    const debate = msg("Point one.\nPoint two.", { debate: { phase: "opening", round: 1, iteration: 0, side: "prop" } });
    expect(count(render(debate), /data-bubble="/g)).toBe(0);
    const user = msg("hi\nthere", { author: { type: "user" } });
    expect(count(render(user), /data-bubble="/g)).toBe(0);
  });

  it("shows a watch reply as script lines under one name tape", () => {
    const html = render(msg("Line one.\nLine two."), "script");
    expect(count(html, /class="[^"]*scriptLine/g)).toBe(2);
  });

  it("applies auto-Readable only when one bubble is over 600 characters", () => {
    const short = ["a".repeat(250), "b".repeat(250), "c".repeat(200)].join("\n");   // 700 chars, three bubbles
    const shortHtml = render(msg(short));
    expect(count(shortHtml, /data-bubble="/g)).toBe(3);
    expect(shortHtml).not.toMatch(/class="[^"]*readable/);
    const long = `${"x".repeat(650)}\nshort`;
    const longHtml = render(msg(long));
    expect(longHtml).toMatch(/class="[^"]*readable/);
    expect(count(longHtml, /data-bubble="/g)).toBe(0);   // the Readable panel shows the text unsplit
  });

  it("shows the reply unsplit when the user turns Readable on", () => {
    expect(count(render(msg("one\ntwo"), "chat", { ...ctx, readable: true }), /data-bubble="/g)).toBe(0);
  });

  it("opens a new bubble while streaming when a line break arrives", () => {
    expect(count(render(msg("Hey", { status: "streaming" })), /data-bubble="/g)).toBe(1);
    expect(count(render(msg("Hey\nYou up?", { status: "streaming" })), /data-bubble="/g)).toBe(2);
  });
});

describe("MessageRow cut actions (audit D-11)", () => {
  const live: SessionCtx = { ...ctx, replay: false, demo: false };
  const cut = msg("Half a tho", { status: "interrupted", interruptedBy: "error" });
  const actions = (chat: boolean) => renderToStaticMarkup(createElement(SessionContext.Provider, { value: live },
    createElement(MessageRow, { m: cut, chars: {}, variant: "chat", selected: false, canRegenerate: false, chat, fresh: false })));

  it("offers one chip, Regenerate, on an interrupted chat reply", () => {
    expect(actions(true)).toContain(">Regenerate<");
    expect(actions(true)).not.toContain(">Continue<");
  });

  it("offers neither on a cut debate argument or scene line (Regenerate is a chat command)", () => {
    expect(actions(false)).not.toContain(">Regenerate<");
    expect(actions(false)).not.toContain(">Continue<");
  });
});
