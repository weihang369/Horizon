// Non-session fixtures: settings, catalogues, worlds, songs, memory, knowledge, jobs, variants.
import type {
  AppSettings, GenerationJob, MemoryItem, StylePreset, SystemTrack, ThemeSong, World,
} from "../../../src/contract/types";
import { MODELS } from "../../../src/mock/pricing.config";
import { themeUrl } from "../assets";
import type { CharacterDef } from "./characters";

export const DEFAULT_SETTINGS: AppSettings = {
  openRouterKeyStatus: "missing",
  demoMode: true,
  models: { ...MODELS },
  generationMode: "lean",
  autoGenerateMissingEmotions: false,
  budget: { dailyCapUsd: 1.0, perCharacterCreationCapUsd: 0.6, warnAtPct: 80 },
  energy: { defaultMaxPoints: 1000, usdPerPoint: 0.0001, topUpStepPoints: 500 },
  spentTodayUsd: 0,
  pricing: { period: "off_peak", nextChangeAt: "2026-10-02T01:00:00Z" },
  audio: { masterMuted: false, musicMuted: false, sfxMuted: false, master: 0.8, music: 0.6, sfx: 0.8, duckMusic: true },
  display: { reducedMotion: "system", vfxIntensity: "full", flashIntensity: "full", parallax: true, textSize: "m", speakerCutIns: true },
  chat: { defaultEmotionMode: "llm", responderDefault: "auto", debateAutoAdvance: true, readableDefault: false },
  cost: { showEstimates: true, confirmBeforeGenerate: true, showHud: true },
  presenterMode: false,
  contentRating: "sfw",
};

export const STYLE_PRESETS: StylePreset[] = [
  {
    id: "style_horizon_anime",
    version: 1,
    promptFragment:
      "Modern Japanese anime illustration, clean confident line art, soft cel shading with subtle gradients, bright saturated but natural colours, expressive eyes with glossy highlights, fashionable contemporary clothing with fabric detail, slice-of-life romantic-comedy aesthetic, adult character with adult proportions, waist-up portrait, plain background.",
    referenceImageUrls: [],
  },
];

const SKETCH_CREDIT = "Procedural WebAudio sketch by Horizon (placeholder, D-52)";
export const SYSTEM_TRACKS: SystemTrack[] = [
  { id: "trk_mainTheme", kind: "main_theme", url: "placeholder:system/main_theme", durationSec: 19.2, source: "free_library", credit: SKETCH_CREDIT, licence: "CC0-1.0" },
  { id: "trk_arena", kind: "arena", url: "placeholder:system/arena", durationSec: 15, source: "free_library", credit: SKETCH_CREDIT, licence: "CC0-1.0" },
  { id: "trk_ambientBed", kind: "ambient_bed", url: "placeholder:system/ambient_bed", durationSec: 32, source: "free_library", credit: SKETCH_CREDIT, licence: "CC0-1.0" },
];

export const WORLDS: World[] = [
  {
    id: "wld_seedMeridian", name: "Meridian Council",
    cover: { kind: "preset", presetId: "cover_night_skyline" },
    you: { displayName: "Kai", about: "A policy analyst who convenes the council" },
    characterCount: 3, isSeed: true,
    createdAt: "2026-09-14T08:00:00Z", updatedAt: "2026-10-01T10:08:00Z", lastActiveAt: "2026-10-01T10:08:00Z",
  },
  {
    id: "wld_seedSunnyHollow", name: "Sunny Hollow",
    cover: { kind: "preset", presetId: "cover_sunset_rooftops" },
    you: { displayName: "Kai", about: "Hana's partner of two years; works in IT" },
    characterCount: 3, isSeed: true,
    createdAt: "2026-09-14T08:05:00Z", updatedAt: "2026-09-30T19:06:00Z", lastActiveAt: "2026-09-30T19:06:00Z",
  },
];

export function songsFor(defs: CharacterDef[]): { song: ThemeSong; mock: boolean }[] {
  const out: { song: ThemeSong; mock: boolean }[] = [];
  for (const d of defs) {
    if (!d.song) continue;
    const { bpm } = d.song.brief;
    const durationSec = Math.round(((8 * 4 * 60) / bpm) * 10) / 10;
    out.push({
      mock: d.mock,
      song: {
        id: d.song.id,
        characterId: d.character.id,
        status: "ready",
        url: themeUrl(d.character.id),
        durationSec,
        brief: d.song.brief,
        instrumental: true,
        generation: {
          model: MODELS.music,
          prompt: `Instrumental theme: ${d.song.brief.vibe}. ${d.song.brief.genres.join(", ")}; ${d.song.brief.moods.join(", ")}; ${bpm} BPM; ${d.song.brief.instruments.join(", ")}.`,
          costUsd: 0.04,
        },
        licenseNote: "Placeholder: procedural WebAudio sketch (D-52). The real theme comes from Google Lyria 3 Clip via OpenRouter (provider terms apply).",
      },
    });
  }
  return out;
}

