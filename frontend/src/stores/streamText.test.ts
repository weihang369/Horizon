// clearStream(ids) also drops the ids from the StreamSmoother: a session closed mid-reply left its unfinished entry
// there, and the global ticker then ran every frame for good (R12: it runs only while text is being revealed).
import { afterEach, describe, expect, it, vi } from "vitest";
import { ticker } from "../vfx/ticker";
import { clearStream, setStreamTarget, streamText } from "./streamText";

const frames: FrameRequestCallback[] = [];
const run = (n: number) => {
  for (let i = 0; i < n; i++) frames.splice(0).forEach((cb) => cb((i + 1) * 16));
};

afterEach(() => vi.unstubAllGlobals());

describe("clearStream", () => {
  it("a message cleared mid-stream stops the ticker and stays cleared", () => {
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => frames.push(cb));
    setStreamTarget("msg_mid", "Half a reply that never finishes");
    run(2);
    expect(ticker.size).toBe(1);
    clearStream(["msg_mid"]);
    run(3);
    expect(ticker.size).toBe(0);
    expect(streamText.getState().text.msg_mid).toBeUndefined();
  });
});


describe("setStreamTarget", () => {
  it("a new take of a finished reply starts blank, not on the old text (pass 2 J2-04)", () => {
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => frames.push(cb));
    setStreamTarget("msg_regen", "Old full reply.", true);
    run(200);
    expect(streamText.getState().text.msg_regen).toBe("Old full reply.");
    setStreamTarget("msg_regen", "", false);   // Regenerate's turn.start
    expect(streamText.getState().text.msg_regen).toBe("");
    clearStream(["msg_regen"]);
  });
});
