// "AI" profile drafts for the wizard (CHR-02/03): a seed line like "Sarah, a doctor" becomes a full profile,
// appearance chips, a palette pick and a song brief. Deterministic per seed. Owner: EE.
import type { Appearance, Character, CharacterProfile, SongBrief } from "../../contract/types";
import { PALETTES } from "../../theme/palettes";
import { createRng } from "../rng";

const PROFESSIONAL = /doctor|physician|nurse|lawyer|attorney|counsel|economist|therapist|accountant|pharmac|engineer|teacher|professor|scientist|advisor|consultant/i;

const NAMES = ["Sarah", "Kenji", "Lucia", "Omar", "Priya", "Theo", "Aiko", "Marcus", "Noor", "Elias"];
/** docs/ai/04 P11: plain greetings (the first chat says it word for word, P9) and example lines that teach the voice. */
const GREETINGS = ["Oh, hey. I'm {name}.", "Hey. {name}. Good to meet you.", "Hi, I'm {name}. Pull up a chair."];
const EXAMPLE_LINES = [
  "Honestly? I'd start with the easy part.", "Hm. Give me a second with that.", "That's fair. Still, I'd push back a little.",
  "Okay, tell me the rest.", "Long day. Worth it, though.", "Wait, say that again?",
];
const firstWord = (n: string) => n.trim().split(/\s+/)[0]?.toLowerCase() ?? "";
/** A name from the seed is kept (the user asked for it); a bank name skips names already used in the world (P11). */
const pickName = (seed: string, namesInUse: string[] = []) => {
  const m = seed.match(/^\s*([A-Z][a-z]+)(?=[\s,])/);
  if (m) return m[1];
  const taken = new Set(namesInUse.map(firstWord));
  const start = createRng(seed).int(0, NAMES.length - 1);
  for (let i = 0; i < NAMES.length; i++) {
    const n = NAMES[(start + i) % NAMES.length];
    if (!taken.has(n.toLowerCase())) return n;
  }
  return NAMES[start];
};

function roleFrom(seed: string): string {
  const m = seed.match(/\b(?:a|an)\s+([^,.]+)/i);
  const raw = (m ? m[1] : seed).replace(/\bwho\b.*$/i, "").trim();
  return raw ? raw.replace(/^\w/, (c) => c.toUpperCase()).slice(0, 60) : "Friend";
}

export interface DraftResult {
  profile: CharacterProfile;
  attributes: Appearance["attributes"];
  appearanceSummary: string;
  paletteId: string;
  advisory: boolean;
  brief: SongBrief;
}

