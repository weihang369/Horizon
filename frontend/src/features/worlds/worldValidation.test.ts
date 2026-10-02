import { describe, expect, it } from "vitest";
import { validateWorldName } from "./worldValidation";

const worlds = [{ id: "a", name: "Meridian Council" }];

describe("validateWorldName", () => {
  it("requires 1–40 chars", () => {
    expect(validateWorldName("  ", worlds)).toMatch(/name/);
    expect(validateWorldName("x".repeat(41), worlds)).toMatch(/40/);
    expect(validateWorldName("Harbour Street", worlds)).toBeNull();
  });
  it("is unique, case-insensitive, except for itself", () => {
    expect(validateWorldName("meridian council ", worlds)).toMatch(/already/);
    expect(validateWorldName("Meridian Council", worlds, "a")).toBeNull();
  });
});
