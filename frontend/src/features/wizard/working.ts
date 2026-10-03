// The wizard's local working copy (human edits between saves). Server → local sync happens per slice while that
// slice is clean, so an arriving AI draft fills the form but never overwrites a human edit (CHR-04 AC3). Owner: Builder B.
import { useCallback, useEffect, useMemo, useReducer } from "react";
import type { Appearance, Character, CharacterProfile, SongBrief } from "@/contract/types";
import type { CharacterPatch } from "@/client/HorizonClient";
import { compileSummary } from "./options";

export interface Working {
  profile: CharacterProfile;
  editedFields: string[];
  advisory: boolean;
  attributes: Appearance["attributes"];
  summary: string;
  summaryEdited: boolean;
  brief: SongBrief | null;
  dirty: { profile: boolean; look: boolean };
  /** Bumped when an AI draft lands in a clean form (drives the staggered field reveal, CHR-03 AC1). */
  revealKey: number;
}

type Action =
  | { type: "sync"; c: Character }
  | { type: "field"; field: keyof CharacterProfile; value: unknown; human: boolean }
  | { type: "advisory"; value: boolean }
  | { type: "attr"; path: [keyof Appearance["attributes"], string?]; value: unknown }
  | { type: "summary"; value: string; edited: boolean }
  | { type: "brief"; value: SongBrief }
  | { type: "saved"; slice: "profile" | "look" | "all" }
  | { type: "reset"; c: Character };

const blankProfile = (): CharacterProfile => ({
  name: "", role: "", age: 30, tagline: "", personality: { summary: "", traits: [] }, backstory: "",
  speakingStyle: { summary: "", tone: "", formality: "neutral", quirks: [], catchphrases: [] },
  expertise: [], boundaries: [], greeting: "",
});

/** Song briefs are not on the Character; keep the edited one per character for this app session. */
const briefMemory = new Map<string, SongBrief>();
export const rememberBrief = (characterId: string, b: SongBrief) => void briefMemory.set(characterId, b);
export const recallBrief = (characterId: string) => briefMemory.get(characterId) ?? null;

function fromCharacter(c: Character | null): Working {
  return {
    profile: c ? structuredClone(c.profile) : blankProfile(),
    editedFields: c?.profileMeta?.editedFields ?? [],
    advisory: c?.advisory ?? false,
    attributes: c ? structuredClone(c.appearance.attributes) : structuredClone(DEFAULT_ATTRS),
    summary: c?.appearance.appearanceSummary ?? "",
    summaryEdited: false,
    brief: c ? recallBrief(c.id) : null,
    dirty: { profile: false, look: false },
    revealKey: 0,
  };
}

const DEFAULT_ATTRS: Appearance["attributes"] = {
  body: { ageBand: "adult", build: "average", height: "average", skinTone: "beige" },
  face: { shape: "oval", baseline: "neutral", marks: [] },
  eyes: { shape: "almond", color: "brown", glasses: "none" },
  hair: { length: "short", style: "straight", color: "black", fringe: "none" },
  outfit: { archetype: "casual", primaryColor: "#2F5D8A", secondaryColor: "#F5F2EA" },
  accessories: [], vibe: [],
};

const emptyProfile = (p: CharacterProfile) => !p.role && !p.tagline && !p.backstory;

function reducer(w: Working, a: Action): Working {
  switch (a.type) {
    case "reset": return fromCharacter(a.c);
    case "sync": {
      let next = w;
      if (!w.dirty.profile) {
        const landed = emptyProfile(w.profile) && !emptyProfile(a.c.profile);
        next = { ...next, profile: structuredClone(a.c.profile), advisory: a.c.advisory, editedFields: a.c.profileMeta?.editedFields ?? w.editedFields, revealKey: landed ? w.revealKey + 1 : w.revealKey };
      }
      if (!w.dirty.look) next = { ...next, attributes: structuredClone(a.c.appearance.attributes), summary: a.c.appearance.appearanceSummary };
      if (!next.brief) next = { ...next, brief: recallBrief(a.c.id) };
      return next;
    }
    case "field": {
      const editedFields = a.human ? [...new Set([...w.editedFields, a.field])] : w.editedFields.filter((f) => f !== a.field);
      return { ...w, profile: { ...w.profile, [a.field]: a.value }, editedFields, dirty: { ...w.dirty, profile: true } };
    }
    case "advisory": return { ...w, advisory: a.value, dirty: { ...w.dirty, profile: true } };
    case "attr": {
      const [group, key] = a.path;
      const attributes = structuredClone(w.attributes) as unknown as Record<string, unknown>;
      if (key) (attributes[group] as Record<string, unknown>)[key] = a.value;
      else attributes[group] = a.value;
      const at = attributes as unknown as Appearance["attributes"];
      return { ...w, attributes: at, summary: w.summaryEdited ? w.summary : compileSummary(at, w.profile.role), dirty: { ...w.dirty, look: true } };
    }
    case "summary": return { ...w, summary: a.value, summaryEdited: a.edited, dirty: { ...w.dirty, look: true } };
    case "brief": return { ...w, brief: a.value };
    case "saved": return { ...w, dirty: a.slice === "all" ? { profile: false, look: false } : { ...w.dirty, [a.slice]: false } };
  }
}

export function useWorking(c: Character | null | undefined) {
  const [w, dispatch] = useReducer(reducer, c ?? null, fromCharacter);
  useEffect(() => {
    if (c) dispatch({ type: "sync", c });
  }, [c]);
  const api = useMemo(() => ({
    setField: (field: keyof CharacterProfile, value: unknown, human = true) => dispatch({ type: "field", field, value, human }),
    setAdvisory: (value: boolean) => dispatch({ type: "advisory", value }),
    setAttr: (path: [keyof Appearance["attributes"], string?], value: unknown) => dispatch({ type: "attr", path, value }),
    setSummary: (value: string, edited = true) => dispatch({ type: "summary", value, edited }),
    setBrief: (value: SongBrief) => dispatch({ type: "brief", value }),
    markSaved: (slice: "profile" | "look" | "all") => dispatch({ type: "saved", slice }),
    reset: (rc: Character) => dispatch({ type: "reset", c: rc }),
  }), []);
  const patch = useCallback((): CharacterPatch | null => {
    const p: CharacterPatch = {};
    if (w.dirty.profile) {
      p.profile = w.profile;
      p.profileMeta = { editedFields: w.editedFields };
      p.advisory = w.advisory;
    }
    if (w.dirty.look) p.appearance = { attributes: w.attributes, appearanceSummary: w.summary };
    return Object.keys(p).length ? p : null;
  }, [w]);
  useEffect(() => {
    if (c && w.brief) rememberBrief(c.id, w.brief);
  }, [c, w.brief]);
  return { w, ...api, patch, dirty: w.dirty.profile || w.dirty.look };
}

export type WorkingApi = ReturnType<typeof useWorking>;
