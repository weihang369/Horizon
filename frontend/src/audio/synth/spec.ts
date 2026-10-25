// Procedural theme spec (`*.proc.json`) and the brief → music mapping (VMD paper §2.6).
// PURE and Node-safe: the EE's seed build imports themeSpecFromBrief() to write the .proc.json files.
import type { SongBrief } from "../../contract/types";

export type ModeName =
  | "ionian" | "dorian" | "phrygian" | "lydian" | "mixolydian" | "aeolian" | "major_pent" | "minor_pent";

export type Groove =
  | "lofi" | "jazzhop" | "citypop" | "chiptune" | "orchestral" | "folk" | "synthwave" | "piano"
  | "bossa" | "ambient" | "rock" | "edm";

export type Voice =
  | "keys" | "pad" | "bells" | "pluck" | "guitar" | "bass" | "strings" | "brass" | "harmonica" | "chip" | "drums" | "crackle" | "arp";

/** Contents of a `*.proc.json` file. */
export interface ThemeProcSpec {
  kind: "horizon.theme";
  version: 1;
  /** PRNG seed (character id) — same seed, same theme. */
  seed: string;
  title?: string;
  brief: SongBrief;
  /** Optional overrides (system tracks). */
  mode?: ModeName;
  groove?: Groove;
  bars?: 8 | 16;
  /** Loudness trim applied after normalisation. */
  gainDb?: number;
}

export const MOOD_MODE: Record<string, ModeName> = {
  hopeful: "ionian", confident: "ionian", calm: "major_pent", dreamy: "lydian", playful: "mixolydian",
  romantic: "dorian", nostalgic: "dorian", melancholic: "aeolian", tense: "phrygian", energetic: "minor_pent",
};

export const GENRE_GROOVE: Record<string, Groove> = {
  "lo-fi": "lofi", lofi: "lofi", "jazz hip-hop": "jazzhop", "city-pop": "citypop", chiptune: "chiptune",
  orchestral: "orchestral", "acoustic folk": "folk", folk: "folk", synthwave: "synthwave", piano: "piano",
  "bossa nova": "bossa", ambient: "ambient", rock: "rock", edm: "edm",
};

/** Default voices per groove (instruments in the brief add to / steer these). */
export const GROOVE_VOICES: Record<Groove, Voice[]> = {
  lofi: ["keys", "bass", "drums", "crackle"],
  jazzhop: ["keys", "bass", "drums", "crackle"],
  citypop: ["keys", "bass", "drums", "bells"],
  chiptune: ["chip", "arp", "bass", "drums"],
  orchestral: ["strings", "brass", "bass"],
  folk: ["guitar", "bass", "drums"],
  synthwave: ["pad", "arp", "bass", "drums"],
  piano: ["keys"],
  bossa: ["guitar", "bass", "drums"],
  ambient: ["pad", "bells"],
  rock: ["guitar", "bass", "drums"],
  edm: ["pad", "arp", "bass", "drums"],
};

const INSTRUMENT_VOICE: Record<string, Voice> = {
  piano: "keys", synth: "pad", guitar: "guitar", bass: "bass", strings: "strings", brass: "brass",
  drums: "drums", harmonica: "harmonica", bells: "bells", "vinyl crackle": "crackle",
};

/** Resolve the musical plan for a spec (pure). */
export function planFromSpec(spec: ThemeProcSpec): { mode: ModeName; groove: Groove; voices: Voice[]; bpm: number; bars: number } {
  const moods = spec.brief.moods.map((m) => m.toLowerCase());
  const genres = spec.brief.genres.map((g) => g.toLowerCase());
  const mode = spec.mode ?? (moods.map((m) => MOOD_MODE[m]).find(Boolean) as ModeName | undefined) ?? "ionian";
  const groove = spec.groove ?? (genres.map((g) => GENRE_GROOVE[g]).find(Boolean) as Groove | undefined) ?? "lofi";
  const voices = new Set<Voice>(GROOVE_VOICES[groove]);
  for (const ins of spec.brief.instruments.map((i) => i.toLowerCase())) {
    const v = INSTRUMENT_VOICE[ins];
    if (!v) continue;
    if (v === "pad" && (groove === "chiptune" || groove === "synthwave" || groove === "edm")) voices.add("arp");
    voices.add(v);
  }
  const bpm = Math.max(60, Math.min(160, Math.round(spec.brief.bpm || 100)));
  return { mode, groove, voices: [...voices], bpm, bars: spec.bars ?? 8 };
}

/** Build the `.proc.json` contents from a character's song brief. */
export function themeSpecFromBrief(seed: string, brief: SongBrief, title?: string): ThemeProcSpec {
  return { kind: "horizon.theme", version: 1, seed, title, brief };
}

export function isThemeProcSpec(x: unknown): x is ThemeProcSpec {
  const o = x as Partial<ThemeProcSpec> | null;
  return !!o && o.kind === "horizon.theme" && o.version === 1 && typeof o.seed === "string" && !!o.brief;
}

export type SystemTrackKind = "main_theme" | "arena" | "ambient_bed";

/** The 3 system tracks (VMD §2.6): Main 100 Dorian synthwave · Arena 128 Phrygian pulse · Bed 60 Lydian pad. */
export const SYSTEM_TRACK_SPECS: Record<SystemTrackKind, ThemeProcSpec> = {
  main_theme: {
    kind: "horizon.theme", version: 1, seed: "horizon-main", title: "Horizon Main Theme", mode: "dorian", groove: "synthwave",
    brief: { genres: ["synthwave"], moods: ["hopeful"], bpm: 100, instruments: ["synth", "bass", "drums", "bells"], vibe: "night drive over the city" },
  },
  arena: {
    kind: "horizon.theme", version: 1, seed: "horizon-arena", title: "Arena", mode: "phrygian", groove: "edm",
    brief: { genres: ["EDM"], moods: ["tense"], bpm: 128, instruments: ["synth", "bass", "drums"], vibe: "debate floor pulse" },
  },
  ambient_bed: {
    kind: "horizon.theme", version: 1, seed: "horizon-bed", title: "Ambient Bed", mode: "lydian", groove: "ambient", bars: 8,
    brief: { genres: ["ambient"], moods: ["dreamy"], bpm: 60, instruments: ["synth", "bells"], vibe: "soft room tone" },
  },
};
