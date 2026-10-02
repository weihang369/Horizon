// LOOK step catalogues (CHR-06): Sims-style chip and swatch pickers. Values are free strings in the contract;
// these lists are the UI's vocabulary. Swatch hexes are *character appearance data* (they are sent to the image
// model and stored in Appearance), not UI theme colours. Owner: Builder B.
import type { AgeBand, Appearance, CharacterProfile, SongBrief } from "@/contract/types";

export interface Opt { value: string; label: string }
export interface SwatchOpt { value: string; label: string; hex: string }

const o = (...xs: string[]): Opt[] => xs.map((v) => ({ value: v, label: v.replace(/_/g, " ") }));

export const AGE_BANDS: { value: AgeBand; label: string }[] = [
  { value: "young_adult", label: "Young adult" },
  { value: "adult", label: "Adult" },
  { value: "middle_aged", label: "Middle-aged" },
  { value: "senior", label: "Senior" },
];
export const BUILDS = o("slim", "petite", "average", "athletic", "curvy", "stocky", "broad");
export const HEIGHTS = o("short", "average", "tall");
export const SKIN: SwatchOpt[] = [
  ["porcelain", "#F6E3D4"], ["fair", "#EFD0B8"], ["light", "#E6BC98"], ["beige", "#D9A97E"],
  ["warm beige", "#C99468"], ["olive", "#B5895B"], ["tan", "#A47148"], ["golden brown", "#8D5A35"],
  ["brown", "#77482A"], ["deep brown", "#5C3520"], ["espresso", "#452616"], ["ebony", "#2F1A10"],
].map(([value, hex]) => ({ value, label: value, hex }));

export const FACE_SHAPES = o("oval", "round", "heart", "square", "long", "diamond");
export const BASELINES: { value: "soft" | "neutral" | "sharp"; label: string }[] = [
  { value: "soft", label: "Soft" }, { value: "neutral", label: "Neutral" }, { value: "sharp", label: "Sharp" },
];
export const MARKS = o("freckles", "dimples", "beauty mark", "scar", "laugh lines", "smile lines");

export const EYE_SHAPES = o("almond", "round", "upturned", "downturned", "hooded", "monolid");
export const EYE_COLORS: SwatchOpt[] = [
  ["dark brown", "#3B2416"], ["brown", "#6B4226"], ["amber", "#B8742A"], ["hazel", "#8E7340"],
  ["green", "#4F7D4A"], ["grey", "#8A9099"], ["blue", "#4A7DB8"], ["light blue", "#8DB8E0"],
  ["violet", "#7D5BA6"], ["black", "#17130F"], ["gold", "#C9A23A"], ["teal", "#2E8C88"],
].map(([value, hex]) => ({ value, label: value, hex }));
export const GLASSES: { value: Appearance["attributes"]["eyes"]["glasses"]; label: string }[] = [
  { value: "none", label: "None" }, { value: "round", label: "Round" }, { value: "square", label: "Square" }, { value: "half_rim", label: "Half-rim" },
];

export const HAIR_LENGTHS = o("buzz", "short", "chin", "shoulder", "long", "very long");
export const HAIR_STYLES = o("straight", "wavy", "curly", "coily", "bob", "pixie", "ponytail", "low bun", "high bun", "braids", "twin tails", "slicked back");
export const HAIR_COLORS: SwatchOpt[] = [
  ["black", "#141214"], ["soft black", "#2A2321"], ["dark brown", "#3D2A1F"], ["chestnut", "#6A3F27"],
  ["auburn", "#8C3B24"], ["copper", "#B5582C"], ["honey blonde", "#C99A55"], ["platinum", "#E6DCC4"],
  ["ash grey", "#9A9A98"], ["silver", "#C9CED6"], ["white", "#EEEAE2"], ["pink", "#E58CB0"],
  ["lavender", "#A98BD6"], ["teal", "#2E9C96"], ["navy", "#2A3A66"], ["crimson", "#9E1F2F"],
].map(([value, hex]) => ({ value, label: value, hex }));
export const FRINGES = o("none", "straight", "side-swept", "curtain", "wispy");

export const OUTFITS = o("casual", "street", "cosy", "business", "medical", "formal", "academic", "sporty", "artsy", "uniform");
export const OUTFIT_COLORS: SwatchOpt[] = [
  ["ink", "#1C1C24"], ["charcoal", "#3A3A44"], ["cream", "#F5F2EA"], ["sand", "#D9C6A5"],
  ["navy", "#2F5D8A"], ["sky", "#7FB5E0"], ["forest", "#2F6B45"], ["sage", "#9DB89A"],
  ["wine", "#7A1F35"], ["coral", "#E8735A"], ["mustard", "#D4A017"], ["lilac", "#B9A3E0"],
].map(([value, hex]) => ({ value, label: value, hex }));

