// Zod schemas for every doc 05 shape (contract rev 1.3). types.ts stays canonical:
// each schema is checked against its type with `satisfies z.ZodType<T>`, so the two cannot drift.
// Objects are strict, so fixture typos fail validation instead of being silently dropped.
import { z } from "zod";
import type {
  AppSettings, Appearance, Character, CharacterProfile, Citation, DebateConfig, DebateState, EmotionAsset, EmotionAssetRef,
  Energy, GenerationJob, GenerationTask, GroupConfig, KnowledgeChunk, KnowledgeSource, MemoryItem, Message, MessageAuthor,
  MessageUsage, Palette, Participant, Reaction, Session, SessionEvent, SongBrief, StylePreset, SystemTrack,
  ThemeSong, TurnCall, TurnTrace, UsageRecord, Verdict, WatchConfig, WatchState, World, YouCard,
} from "./types";
import type { HorizonErrorShape } from "./errors";
import type { GlobalEvent, JobEvent } from "../client/HorizonClient";

const so = z.strictObject;

export const ID_RE = /^[a-z]+_[0-9A-Za-z]{1,40}$/;
// The prefix lives in the regex (not a refinement) so the exported JSON Schema enforces it too.
export const id = (prefix?: string) =>
  prefix
    ? z.string().regex(new RegExp(`^${prefix}_[0-9A-Za-z]{1,40}$`), { message: `id must start with ${prefix}_` })
    : z.string().regex(ID_RE);
export const isoDate = z.string().refine((s) => !Number.isNaN(Date.parse(s)) && /\d{4}-\d{2}-\d{2}T/.test(s), {
  message: "expected an ISO-8601 timestamp",
});
/** Relative asset URL (`/assets/…`), a data URL (wizard placeholders) or a `placeholder:` scheme (audio). */
export const assetUrl = z.string().refine(
  (s) => s.startsWith("/assets/") || s.startsWith("data:") || s.startsWith("placeholder:"),
  { message: "asset URLs must be relative (/assets/…), data: or placeholder:" },
);

// ── Enums ────────────────────────────────────────────────────────────────────
export const EmotionSchema = z.enum(["neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed"]);
export const EmotionSourceSchema = z.enum(["user", "llm", "classifier", "default"]);
export const CharacterStatusSchema = z.enum(["draft", "review", "approved", "archived"]);
export const CreationStepSchema = z.enum(["seed", "profile", "look", "portrait", "emotions", "palette", "theme", "approve"]);
export const SessionModeSchema = z.enum(["one_on_one", "group", "debate", "watch"]);
export const SessionStatusSchema = z.enum(["active", "paused", "ended"]);
export const PausedReasonSchema = z.enum(["user", "turn_cap", "daily_budget", "error", "navigated_away"]);
export const AssetStatusSchema = z.enum(["pending", "generating", "ready", "failed", "rejected"]);
export const VfxPresetSchema = z.enum(["none", "sparkle", "rain", "anger", "shock", "ponder", "blush", "sleep"]);
export const EnergyStateSchema = z.enum(["active", "tired", "exhausted"]);
export const ErrorCodeSchema = z.enum([
  "missing_key", "invalid_key", "insufficient_credits", "rate_limited", "content_refused", "provider_error",
  "daily_budget_exceeded", "creation_budget_exceeded", "energy_exhausted", "timeout", "network",
  "not_found", "validation", "conflict", // rev 1.3
]);
export const DebatePhaseSchema = z.enum(["setup", "opening", "rebuttal", "closing", "verdict", "ended"]);
export const SideSchema = z.enum(["prop", "opp"]);
const PricePeriodSchema = z.enum(["peak", "off_peak"]);

