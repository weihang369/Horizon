// Appearance → ShadowSpec (R8). PURE and Node-safe.
// Seed characters get explicit identity overrides (VMD paper §2.3 table); everyone else is derived
// from Appearance (hair length/style, glasses, accessories, extra details) so wizard silhouettes match.
import type { Appearance, Emotion } from "../../contract/types";
import { getPalette } from "../../theme/palettes";
import type { ShadowAccessory, ShadowGlasses, ShadowHair, ShadowSpec, ShadowVariant } from "./types";

type Identity = Pick<ShadowSpec, "hair" | "glasses" | "accessories" | "streak" | "lapels" | "shoulders">;

/** Explicit identities for the 6 seed characters (doc 06 §2). */
export const SEED_IDENTITIES: Record<string, Identity> = {
  chr_seedAmara: { hair: "short", glasses: "round", accessories: ["stethoscope", "earrings"], lapels: true },
  chr_seedVictor: { hair: "slicked", glasses: "none", accessories: ["tie"], streak: "#C9CED6", lapels: true, shoulders: 1.06 },
  chr_seedMei: { hair: "bun", glasses: "pushed_up", accessories: ["pencil"] },
  chr_seedHana: { hair: "bob", glasses: "none", accessories: ["hairpin"], shoulders: 0.94 },
  chr_seedTakeshi: { hair: "short", glasses: "none", accessories: ["bucket_hat"], shoulders: 1.08 },
  chr_seedRin: { hair: "shoulder", glasses: "none", accessories: ["headphones_neck", "ear_cuff"], streak: "#2EC4B6", shoulders: 0.94 },
};

const COLOR_WORDS: Record<string, string> = {
  black: "#3A3A44", "dark brown": "#5A3A2A", chestnut: "#8A4B2F", auburn: "#9A3B2A", copper: "#C46A3A",
  ginger: "#D9792E", "honey blonde": "#E0B060", platinum: "#E8E4DA", silver: "#C9CED6", grey: "#A6A6AE",
  white: "#F2F2F2", pink: "#FF8FB8", lavender: "#C3A3F0", teal: "#2EC4B6", navy: "#3557A0", burgundy: "#8C2A44",
  blue: "#4A8BE8", green: "#3DBA6A", red: "#E64646", purple: "#9A5AE0",
};

function hairFrom(a: Appearance["attributes"]["hair"]): ShadowHair {
  const style = a.style.toLowerCase();
  if (style.includes("bun")) return "bun";
  if (style.includes("slick")) return "slicked";
  if (style.includes("bob")) return "bob";
  if (style.includes("pony")) return "ponytail";
  if (style.includes("twin")) return "twin";
  if (style.includes("braid")) return "long";
  if (style.includes("undercut")) return "short";
  const len = a.length.toLowerCase();
  if (len.includes("buzz")) return "buzz";
  if (len.includes("very") || len === "long") return "long";
  if (len.includes("shoulder")) return "shoulder";
  if (len.includes("chin")) return "bob";
  return "short";
}

function accessoriesFrom(list: string[], text: string): ShadowAccessory[] {
  const out = new Set<ShadowAccessory>();
  for (const raw of list) {
    const a = raw.toLowerCase();
    if (a.includes("tie")) out.add("tie");
    else if (a.includes("hairpin") || a.includes("hair pin") || a.includes("clip")) out.add("hairpin");
    else if (a.includes("headphone")) out.add(/neck/.test(text) ? "headphones_neck" : "headphones");
    else if (a.includes("hat") || a.includes("cap")) out.add("bucket_hat");
    else if (a.includes("stethoscope")) out.add("stethoscope");
    else if (a.includes("earring")) out.add("earrings");
    else if (a.includes("scarf")) out.add("scarf");
    else if (a.includes("pendant") || a.includes("necklace")) out.add("pendant");
    else if (a.includes("cuff")) out.add("ear_cuff");
  }
  if (/pencil/.test(text)) out.add("pencil");
  return [...out];
}

/** Derive a silhouette identity from Appearance alone. */
export function identityFromAppearance(appearance: Appearance): Identity {
  const at = appearance.attributes;
  const text = `${at.extraDetails ?? ""} ${appearance.appearanceSummary}`.toLowerCase();
  let glasses: ShadowGlasses = at.eyes.glasses;
  if (glasses !== "none" && /(pushed up|on (her|his|their) head)/.test(text)) glasses = "pushed_up";
  const build = at.body.build.toLowerCase();
  const shoulders = /broad|stocky|athletic/.test(build) ? 1.07 : /slim|petite/.test(build) ? 0.93 : 1;
  const streakWord = at.hair.streakColor?.toLowerCase();
  const streak = streakWord ? COLOR_WORDS[streakWord] ?? (streakWord.startsWith("#") ? streakWord : "#C9CED6") : undefined;
  return {
    hair: hairFrom(at.hair),
    glasses,
    accessories: accessoriesFrom(at.accessories, text),
    streak,
    lapels: ["business", "medical", "formal", "academic"].includes(at.outfit.archetype.toLowerCase()),
    shoulders,
  };
}

export interface SpecOptions {
  /** Enables the explicit seed identity override when it matches a seed character. */
  characterId?: string;
  /** Candidate B (mirrored, alternate hair). */
  candidate?: 1 | 2;
}

const ALT_HAIR: Record<ShadowHair, ShadowHair> = {
  buzz: "short", short: "slicked", bob: "shoulder", shoulder: "bob", long: "ponytail",
  bun: "ponytail", slicked: "short", ponytail: "long", twin: "long",
};

/**
 * specFromAppearance(appearance, paletteId, emotion, variant, opts?)
 * `opts` is an additive extension of the §3 signature (seed override + candidate B).
 */
export function specFromAppearance(
  appearance: Appearance | null | undefined,
  paletteId: string | null | undefined,
  emotion: Emotion = "neutral",
  variant: ShadowVariant = "default",
  opts: SpecOptions = {},
): ShadowSpec {
  const pal = getPalette(paletteId);
  const seed = opts.characterId ? SEED_IDENTITIES[opts.characterId] : undefined;
  const id: Identity = seed ?? (appearance ? identityFromAppearance(appearance) : { hair: "short", glasses: "none", accessories: [] });
  const cand2 = opts.candidate === 2;
  return {
    colors: {
      primary: pal.primary, secondary: pal.secondary, accent: pal.accent,
      glow: pal.glow, stage: pal.stage, surface: pal.surface,
    },
    emotion,
    variant,
    ...id,
    hair: cand2 ? ALT_HAIR[id.hair] : id.hair,
    mirror: cand2 || undefined,
  };
}

/** Canonical placeholder portrait path (seed build output, served under /assets). */
export function placeholderPortraitPath(characterId: string, name: Emotion | "blink" | "cand-2"): string {
  return `/assets/placeholder/portraits/${characterId}/${name}.svg`;
}

/** True for generated placeholder portraits (static seed SVGs or Shadow data URLs). */
export function isPlaceholderUrl(url: string | null | undefined): boolean {
  if (!url) return false;
  return url.includes("/placeholder/") || (url.startsWith("data:image/svg+xml") && url.includes("horizon-shadow"));
}
