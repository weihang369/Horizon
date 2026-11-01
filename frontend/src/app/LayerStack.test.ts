// Esc order and drawer focus (audit 03-F10, E-15.1): Esc closes what is on top, and closing a drawer returns focus to
// its opener only when focus was inside it.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ui } from "../stores/ui";
import { closeOverlay, isOverlayOpen, openOverlay } from "./layers";
import { handleEscape } from "./LayerStack";

const esc = () => handleEscape({ key: "Escape", defaultPrevented: false, preventDefault() {}, stopPropagation() {} } as KeyboardEvent);

describe("Esc with a modal and an expanded dock", () => {
  afterEach(() => ui.setState({ layers: [], dockExpansion: null }));

  it("closes a modal opened after the dock first, keeping the dock", () => {
    openOverlay("O12", { sessionId: "ses_1", kind: "ask" });
    openOverlay("O05", { reason: "Asking needs your OpenRouter key." });
    esc();
    expect(isOverlayOpen("O05")).toBe(false);
    expect(isOverlayOpen("O12")).toBe(true);
    esc();
    expect(isOverlayOpen("O12")).toBe(false);
  });

  it("collapses a dock expanded after the modal first", () => {
    openOverlay("O05", {});
    openOverlay("O12", { sessionId: "ses_1", kind: "interject" });
    esc();
    expect(isOverlayOpen("O12")).toBe(false);
    expect(isOverlayOpen("O05")).toBe(true);
  });
});

describe("closing a drawer", () => {
  const doc = globalThis as unknown as { document?: unknown };
  afterEach(() => {
    delete doc.document;
    ui.setState({ layers: [] });
  });

  const setup = () => {
    const opener = { isConnected: true, focus: vi.fn() };
    const inside = {};
    const dom = { activeElement: opener as unknown, querySelector: () => ({ contains: (x: unknown) => x === inside }) };
    doc.document = dom;
    openOverlay("O08", { sessionId: "ses_1" });
    return { opener, inside, dom };
  };

  it("returns focus to the opener when focus was inside it", async () => {
    const { opener, inside, dom } = setup();
    dom.activeElement = inside;
    closeOverlay("O08");
    await Promise.resolve();
    expect(opener.focus).toHaveBeenCalledTimes(1);
  });

  it("leaves focus alone when it was elsewhere (typing in the composer)", async () => {
    const { opener, dom } = setup();
    dom.activeElement = { composer: true };
    closeOverlay("O08");
    await Promise.resolve();
    expect(opener.focus).not.toHaveBeenCalled();
  });
});