// ── Settings & catalogues ───────────────────────────────────────────────────
const ModelSetSchema = so({ chat: z.string(), decision: z.string(), image: z.string(), music: z.string(), embedding: z.string() });
const unit = z.number().min(0).max(1);
export const AppSettingsSchema = so({
  openRouterKeyStatus: z.enum(["missing", "set", "invalid"]),
  demoMode: z.boolean(),
  models: ModelSetSchema,
  modelOverrides: ModelSetSchema.partial().optional(),
  generationMode: z.enum(["lean", "standard"]),
  autoGenerateMissingEmotions: z.boolean(),
  budget: so({ dailyCapUsd: z.number().positive(), perCharacterCreationCapUsd: z.number().positive(), warnAtPct: z.number().min(1).max(100) }),
  energy: so({
    defaultMaxPoints: z.number().int().positive(), usdPerPoint: z.number().positive(), topUpStepPoints: z.number().int().positive(),
    estReplyPoints: so({ off_peak: z.number().positive(), peak: z.number().positive() }), // rev 1.3 (D-78)
  }),
  spentTodayUsd: z.number().min(0),
  pricing: so({ period: PricePeriodSchema, nextChangeAt: isoDate }),
  audio: so({
    masterMuted: z.boolean(), musicMuted: z.boolean(), sfxMuted: z.boolean(),
    master: unit, music: unit, sfx: unit, duckMusic: z.boolean(),
  }),
  display: so({
    reducedMotion: z.enum(["system", "on", "off"]), vfxIntensity: z.enum(["off", "subtle", "full"]),
    flashIntensity: z.enum(["off", "low", "full"]), parallax: z.boolean(), textSize: z.enum(["s", "m", "l"]),
    speakerCutIns: z.boolean(),
  }),
  chat: so({
    defaultEmotionMode: z.enum(["llm", "user"]), responderDefault: z.enum(["auto", "everyone", "mentioned"]),
    debateAutoAdvance: z.boolean(), readableDefault: z.boolean(),
  }),
  cost: so({ showEstimates: z.boolean(), confirmBeforeGenerate: z.boolean(), showHud: z.boolean() }),
  presenterMode: z.boolean(),
  contentRating: z.literal("sfw"),
}) satisfies z.ZodType<AppSettings>;

export const StylePresetSchema = so({
  id: z.string(), version: z.number().int().positive(), promptFragment: z.string(), referenceImageUrls: z.array(z.string()),
}) satisfies z.ZodType<StylePreset>;

