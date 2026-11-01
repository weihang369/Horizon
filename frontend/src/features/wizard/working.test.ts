// Audit C-P1-5 (part 2): a field regenerate's AI value is already saved on the server, so it must not leave a clean
// form showing "Unsaved edits" (and the leave guard) for nothing.
import { describe, expect, it } from "vitest";
import type { CharacterProfile } from "@/contract/types";
import { reducer, type Working } from "./working";

const profile: CharacterProfile = {
  name: "Mira", role: "Nurse", age: 30, tagline: "Calm", personality: { summary: "", traits: [] }, backstory: "",
  speakingStyle: { summary: "", tone: "", formality: "neutral", quirks: [], catchphrases: [] },
  expertise: [], boundaries: [], greeting: "Hi",
};

const clean = (editedFields: string[] = []): Working => ({
  profile, editedFields, advisory: false, attributes: {} as Working["attributes"], summary: "", summaryEdited: false,
  brief: null, dirty: { profile: false, look: false }, revealKey: 0,
});

describe("working reducer: field", () => {
  it("keeps a clean form clean for an AI value the server saved", () => {
    const w = reducer(clean(), { type: "field", field: "greeting", value: "Hello there", human: false });
    expect(w.profile.greeting).toBe("Hello there");
    expect(w.dirty.profile).toBe(false);
  });
  it("marks it dirty when the AI value clears an edited mark (the server doesn't store that)", () => {
    const w = reducer(clean(["greeting"]), { type: "field", field: "greeting", value: "Hello there", human: false });
    expect(w.editedFields).toEqual([]);
    expect(w.dirty.profile).toBe(true);
  });
  it("marks a human edit dirty, and keeps other unsaved edits dirty", () => {
    expect(reducer(clean(), { type: "field", field: "role", value: "Doctor", human: true }).dirty.profile).toBe(true);
    const edited = { ...clean(), dirty: { profile: true, look: false } };
    expect(reducer(edited, { type: "field", field: "greeting", value: "Yo", human: false }).dirty.profile).toBe(true);
  });
});