export const MEMORY: MemoryItem[] = [
  { id: "mem_seedAmara1", characterId: "chr_seedAmara", worldId: "wld_seedMeridian", kind: "about_user", text: "Kai cut back on coffee recently; had temple headaches", importance: 0.7, sourceSessionId: "ses_seedAmaraHeadache", sourceMessageId: "msg_seedA04", createdAt: "2026-09-29T21:16:00Z" },
  { id: "mem_seedHana1", characterId: "chr_seedHana", worldId: "wld_seedSunnyHollow", kind: "preference", text: "Kai's favourite cake is yuzu", importance: 0.6, sourceSessionId: "ses_seedHanaLongDay", sourceMessageId: "msg_seedH02", createdAt: "2026-09-30T19:03:00Z" },
  { id: "mem_seedHana2", characterId: "chr_seedHana", worldId: "wld_seedSunnyHollow", kind: "event", text: "Sold Kai's bouquet to a nervous proposer", importance: 0.5, sourceSessionId: "ses_seedHanaLongDay", sourceMessageId: "msg_seedH06", createdAt: "2026-09-30T19:05:00Z" },
  { id: "mem_seedMei1", characterId: "chr_seedMei", worldId: "wld_seedMeridian", kind: "fact", text: "Argued that pilot evidence comes from self-selected firms", importance: 0.8, sourceSessionId: "ses_seedDebate4Day", sourceMessageId: "msg_seedD03", createdAt: "2026-10-01T10:00:30Z" },
  { id: "mem_seedTakeshi1", characterId: "chr_seedTakeshi", worldId: "wld_seedSunnyHollow", kind: "event", text: "Took Rin fishing on a rainy Sunday; first fish named \"Patch Notes\"", importance: 0.6, sourceSessionId: "ses_seedRainySunday", sourceMessageId: "msg_seedW10", createdAt: "2026-09-27T02:45:00Z" },
];
/** Victor and Rin deliberately have no memories (empty state, doc 06 §5). */
export const MEMORY_OWNERS = ["chr_seedAmara", "chr_seedVictor", "chr_seedMei", "chr_seedHana", "chr_seedTakeshi", "chr_seedRin"];

/** D-59: sources and their passages live in ./knowledge (chunks + citedCount are filled by the build). */
export { KNOWLEDGE_SOURCES as KNOWLEDGE } from "./knowledge";

// ── UI-phase jobs (seed/_mock/jobs) ──
export const JOBS: GenerationJob[] = [
  {
    // In-progress emotion set at 3/6 (Standard), shown as the background pill (STATE-02).
    id: "job_mockKenjiEmotions", characterId: "chr_mockKenji", kind: "emotion_set", status: "running", progress: 0.55,
    estimatedCostUsd: 0.234, actualCostUsd: 0.117,
    tasks: [
      { id: "task_mockKenjiHappy", type: "emotion_image", emotion: "happy", status: "succeeded", attempt: 1, maxAttempts: 3, resultRef: "emo_mockKenjiHappy" },
      { id: "task_mockKenjiSad", type: "emotion_image", emotion: "sad", status: "succeeded", attempt: 1, maxAttempts: 3, resultRef: "emo_mockKenjiSad" },
      { id: "task_mockKenjiAngry", type: "emotion_image", emotion: "angry", status: "succeeded", attempt: 1, maxAttempts: 3, resultRef: "emo_mockKenjiAngry" },
      { id: "task_mockKenjiSurprised", type: "emotion_image", emotion: "surprised", status: "running", attempt: 1, maxAttempts: 3 },
      { id: "task_mockKenjiThinking", type: "emotion_image", emotion: "thinking", status: "queued", attempt: 0, maxAttempts: 3 },
      { id: "task_mockKenjiEmbarrassed", type: "emotion_image", emotion: "embarrassed", status: "queued", attempt: 0, maxAttempts: 3 },
    ],
    createdAt: "2026-10-01T11:58:00Z", startedAt: "2026-10-01T11:58:01Z",
  },
  {
    // Failed task + partial emotion set (CHR-08 AC5).
    id: "job_mockAoiEmotions", characterId: "chr_mockAoi", kind: "emotion_set", status: "partial", progress: 1,
    estimatedCostUsd: 0.117, actualCostUsd: 0.078,
    tasks: [
      { id: "task_mockAoiHappy", type: "emotion_image", emotion: "happy", status: "succeeded", attempt: 1, maxAttempts: 3, resultRef: "emo_mockAoiHappy" },
      { id: "task_mockAoiSad", type: "emotion_image", emotion: "sad", status: "failed", attempt: 1, maxAttempts: 3, error: { code: "provider_error", message: "The image provider returned an error.", retryable: true } },
      { id: "task_mockAoiAngry", type: "emotion_image", emotion: "angry", status: "succeeded", attempt: 1, maxAttempts: 3, resultRef: "emo_mockAoiAngry" },
    ],
    createdAt: "2026-09-30T19:20:00Z", startedAt: "2026-09-30T19:20:01Z", finishedAt: "2026-09-30T19:20:34Z",
  },
];

// ── Fixture variants applied by Mock State Switcher scenarios ──
export interface FixtureVariant {
  id: string;
  label: string;
  characterPatches: { characterId: string; energy?: { current: number; state: "active" | "tired" | "exhausted" } }[];
}
export const VARIANTS: FixtureVariant[] = [
  { id: "exhausted_takeshi", label: "Takeshi exhausted (0 ⚡)", characterPatches: [{ characterId: "chr_seedTakeshi", energy: { current: 0, state: "exhausted" } }] },
];