const hex = z.string().regex(/^#[0-9A-Fa-f]{6}$/);
export const PaletteSchema = so({
  id: z.string().startsWith("pal_"), name: z.string(),
  primary: hex, secondary: hex, accent: hex, stage: hex, surface: hex, onPrimary: hex, glow: hex, text: hex,
  fit: z.string().optional(),
}) satisfies z.ZodType<Palette>;

const LoopSchema = so({ startSec: z.number().min(0), endSec: z.number().positive() });
export const SystemTrackSchema = so({
  id: id("trk"), kind: z.enum(["main_theme", "arena", "ambient_bed"]), url: assetUrl, durationSec: z.number().positive(),
  loop: LoopSchema.optional(), gainDb: z.number().optional(),
  source: z.literal("free_library"), credit: z.string(), licence: z.string(),
}) satisfies z.ZodType<SystemTrack>;

// ── World ───────────────────────────────────────────────────────────────────
export const YouCardSchema = so({ displayName: z.string().min(1).max(30), about: z.string().max(160).optional() }) satisfies z.ZodType<YouCard>;
export const WorldSchema = so({
  id: id("wld"), name: z.string().min(1).max(40),
  cover: so({ kind: z.enum(["preset", "upload", "generated"]), presetId: z.string().optional(), url: z.string().optional() }),
  you: YouCardSchema.optional(),
  characterCount: z.number().int().min(0),
  isSeed: z.boolean(),
  createdAt: isoDate, updatedAt: isoDate, lastActiveAt: isoDate,
}) satisfies z.ZodType<World>;

// ── Character ───────────────────────────────────────────────────────────────
export const EmotionAssetRefSchema = so({ assetId: id("emo"), url: assetUrl, vfxPreset: VfxPresetSchema }) satisfies z.ZodType<EmotionAssetRef>;
export const EnergySchema = so({
  max: z.number().int().positive(), current: z.number().min(0), asOf: isoDate, regenPerHour: z.number().min(0),
  state: EnergyStateSchema, fullAt: isoDate.optional(), spentToday: z.number().min(0),
}) satisfies z.ZodType<Energy>;
export const CharacterProfileSchema = so({
  name: z.string().min(1), title: z.string().optional(), role: z.string().min(1),
  age: z.number().int().min(18),
  pronouns: z.string().optional(), tagline: z.string().max(80),
  personality: so({ summary: z.string(), traits: z.array(z.string()).min(3).max(8) }),
  backstory: z.string(),
  speakingStyle: so({
    summary: z.string(), tone: z.string(), formality: z.enum(["casual", "neutral", "formal"]),
    quirks: z.array(z.string()), catchphrases: z.array(z.string()),
  }),
  expertise: z.array(z.string()),
  goals: z.string().optional(),
  boundaries: z.array(z.string()),
  greeting: z.string(),
  exampleLines: z.array(z.string()).max(3).optional(),
  relationshipToUser: z.string().optional(),
  systemPromptPreview: z.string().optional(),
}) satisfies z.ZodType<CharacterProfile>;
export const AppearanceSchema = so({
  attributes: so({
    body: so({ ageBand: z.enum(["young_adult", "adult", "middle_aged", "senior"]), build: z.string(), height: z.string(), skinTone: z.string() }),
    face: so({ shape: z.string(), baseline: z.enum(["soft", "neutral", "sharp"]), marks: z.array(z.string()) }),
    eyes: so({ shape: z.string(), color: z.string(), glasses: z.enum(["none", "round", "square", "half_rim"]) }),
    hair: so({ length: z.string(), style: z.string(), color: z.string(), streakColor: z.string().optional(), fringe: z.string() }),
    outfit: so({ archetype: z.string(), primaryColor: z.string(), secondaryColor: z.string() }),
    accessories: z.array(z.string()).max(3),
    vibe: z.array(z.string()).max(2),
    extraDetails: z.string().optional(),
  }),
  appearanceSummary: z.string(),
  basePortraitUrl: assetUrl.optional(),
  candidates: z.array(so({ id: z.string(), url: assetUrl, selected: z.boolean(), status: AssetStatusSchema })),
  stylePresetId: z.string(), stylePresetVersion: z.number().int().positive(),
}) satisfies z.ZodType<Appearance>;

const emotionsRecord = z.strictObject({
  neutral: EmotionAssetRefSchema.nullable(), happy: EmotionAssetRefSchema.nullable(), sad: EmotionAssetRefSchema.nullable(),
  angry: EmotionAssetRefSchema.nullable(), surprised: EmotionAssetRefSchema.nullable(),
  thinking: EmotionAssetRefSchema.nullable(), embarrassed: EmotionAssetRefSchema.nullable(),
});
export const CharacterSchema = so({
  id: id("chr"), worldId: id("wld"),
  status: CharacterStatusSchema,
  creationStep: CreationStepSchema.optional(),
  seedPrompt: z.string(),
  intent: z.enum(["expert", "companion", "other"]),
  advisory: z.boolean(),
  profile: CharacterProfileSchema,
  profileMeta: so({ editedFields: z.array(z.string()) }).optional(),
  appearance: AppearanceSchema,
  paletteId: z.string().startsWith("pal_"),
  emotionSet: z.array(EmotionSchema),
  emotions: emotionsRecord,
  blink: EmotionAssetRefSchema.nullable().optional(),
  themeSongId: id("song").optional(),
  energy: EnergySchema,
  activeJobId: id("job").optional(),
  version: z.number().int().positive(),
  isSeed: z.boolean(),
  createdAt: isoDate, updatedAt: isoDate, approvedAt: isoDate.optional(), archivedAt: isoDate.optional(), deletedAt: isoDate.optional(),
}) satisfies z.ZodType<Character>;

export const EmotionAssetSchema = so({
  id: id("emo"), characterId: id("chr"), emotion: EmotionSchema,
  variant: z.enum(["default", "blink"]),
  status: AssetStatusSchema,
  url: assetUrl.optional(), width: z.number().optional(), height: z.number().optional(),
  format: z.enum(["webp", "avif"]).optional(), bytes: z.number().optional(),
  vfxPreset: VfxPresetSchema,
  generation: so({
    model: z.string(), technique: z.enum(["reference_edit", "expression_sheet", "prompt_only", "manual"]),
    prompt: z.string(), referenceUrls: z.array(z.string()), seed: z.number().optional(), costUsd: z.number(), jobId: z.string().optional(),
  }).optional(),
  version: z.number().int().positive(), isActive: z.boolean(),
}) satisfies z.ZodType<EmotionAsset>;

export const SongBriefSchema = so({
  genres: z.array(z.string()), moods: z.array(z.string()), bpm: z.number().min(60).max(160),
  instruments: z.array(z.string()), vibe: z.string(),
}) satisfies z.ZodType<SongBrief>;
export const ThemeSongSchema = so({
  id: id("song"), characterId: id("chr"), status: AssetStatusSchema,
  url: assetUrl.optional(), durationSec: z.number().optional(), format: z.enum(["opus", "aac", "mp3"]).optional(), bytes: z.number().optional(),
  loop: LoopSchema.optional(), gainDb: z.number().optional(),
  brief: SongBriefSchema,
  instrumental: z.boolean(),
  generation: so({ model: z.string(), prompt: z.string(), costUsd: z.number(), jobId: z.string().optional() }).optional(),
  licenseNote: z.string(),
}) satisfies z.ZodType<ThemeSong>;

// ── Session ─────────────────────────────────────────────────────────────────
export const ParticipantSchema = so({
  characterId: id("chr"), role: z.enum(["speaker", "debater"]), side: SideSchema.nullable().optional(),
  currentEmotion: EmotionSchema, mutedByUser: z.boolean(),
}) satisfies z.ZodType<Participant>;
export const GroupConfigSchema = so({
  responderPolicy: z.enum(["auto", "everyone", "mentioned"]), maxAutoResponders: z.literal(2),
}) satisfies z.ZodType<GroupConfig>;
export const DebateConfigSchema = so({
  motion: z.string().min(1).max(200),
  format: z.enum(["two_sided", "panel"]),
  sides: so({ prop: z.array(id("chr")), opp: z.array(id("chr")) }).optional(),
  roundsPreset: z.enum(["quick", "standard"]),
  phases: z.array(z.enum(["opening", "rebuttal", "closing"])),
  turnLength: z.enum(["short", "medium", "long"]),
  moderator: z.enum(["user", "auto_host"]),
  verdictBy: z.enum(["arbiter", "user", "none"]),
  rubric: z.array(so({ id: z.string(), label: z.string() })).min(2).max(6),
  autoAdvance: z.boolean(), pauseMs: z.number().min(0),
}) satisfies z.ZodType<DebateConfig>;
export const VerdictSchema = so({
  decidedBy: z.enum(["arbiter", "user", "none"]),
  strongerCase: SideSchema.nullable().optional(),
  scoresBy: z.enum(["side", "debater"]).optional(),
  scores: z.array(so({ subjectId: z.string(), criterionId: z.string(), value: z.number().min(0).max(10) })).optional(),
  summary: z.array(so({ subjectId: z.string(), points: z.array(z.string()) })),
  keyDisagreement: z.string().optional(),
  rationale: z.string().optional(),
}) satisfies z.ZodType<Verdict>;
export const DebateStateSchema = so({
  phase: DebatePhaseSchema, round: z.number().int().min(0), iteration: z.number().int().min(0),
  nextSpeakerId: z.string().optional(), verdict: VerdictSchema.optional(),
}) satisfies z.ZodType<DebateState>;
export const WatchConfigSchema = so({
  premise: z.string().min(1).max(300),
  maxTurns: z.union([z.literal(10), z.literal(20), z.literal(40)]),
  paceMs: z.union([z.literal(3000), z.literal(1500), z.literal(500)]),
  openingSpeaker: z.string(),
}) satisfies z.ZodType<WatchConfig>;
export const WatchStateSchema = so({
  status: z.enum(["playing", "paused", "ended"]), turnsTaken: z.number().int().min(0), turnLimit: z.number().int().min(0),
  nextSpeakerId: z.string().optional(),
}) satisfies z.ZodType<WatchState>;

export const SessionSchema = so({
  id: id("ses"), worldId: id("wld"),
  title: z.string(), titleIsCustom: z.boolean(),
  mode: SessionModeSchema, status: SessionStatusSchema, pausedReason: PausedReasonSchema.optional(),
  participants: z.array(ParticipantSchema).min(1).max(5),
  emotionMode: z.enum(["llm", "user"]),
  musicPolicy: z.enum(["character_theme", "follow_speaker", "arena", "scene_bed"]),
  readableMode: z.boolean(),
  config: z.union([GroupConfigSchema, DebateConfigSchema, WatchConfigSchema]).nullable(),
  state: z.union([DebateStateSchema, WatchStateSchema]).nullable(),
  continuedFrom: id("ses").optional(),
  isSeed: z.boolean(),
  costUsd: z.number().min(0), messageCount: z.number().int().min(0),
  createdAt: isoDate, updatedAt: isoDate, lastMessageAt: isoDate.optional(),
}) satisfies z.ZodType<Session>;

// ── Message & trace ─────────────────────────────────────────────────────────
export const MessageAuthorSchema = so({
  type: z.enum(["user", "character", "host", "system"]), characterId: id("chr").optional(),
}) satisfies z.ZodType<MessageAuthor>;
export const ReactionSchema = so({ characterId: id("chr"), emotion: EmotionSchema, p: unit.optional(), at: isoDate }) satisfies z.ZodType<Reaction>;
export const MessageUsageSchema = so({
  tokensIn: z.number().int().min(0), tokensCached: z.number().int().min(0).optional(), tokensOut: z.number().int().min(0),
  costUsd: z.number().min(0), energySpent: z.number().int().min(0).optional(),
  firstTokenMs: z.number().min(0), totalMs: z.number().min(0),
}) satisfies z.ZodType<MessageUsage>;
const SkipReasonSchema = z.enum(["exhausted", "muted", "archived"]);
export const TurnCallSchema = so({
  purpose: z.string().min(1), model: z.string(), costUsd: z.number().min(0), latencyMs: z.number().min(0), fallback: z.boolean().optional(),
}) satisfies z.ZodType<TurnCall>;
export const TurnTraceSchema = so({
  messageId: id("msg"),
  model: so({
    id: z.string(), provider: z.string(), quantization: z.string().optional(), pricePeriod: PricePeriodSchema.optional(),
    latencyMs: so({ firstToken: z.number(), total: z.number() }),
    tokensIn: z.number().int(), tokensCached: z.number().int().optional(), tokensOut: z.number().int(), costUsd: z.number(),
  }).optional(),
  energy: so({ characterId: id("chr"), spent: z.number().int().min(0), remaining: z.number().min(0), max: z.number().int().positive() }).optional(),
  emotion: so({
    chosen: EmotionSchema, source: EmotionSourceSchema,
    candidates: z.array(so({ label: EmotionSchema, p: unit })).optional(),
  }).optional(),
  routing: so({
    question: z.string().optional(), selected: z.string(),
    forcedBy: z.enum(["user_ask", "mention", "nudge", "round_order"]).optional(),
    candidates: z.array(so({ characterId: id("chr"), p: unit })).optional(),
    skipped: z.array(so({ characterId: id("chr"), reason: SkipReasonSchema })).optional(),
    reason: z.string().optional(),
  }).optional(),
  memory: so({
    recalled: z.array(so({ memoryItemId: z.string(), text: z.string(), sourceSessionId: z.string().optional(), score: z.number().optional() })),
  }).optional(),
  knowledge: so({
    query: z.string().optional(),
    trigger: z.enum(["always", "tool_call", "gated"]).optional(),
    retrieved: z.array(so({
      chunkId: z.string().regex(ID_RE), sourceId: z.string().regex(ID_RE), title: z.string(), locator: z.string().optional(),
      text: z.string(), score: unit, cited: z.boolean(), n: z.number().int().positive().optional(),
    })),
  }).optional(),
  contextInSession: z.array(so({ text: z.string(), messageId: id("msg") })).optional(),
  context: so({
    budget: z.number().int().positive(), cacheHitPct: z.number().min(0).max(100).optional(),
    used: so({
      system: z.number().int(), persona: z.number().int(), memory: z.number().int(), knowledge: z.number().int(),
      history: z.number().int(), user: z.number().int(), mode: z.number().int(),
    }),
  }).optional(),
  guardrail: so({ checks: z.array(so({ name: z.string(), verdict: z.enum(["pass", "flag", "block"]), p: unit.optional() })) }).optional(),
  graph: so({ path: z.array(z.string()) }).optional(),
  calls: z.array(TurnCallSchema).optional(), // rev 1.3
}) satisfies z.ZodType<TurnTrace>;

export const CitationSchema = so({
  n: z.number().int().positive(), sourceId: z.string().regex(ID_RE), title: z.string(), type: z.enum(["text", "file", "url"]),
  chunkId: z.string().regex(ID_RE), locator: z.string().optional(), quote: z.string().min(1).max(400), score: unit.optional(),
}) satisfies z.ZodType<Citation>;

export const MessageSchema = so({
  id: id("msg"), sessionId: id("ses"), seq: z.number().int().positive(),
  author: MessageAuthorSchema,
  kind: z.enum(["chat", "steer", "interject", "direction", "narration", "summary", "verdict", "system_note"]),
  targetCharacterId: id("chr").optional(),
  content: z.string(),
  status: z.enum(["streaming", "complete", "interrupted", "error"]),
  interruptedBy: z.enum(["user", "error"]).optional(),
  emotion: EmotionSchema.optional(), emotionSource: EmotionSourceSchema.optional(),
  debate: so({ phase: DebatePhaseSchema, round: z.number().int(), iteration: z.number().int(), side: SideSchema.optional() }).optional(),
  forcedSpeaker: z.boolean().optional(),
  reactions: z.array(ReactionSchema).optional(),
  variants: z.array(so({ id: z.string(), content: z.string(), emotion: EmotionSchema.optional(), createdAt: isoDate })).optional(),
  activeVariantId: z.string().optional(),
  usage: MessageUsageSchema.optional(),
  trace: TurnTraceSchema.optional(),
  citations: z.array(CitationSchema).optional(),
  error: so({ code: ErrorCodeSchema, message: z.string(), retryable: z.boolean() }).optional(),
  createdAt: isoDate,
}) satisfies z.ZodType<Message>;

// ── Streaming events ────────────────────────────────────────────────────────
const evtBase = { id: id("evt"), sessionId: id("ses"), seq: z.number().int().positive(), at: isoDate };
const ev = <T extends string, P extends z.ZodType>(type: T, payload: P) =>
  so({ ...evtBase, type: z.literal(type), payload });
const skipped = z.array(so({ characterId: id("chr"), reason: SkipReasonSchema }));
const PartialMessageSchema = MessageSchema.partial();

export const SessionEventSchema = z.discriminatedUnion("type", [
  ev("turn.next", so({ nextSpeakerId: z.string(), forcedBy: z.string().optional(), skipped: skipped.optional() })),
  ev("turn.thinking", so({ characterId: id("chr") })),
  ev("turn.start", so({
    messageId: id("msg"), author: MessageAuthorSchema, emotion: EmotionSchema.optional(), variantId: z.string().optional(),
    message: PartialMessageSchema.optional(),
  })),
  ev("token", so({ messageId: id("msg"), delta: z.string(), variantId: z.string().optional() })),
  ev("emotion", so({ messageId: id("msg").optional(), characterId: id("chr"), emotion: EmotionSchema, source: EmotionSourceSchema })),
  ev("turn.end", so({
    messageId: id("msg"), status: z.enum(["streaming", "complete", "interrupted", "error"]),
    interruptedBy: z.enum(["user", "error"]).optional(), usage: MessageUsageSchema.optional(), variantId: z.string().optional(),
    citations: z.array(CitationSchema).optional(),
  })),
  ev("energy", so({
    characterId: id("chr"), current: z.number().min(0), max: z.number().int().positive(), state: EnergyStateSchema,
    fullAt: isoDate.optional(), spent: z.number().int().min(0).optional(),
  })),
  ev("reaction", so({ messageId: id("msg"), characterId: id("chr"), emotion: EmotionSchema, p: unit.optional(), source: EmotionSourceSchema })),
  ev("insight", so({ messageId: id("msg"), trace: TurnTraceSchema })),
  ev("phase", so({ phase: DebatePhaseSchema, round: z.number().int().min(0), iteration: z.number().int().min(0) })),
  ev("watch.state", so({
    status: z.enum(["playing", "paused", "ended"]), paceMs: z.number(), turnsTaken: z.number().int(), turnLimit: z.number().int(),
  })),
  ev("session.paused", so({ reason: PausedReasonSchema.optional() })),
  ev("session.resumed", so({ reason: z.string().optional() })),
  ev("budget.warning", so({ scope: z.enum(["daily", "creation"]), spentUsd: z.number(), capUsd: z.number() })),
  ev("error", so({ code: ErrorCodeSchema, message: z.string(), retryable: z.boolean(), messageId: id("msg").optional() })),
  ev("message", so({ message: MessageSchema })),
  ev("session.state", so({
    status: SessionStatusSchema.optional(), pausedReason: PausedReasonSchema.optional(),
    state: z.union([DebateStateSchema, WatchStateSchema]).optional(),
    participants: z.array(ParticipantSchema).optional(),
    settings: SessionSchema.pick({
      title: true, titleIsCustom: true, emotionMode: true, musicPolicy: true, readableMode: true, config: true,
    }).partial().optional(), // D-57
  })),
]) satisfies z.ZodType<SessionEvent>;

// ── Jobs, ledger, memory, knowledge ─────────────────────────────────────────
const errObj = so({ code: ErrorCodeSchema, message: z.string(), retryable: z.boolean() });
export const GenerationTaskSchema = so({
  id: id("task"),
  type: z.enum(["profile", "appearance_summary", "palette_pick", "portrait_candidate", "emotion_image", "expression_sheet", "blink_frame", "song_brief", "theme_song"]),
  emotion: EmotionSchema.optional(),
  status: z.enum(["queued", "running", "succeeded", "failed", "skipped"]),
  attempt: z.number().int().min(0), maxAttempts: z.number().int().min(1).max(3),
  resultRef: z.string().optional(), previewUrl: z.string().optional(),
  error: errObj.optional(),
}) satisfies z.ZodType<GenerationTask>;
export const GenerationJobSchema = so({
  id: id("job"), characterId: id("chr"),
  kind: z.enum(["profile_draft", "profile_regenerate", "portrait_candidates", "portrait_tweak", "emotion_set", "emotion_regenerate", "song"]),
  targetField: z.string().optional(),
  status: z.enum(["queued", "running", "succeeded", "partial", "failed", "cancelled"]),
  progress: unit,
  estimatedCostUsd: z.number().min(0), actualCostUsd: z.number().min(0),
  tasks: z.array(GenerationTaskSchema),
  error: so({ code: ErrorCodeSchema, message: z.string() }).optional(),
  createdAt: isoDate, startedAt: isoDate.optional(), finishedAt: isoDate.optional(),
}) satisfies z.ZodType<GenerationJob>;
export const UsageRecordSchema = so({
  id: z.string(), at: isoDate,
  category: z.enum(["chat", "decision", "image", "music", "profile", "summary", "memory", "embedding", "energy_topup"]),
  model: z.string().optional(), provider: z.string().optional(), pricePeriod: PricePeriodSchema.optional(),
  sessionId: z.string().optional(), characterId: z.string().optional(), jobId: z.string().optional(),
  tokensIn: z.number().int().optional(), tokensCached: z.number().int().optional(), tokensOut: z.number().int().optional(),
  costUsd: z.number().min(0), estimatedCostUsd: z.number().min(0).optional(), energyPoints: z.number().int().optional(), latencyMs: z.number().optional(),
}) satisfies z.ZodType<UsageRecord>;
export const MemoryItemSchema = so({
  id: id("mem"), characterId: id("chr"), worldId: id("wld"),
  kind: z.enum(["fact", "event", "preference", "about_user"]),
  text: z.string(), importance: unit, sourceSessionId: z.string().optional(), sourceMessageId: z.string().optional(), createdAt: isoDate,
}) satisfies z.ZodType<MemoryItem>;
export const KnowledgeSourceSchema = so({
  id: id("kno"), characterId: id("chr"), worldId: id("wld"), title: z.string(),
  type: z.enum(["text", "file", "url"]), // "url" = legacy, read-only (rev 1.3)
  status: z.enum(["indexing", "indexed", "keyword_only", "failed"]), bytes: z.number().optional(),
  pages: z.number().int().positive().optional(), chunks: z.number().int().min(0).optional(), url: z.string().optional(),
  citedCount: z.number().int().min(0).optional(), addedAt: isoDate.optional(), error: z.string().optional(),
}) satisfies z.ZodType<KnowledgeSource>;

export const KnowledgeChunkSchema = so({
  id: id("kch"), sourceId: id("kno"), index: z.number().int().min(0), locator: z.string().optional(), text: z.string().min(1),
}) satisfies z.ZodType<KnowledgeChunk>;

// ── Client surface: error envelope, job and global events (rev 1.3) ─────────
// The backend emits these over HTTP/SSE, so they are part of the exported JSON Schema too.
export const HorizonErrorShapeSchema = so({
  code: ErrorCodeSchema, message: z.string(), retryable: z.boolean(),
  retryAfterSec: z.number().min(0).optional(), details: z.record(z.string(), z.unknown()).optional(),
}) satisfies z.ZodType<HorizonErrorShape>;

export const JobEventSchema = z.discriminatedUnion("type", [
  so({ type: z.literal("job.progress"), job: GenerationJobSchema }),
  so({ type: z.literal("task.update"), jobId: id("job"), task: GenerationTaskSchema }),
  so({ type: z.literal("job.done"), job: GenerationJobSchema }),
]) satisfies z.ZodType<JobEvent>;

const BudgetScopeSchema = z.enum(["daily", "creation"]);
export const GlobalEventSchema = z.discriminatedUnion("type", [
  so({
    type: z.literal("entity.changed"),
    kind: z.enum(["settings", "world", "character", "session", "usage", "memory", "knowledge", "job"]),
    id: z.string().optional(), worldId: z.string().optional(),
    progress: so({ stage: z.enum(["extracting", "chunking", "embedding"]), pct: unit }).optional(),
  }),
  so({ type: z.literal("budget.warning"), scope: BudgetScopeSchema, spentUsd: z.number(), capUsd: z.number() }),
  so({
    type: z.literal("budget.reached"), scope: BudgetScopeSchema, spentUsd: z.number(), capUsd: z.number(),
    sessionId: z.string().optional(), jobId: z.string().optional(),
  }),
  so({ type: z.literal("job.progress"), job: GenerationJobSchema }),
  so({ type: z.literal("task.update"), jobId: id("job"), task: GenerationTaskSchema }),
  so({ type: z.literal("job.done"), job: GenerationJobSchema, characterName: z.string().optional() }),
  so({ type: z.literal("error"), error: HorizonErrorShapeSchema, context: z.string().optional() }),
  so({ type: z.literal("mock.reset") }),
]) satisfies z.ZodType<GlobalEvent>;

// ── Fixture files ───────────────────────────────────────────────────────────
// Every seed file is `{ "schemaVersion": 1, "data": … }` (doc 05 §1: fixtures carry schemaVersion at the root).
export const fixtureFile = <T extends z.ZodType>(inner: T) => so({ schemaVersion: z.literal(1), data: inner });
export interface FixtureFile<T> { schemaVersion: 1; data: T }
