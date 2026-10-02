import { describe, expect, it } from "vitest";
import type { GateFacts } from "./gates";
import { canApprove, furthestReachable, gateFrom, laterStep, reachable, validateProfile } from "./gates";

const base = { name: "Sarah", role: "Doctor", age: 34, tagline: "Hi", personality: { summary: "", traits: ["a", "b", "c"] } };
const none: GateFacts = { hasCharacter: false, profileOk: false, baseLocked: false, emotionsStartedOrSkipped: false, paletteSet: false };
const all: GateFacts = { hasCharacter: true, profileOk: true, baseLocked: true, emotionsStartedOrSkipped: true, paletteSet: true };

describe("validateProfile (CHR-04)", () => {
  it("accepts a valid adult profile", () => expect(validateProfile(base)).toEqual({}));
  it("rejects minors with the house copy", () => expect(validateProfile({ ...base, age: 17 }).age).toBe("Horizon characters are adults."));
  it("requires name and role", () => {
    const e = validateProfile({ ...base, name: " ", role: "" });
    expect(e.name).toBeTruthy();
    expect(e.role).toBeTruthy();
  });
  it("caps tagline at 80 and traits at 3–8", () => {
    expect(validateProfile({ ...base, tagline: "x".repeat(81) }).tagline).toBeTruthy();
    expect(validateProfile({ ...base, personality: { summary: "", traits: ["a"] } }).traits).toBeTruthy();
    expect(validateProfile({ ...base, personality: { summary: "", traits: Array(9).fill("t") } }).traits).toBeTruthy();
  });
});

describe("step gates (CHR table)", () => {
  it("nothing past SEED without a character", () => {
    expect(reachable("seed", none)).toBe(true);
    expect(reachable("profile", none)).toBe(false);
    expect(furthestReachable(none)).toBe("seed");
  });
  it("LOOK → PORTRAIT is always open, PORTRAIT → EMOTIONS needs a lock", () => {
    const f = { ...none, hasCharacter: true, profileOk: true };
    expect(reachable("portrait", f)).toBe(true);
    expect(reachable("emotions", f)).toBe(false);
    expect(gateFrom("portrait", f).reason).toMatch(/Lock/);
    expect(furthestReachable(f)).toBe("portrait");
  });
  it("EMOTIONS → PALETTE needs a started job or skip", () => {
    const f = { ...all, emotionsStartedOrSkipped: false };
    expect(reachable("palette", f)).toBe(false);
    expect(reachable("approve", all)).toBe(true);
  });
  it("approve needs a valid profile and a locked base only", () => {
    expect(canApprove({ ...all, emotionsStartedOrSkipped: false })).toBe(true);
    expect(canApprove({ ...all, baseLocked: false })).toBe(false);
    expect(canApprove({ ...all, profileOk: false })).toBe(false);
  });
  it("creationStep only moves forward", () => {
    expect(laterStep("palette", "look")).toBe("palette");
    expect(laterStep(undefined, "look")).toBe("look");
  });
});