export function draftFromSeed(seed: string, intent: Character["intent"], namesInUse: string[] = []): DraftResult {
  const rng = createRng(`draft:${seed}`);
  const name = pickName(seed, namesInUse);
  const role = roleFrom(seed);
  const advisory = intent === "expert" || PROFESSIONAL.test(seed);
  const traits = rng.shuffle(["curious", "patient", "dry-humoured", "warm", "precise", "stubborn", "playful", "loyal", "candid"]).slice(0, 4);
  const profile: CharacterProfile = {
    name,
    role,
    age: rng.int(24, 58),
    pronouns: "",
    tagline: rng.pick(["Ask me the real question.", "One thing at a time.", "I've seen worse. Probably.", "Let's make this simple."]),
    personality: { summary: `${traits[0][0].toUpperCase()}${traits[0].slice(1)} and ${traits[1]}, with a ${traits[2]} streak.`, traits },
    backstory: `${name} spent years as a ${role.toLowerCase()} before anyone thought to ask what they actually think. Now they say it.`,
    speakingStyle: {
      summary: "Plain words, short paragraphs, the occasional aside.",
      tone: rng.pick(["warm", "dry", "upbeat", "measured"]),
      formality: rng.pick(["casual", "neutral", "formal"] as const),
      quirks: [rng.pick(["Counts points on fingers.", "Answers questions with a question first.", "Uses food metaphors."])],
      catchphrases: [rng.pick(["Here's the thing.", "Fair, but no.", "Okay, story time."])],
    },
    expertise: [role.toLowerCase()],
    goals: "Be useful without pretending to know everything.",
    boundaries: advisory ? ["No definitive diagnoses or legal advice; points to a professional for decisions."] : ["Keeps things friendly and SFW."],
    greeting: "",
    exampleLines: [],
    relationshipToUser: intent === "companion" ? "a close friend" : "",
  };
  const attributes: Appearance["attributes"] = {
    body: { ageBand: profile.age < 30 ? "young_adult" : profile.age < 45 ? "adult" : "middle_aged", build: rng.pick(["slim", "average", "athletic"]), height: "average", skinTone: rng.pick(["light", "beige", "olive", "tan", "brown", "deep brown"]) },
    face: { shape: rng.pick(["oval", "round", "heart", "square"]), baseline: "neutral", marks: [] },
    eyes: { shape: rng.pick(["almond", "round", "upturned"]), color: rng.pick(["dark brown", "brown", "hazel", "green", "grey"]), glasses: rng.pick(["none", "none", "round", "square"] as const) },
    hair: { length: rng.pick(["short", "chin", "shoulder", "long"]), style: rng.pick(["straight", "wavy", "curly", "ponytail", "low bun", "bob"]), color: rng.pick(["black", "dark brown", "chestnut", "auburn", "honey blonde"]), fringe: rng.pick(["none", "side-swept", "curtain"]) },
    outfit: { archetype: advisory ? (PROFESSIONAL.test(seed) && /doctor|nurse|physician/i.test(seed) ? "medical" : "business") : rng.pick(["casual", "street", "cosy"]), primaryColor: "#2F5D8A", secondaryColor: "#F5F2EA" },
    accessories: advisory && /doctor|nurse|physician/i.test(seed) ? ["stethoscope"] : [rng.pick(["watch", "earrings", "scarf"])],
    vibe: [rng.pick(["warm", "confident", "gentle", "energetic"])],
  };
  const h = attributes.hair;
  const appearanceSummary = `${attributes.body.ageBand.replace("_", " ")} ${role.toLowerCase()}, ${h.length} ${h.color} ${h.style} hair, ${attributes.eyes.color} eyes, ${attributes.outfit.archetype} outfit.`;
  const paletteId = rng.pick(PALETTES).id;
  const brief: SongBrief = { genres: [rng.pick(["lo-fi", "city-pop", "acoustic folk", "piano", "synthwave"])], moods: [rng.pick(["hopeful", "calm", "playful", "confident"])], bpm: rng.int(80, 124), instruments: ["piano", rng.pick(["synth", "guitar", "bells"])], vibe: `${name}'s everyday theme` };
  // P11, drawn last so the earlier picks keep their order: a plain greeting and 2–3 example lines that differ from it.
  profile.greeting = rng.pick(GREETINGS).replace("{name}", name);
  const n = rng.int(2, 3);
  profile.exampleLines = rng.shuffle(EXAMPLE_LINES).slice(0, n);
  return { profile, attributes, appearanceSummary, paletteId, advisory, brief };
}

/** A regenerated single field (CHR-04 AC2). */
export function regenerateField(profile: CharacterProfile, field: string, attempt: number): Partial<CharacterProfile> {
  const rng = createRng(`field:${profile.name}:${field}:${attempt}`);
  switch (field) {
    case "tagline": return { tagline: rng.pick(["Let's keep it honest.", "Bring snacks, bring questions.", "I'll tell you what I'd do.", "Slow is smooth, smooth is fast."]) };
    case "greeting": return { greeting: rng.pick([`Oh, hey! Good timing.`, `There you are. Sit, talk.`, `Hi again. What's the plan?`]) };
    case "backstory": return { backstory: `${profile.name} grew up somewhere small and loud, learned the job the hard way, and kept the stories.` };
    case "goals": return { goals: rng.pick(["Finish one big project this year.", "Teach someone everything they know.", "Take a real holiday, finally."]) };
    default: return { [field]: (profile as unknown as Record<string, unknown>)[field] } as Partial<CharacterProfile>;
  }
}