export const ACCESSORIES = o("glasses chain", "hairpin", "earrings", "scarf", "pendant", "watch", "headphones", "bucket hat", "tie", "stethoscope", "ear cuff", "beret");
export const VIBES = o("warm", "confident", "gentle", "energetic", "mysterious", "playful", "serious", "dreamy", "rebellious", "elegant");

export const LOOK_TABS = ["body", "face", "eyes", "hair", "outfit", "accessories", "vibe"] as const;
export type LookTab = (typeof LOOK_TABS)[number];

/** CHR-06 AC2: selections compile into one editable sentence. */
export function compileSummary(a: Appearance["attributes"], role: string): string {
  const band = AGE_BANDS.find((b) => b.value === a.body.ageBand)?.label.toLowerCase() ?? "adult";
  const hair = [a.hair.length, a.hair.color, a.hair.style !== "straight" ? a.hair.style : "", "hair"].filter(Boolean).join(" ");
  const parts = [
    `${/^[aeiou]/i.test(band) ? "An" : "A"} ${band}${role ? ` ${role.toLowerCase()}` : ""}`,
    `${a.body.build} build`,
    `${a.body.skinTone} skin`,
    hair + (a.hair.streakColor ? ` with a ${a.hair.streakColor} streak` : "") + (a.hair.fringe !== "none" ? `, ${a.hair.fringe} fringe` : ""),
    `${a.eyes.shape} ${a.eyes.color} eyes${a.eyes.glasses !== "none" ? ` behind ${a.eyes.glasses.replace("_", "-")} glasses` : ""}`,
    `${a.outfit.archetype} outfit`,
  ];
  if (a.face.marks.length) parts.push(a.face.marks.join(" and "));
  if (a.accessories.length) parts.push(`wearing ${a.accessories.join(", ")}`);
  let s = parts.join(", ");
  if (a.vibe.length) s += `. ${a.vibe.map((v) => v[0].toUpperCase() + v.slice(1)).join(", ")} vibe`;
  return `${s}.`;
}

// ── SEED step ────────────────────────────────────────────────────────────────
export const SEED_EXAMPLES = [
  "Sarah, a doctor who explains things with cooking metaphors",
  "A retired detective who now runs a ramen stall",
  "Kenji, a sleepy astrophysicist who loves karaoke",
  "My older sister who always has advice, whether I want it or not",
  "A cheerful mechanic who names every car she fixes",
  "Lucia, an economist who can't resist a hot take",
];
export const SURPRISE = [
  "Noor, a lighthouse keeper who writes letters to ships",
  "A jazz pianist who moonlights as a crossword setter",
  "Theo, a park ranger obsessed with fungi",
  "Aiko, a pastry chef with strong opinions about sourdough",
  "Marcus, a tax accountant who secretly writes romance novels",
  "Priya, a pharmacist who runs marathons at dawn",
  "Elias, a ferry captain who quotes old movies",
  "Omar, a bookshop owner who reviews every customer's choice",
];
export const INTENTS: { value: "expert" | "companion" | "other"; label: string; hint: string }[] = [
  { value: "expert", label: "Expert / Advisor", hint: "Knows a field, gives grounded takes" },
  { value: "companion", label: "Companion / Life-sim", hint: "Friend, family, partner, rival" },
  { value: "other", label: "Other", hint: "Anything else" },
];

// ── PROFILE step: regenerable fields (CHR-04 AC2) ────────────────────────────
export type ProfileField = keyof CharacterProfile;
export const REGEN_FIELDS: ProfileField[] = ["tagline", "greeting", "backstory", "goals"];

// ── THEME step catalogues (CHR-10) ───────────────────────────────────────────
export const GENRES = o("lo-fi", "city-pop", "acoustic folk", "piano", "synthwave", "jazz", "orchestral", "chiptune", "bossa nova", "ambient");
export const MOODS = o("hopeful", "calm", "playful", "confident", "dreamy", "romantic", "nostalgic", "tense", "melancholic");
export const INSTRUMENTS = o("piano", "synth", "guitar", "bells", "bass", "strings", "drums", "flute", "sax", "music box");

export const DEFAULT_BRIEF: SongBrief = { genres: ["lo-fi"], moods: ["hopeful"], bpm: 96, instruments: ["piano", "synth"], vibe: "An everyday theme" };
