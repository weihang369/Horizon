// Wizard step gates (doc 02 CHR epic "Step gates" table) and profile validation (CHR-04). Pure. Owner: Builder B.
import type { Character, CharacterProfile, CreationStep, Emotion, GenerationJob } from "@/contract/types";
import { CREATION_STEPS } from "@/contract/types";

export const STEP_LABEL: Record<CreationStep, string> = {
  seed: "Seed", profile: "Profile", look: "Look", portrait: "Portrait",
  emotions: "Emotions", palette: "Palette", theme: "Theme", approve: "Approve",
};

export const stepIndex = (s: CreationStep | undefined): number => (s ? CREATION_STEPS.indexOf(s) : 0);

export type ProfileErrors = Partial<Record<"name" | "role" | "age" | "tagline" | "traits", string>>;

/** CHR-04 AC1: required fields, adult age, tagline ≤ 80, traits 3–8. */
export function validateProfile(p: Pick<CharacterProfile, "name" | "role" | "age" | "tagline" | "personality">): ProfileErrors {
  const e: ProfileErrors = {};
  if (!p.name.trim()) e.name = "Every character needs a name.";
  if (!p.role.trim()) e.role = "Give them a role, even a loose one.";
  if (!Number.isInteger(p.age)) e.age = "Age must be a whole number.";
  else if (p.age < 18) e.age = "Horizon characters are adults.";
  else if (p.age > 120) e.age = "That's a little too legendary.";
  if (p.tagline.length > 80) e.tagline = "Keep the tagline to 80 characters.";
  const n = p.personality.traits.length;
  if (n > 0 && n < 3) e.traits = "Pick at least 3 traits.";
  if (n > 8) e.traits = "8 traits at most.";
  return e;
}

export const profileValid = (p: Parameters<typeof validateProfile>[0]): boolean => Object.keys(validateProfile(p)).length === 0;

export interface GateFacts {
  /** A character exists: the draft returned, or "Write it myself" was chosen (CHR seed gate). */
  hasCharacter: boolean;
  profileOk: boolean;
  baseLocked: boolean;
  /** Emotion job started, any non-neutral emotion exists, or "Skip for now" (creationStep moved past EMOTIONS). */
  emotionsStartedOrSkipped: boolean;
  paletteSet: boolean;
}

export function gateFacts(c: Character | null | undefined, opts: { profileOk?: boolean; emotionJob?: GenerationJob | null } = {}): GateFacts {
  if (!c) return { hasCharacter: false, profileOk: false, baseLocked: false, emotionsStartedOrSkipped: false, paletteSet: false };
  const others = (Object.keys(c.emotions) as Emotion[]).some((e) => e !== "neutral" && !!c.emotions[e]);
  const past = c.status === "approved" || stepIndex(c.creationStep) > stepIndex("emotions");
  return {
    hasCharacter: true,
    profileOk: opts.profileOk ?? profileValid(c.profile),
    baseLocked: !!c.appearance.basePortraitUrl,
    emotionsStartedOrSkipped: past || others || !!opts.emotionJob,
    paletteSet: !!c.paletteId,
  };
}

/** The gate that must pass to move from `step` to the next one. */
export function gateFrom(step: CreationStep, f: GateFacts): { ok: boolean; reason?: string } {
  switch (step) {
    case "seed": return f.hasCharacter ? { ok: true } : { ok: false, reason: "Draft with AI or write it yourself first." };
    case "profile": return f.profileOk ? { ok: true } : { ok: false, reason: "Fill in the required profile fields." };
    case "look": return { ok: true };
    case "portrait": return f.baseLocked ? { ok: true } : { ok: false, reason: "Lock a base portrait first." };
    case "emotions": return f.emotionsStartedOrSkipped ? { ok: true } : { ok: false, reason: "Generate emotions or skip for now." };
    case "palette": return f.paletteSet ? { ok: true } : { ok: false, reason: "Pick a palette." };
    case "theme": return { ok: true };
    case "approve": return { ok: false };
  }
}

/** A step is reachable when every gate before it passes. */
export function reachable(step: CreationStep, f: GateFacts): boolean {
  const i = stepIndex(step);
  for (let j = 0; j < i; j++) if (!gateFrom(CREATION_STEPS[j], f).ok) return false;
  return true;
}

/** The furthest reachable step (resume target when a URL points past a gate). */
export function furthestReachable(f: GateFacts): CreationStep {
  let last: CreationStep = "seed";
  for (const s of CREATION_STEPS) {
    if (!reachable(s, f)) break;
    last = s;
  }
  return last;
}

/** Approve gate (CHR-11 AC3): valid profile + locked base portrait. */
export const canApprove = (f: GateFacts): boolean => f.hasCharacter && f.profileOk && f.baseLocked;

/** The later of two steps (creationStep only moves forward). */
export const laterStep = (a: CreationStep | undefined, b: CreationStep): CreationStep => (stepIndex(a) >= stepIndex(b) ? a ?? b : b);

/** Emotions missing art, excluding neutral (Approve warnings). */
export function missingEmotions(c: Pick<Character, "emotions">): Emotion[] {
  return (Object.keys(c.emotions) as Emotion[]).filter((e) => e !== "neutral" && !c.emotions[e]);
}
