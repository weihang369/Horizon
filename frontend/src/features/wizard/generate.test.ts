// D-90 (generation-jobs "Naive edits need a raster base"): starting an edit of an SVG placeholder base turns
// `validation` / `base_not_raster` into "Generate a portrait first" with a button to the portrait step.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HorizonError } from "@/contract/errors";

const m = vi.hoisted(() => ({
  start: vi.fn(),
  get: vi.fn(),
  settings: vi.fn(),
  toast: vi.fn(),
  navigate: vi.fn(),
  reportError: vi.fn(),
}));

vi.mock("@/client", () => ({
  client: { jobs: { start: m.start, estimate: vi.fn() }, characters: { get: m.get }, settings: { get: m.settings } },
}));
vi.mock("@/client/hooks", () => ({ useActiveJobs: () => ({ data: [] }) }));
vi.mock("@/app/layers", () => ({ openOverlay: vi.fn(), toast: m.toast }));
vi.mock("@/app/errors", () => ({ reportError: m.reportError }));
vi.mock("@/stores/ui", () => ({ ui: { subscribe: vi.fn(() => () => {}) } }));
vi.mock("@/router", () => ({ navigate: m.navigate }));

const { PORTRAIT_FIRST, startGeneration } = await import("./generate");

const baseNotRaster = () => new HorizonError("validation", "This character's base portrait is a placeholder drawing.", {
  details: { field: "characterId", reason: "base_not_raster" },
});

describe("startGeneration with a placeholder base (D-90)", () => {
  beforeEach(() => {
    Object.values(m).forEach((f) => f.mockReset());
    m.settings.mockResolvedValue({ openRouterKeyStatus: "set", cost: { confirmBeforeGenerate: false } });
  });

  it("offers the portrait step for a draft character", async () => {
    m.start.mockRejectedValue(baseNotRaster());
    m.get.mockResolvedValue({ id: "chr_a", worldId: "wld_x", status: "draft" });
    expect(await startGeneration({ characterId: "chr_a", kind: "emotion_set" }, "Generate emotions")).toBeNull();
    expect(m.reportError).not.toHaveBeenCalled();
    const t = m.toast.mock.calls[0][0];
    expect(t.text).toBe(PORTRAIT_FIRST);
    expect(t.text.startsWith("Generate a portrait first")).toBe(true);
    expect(t.action.label).toBe("Generate a portrait");
    t.action.run();
    expect(m.navigate).toHaveBeenCalledWith({ name: "wizard", worldId: "wld_x", characterId: "chr_a", step: "portrait" });
  });

  it("opens the wizard in edit mode for an approved character", async () => {
    m.start.mockRejectedValue(baseNotRaster());
    m.get.mockResolvedValue({ id: "chr_seedHana", worldId: "wld_seedMeridian", status: "approved" });
    await startGeneration({ characterId: "chr_seedHana", kind: "emotion_regenerate", emotions: ["happy"] }, "Generate happy");
    m.toast.mock.calls[0][0].action.run();
    expect(m.navigate).toHaveBeenCalledWith({ name: "wizard", worldId: "wld_seedMeridian", characterId: "chr_seedHana", step: "portrait", edit: true });
  });

  it("keeps the generic error for other validation failures", async () => {
    const noBase = new HorizonError("validation", "Lock a base portrait first.", { details: { field: "characterId", reason: "no_base" } });
    m.start.mockRejectedValue(noBase);
    await startGeneration({ characterId: "chr_a", kind: "emotion_set" }, "Generate emotions");
    expect(m.toast).not.toHaveBeenCalled();
    expect(m.reportError).toHaveBeenCalledWith(noBase, expect.anything());
  });
});
