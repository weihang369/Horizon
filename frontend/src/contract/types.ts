// Horizon data contract v1.0: a direct transcription of docs/requirements/05-data-contract.md.
// The mock, the FastAPI backend and the AI layer all share these wire shapes.
// Do not change a shape here without updating doc 05 (and bumping SCHEMA_VERSION).

export const SCHEMA_VERSION = 1;

// ── Enums ────────────────────────────────────────────────────────────────────
export type Emotion = "neutral" | "happy" | "sad" | "angry" | "surprised" | "thinking" | "embarrassed";
export const EMOTIONS: Emotion[] = ["neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed"];
export type EmotionSource = "user" | "llm" | "classifier" | "default";
export type CharacterStatus = "draft" | "review" | "approved" | "archived";
export type CreationStep = "seed" | "profile" | "look" | "portrait" | "emotions" | "palette" | "theme" | "approve";
export const CREATION_STEPS: CreationStep[] = ["seed", "profile", "look", "portrait", "emotions", "palette", "theme", "approve"];
export type SessionMode = "one_on_one" | "group" | "debate" | "watch";
export type SessionStatus = "active" | "paused" | "ended";
export type PausedReason = "user" | "turn_cap" | "daily_budget" | "error" | "navigated_away";
export type AssetStatus = "pending" | "generating" | "ready" | "failed" | "rejected";
export type VfxPreset = "none" | "sparkle" | "rain" | "anger" | "shock" | "ponder" | "blush" | "sleep";
export type EnergyState = "active" | "tired" | "exhausted";
export type ErrorCode =
  | "missing_key" | "invalid_key" | "insufficient_credits" | "rate_limited" | "content_refused"
  | "provider_error" | "daily_budget_exceeded" | "creation_budget_exceeded" | "energy_exhausted"
  | "timeout" | "network";
export type DebatePhase = "setup" | "opening" | "rebuttal" | "closing" | "verdict" | "ended";
export type Side = "prop" | "opp";

// ── AppSettings ─────────────────────────────────────────────────────────────
export interface ModelSet { chat: string; decision: string; image: string; music: string }
export interface AppSettings {
  openRouterKeyStatus: "missing" | "set" | "invalid";
  demoMode: boolean;
  models: ModelSet;
  modelOverrides?: Partial<ModelSet>;
  generationMode: "lean" | "standard";
  autoGenerateMissingEmotions: boolean;
  budget: { dailyCapUsd: number; perCharacterCreationCapUsd: number; warnAtPct: number };
  energy: { defaultMaxPoints: number; usdPerPoint: number; topUpStepPoints: number };
  spentTodayUsd: number;
  pricing: { period: "peak" | "off_peak"; nextChangeAt: string }; // D-51
  audio: {
    masterMuted: boolean; musicMuted: boolean; sfxMuted: boolean;
    master: number; music: number; sfx: number; duckMusic: boolean;
  };
  display: {
    reducedMotion: "system" | "on" | "off"; vfxIntensity: "off" | "subtle" | "full";
    flashIntensity: "off" | "low" | "full"; parallax: boolean; textSize: "s" | "m" | "l"; speakerCutIns: boolean;
  };
  chat: {
    defaultEmotionMode: "llm" | "user"; responderDefault: "auto" | "everyone" | "mentioned";
    debateAutoAdvance: boolean; readableDefault: boolean;
  };
  cost: { showEstimates: boolean; confirmBeforeGenerate: boolean; showHud: boolean };
  presenterMode: boolean;
  contentRating: "sfw";
}

// ── Global catalogues ───────────────────────────────────────────────────────
export interface StylePreset { id: string; version: number; promptFragment: string; referenceImageUrls: string[] }
export interface Palette {
  id: string; name: string;
  primary: string; secondary: string; accent: string; stage: string; surface: string;
  onPrimary: string; glow: string; text: string;
  fit?: string;
}
export interface SystemTrack {
  id: string; kind: "main_theme" | "arena" | "ambient_bed"; url: string; durationSec: number;
  loop?: { startSec: number; endSec: number }; gainDb?: number;
  source: "free_library"; credit: string; licence: string;
}

// ── World ───────────────────────────────────────────────────────────────────
export interface YouCard { displayName: string; about?: string }
export interface World {
  id: string; name: string;
  cover: { kind: "preset" | "upload" | "generated"; presetId?: string; url?: string };
  you?: YouCard;
  characterCount: number;
  isSeed: boolean;
  createdAt: string; updatedAt: string; lastActiveAt: string;
}

// ── Character ───────────────────────────────────────────────────────────────
export interface EmotionAssetRef { assetId: string; url: string; vfxPreset: VfxPreset }
export interface Energy {
  max: number; current: number; asOf: string; regenPerHour: number;
  state: EnergyState; fullAt?: string; spentToday: number;
}
export interface CharacterProfile {
  name: string; title?: string; role: string; age: number; pronouns?: string; tagline: string;
  personality: { summary: string; traits: string[] };
  backstory: string;
  speakingStyle: {
    summary: string; tone: string; formality: "casual" | "neutral" | "formal";
    quirks: string[]; catchphrases: string[];
  };
  expertise: string[];
  goals?: string;
  boundaries: string[];
  greeting: string;
  exampleLines?: string[];
  relationshipToUser?: string;
  systemPromptPreview?: string;
}
export type AgeBand = "young_adult" | "adult" | "middle_aged" | "senior";
export interface Appearance {
  attributes: {
    body: { ageBand: AgeBand; build: string; height: string; skinTone: string };
    face: { shape: string; baseline: "soft" | "neutral" | "sharp"; marks: string[] };
    eyes: { shape: string; color: string; glasses: "none" | "round" | "square" | "half_rim" };
    hair: { length: string; style: string; color: string; streakColor?: string; fringe: string };
    outfit: { archetype: string; primaryColor: string; secondaryColor: string };
    accessories: string[];
    vibe: string[];
    extraDetails?: string;
  };
  appearanceSummary: string;
  basePortraitUrl?: string;
  candidates: { id: string; url: string; selected: boolean; status: AssetStatus }[];
  stylePresetId: string; stylePresetVersion: number;
}
export interface Character {
  id: string; worldId: string;
  status: CharacterStatus;
  creationStep?: CreationStep;
  seedPrompt: string;
  intent: "expert" | "companion" | "other";
  advisory: boolean;
  profile: CharacterProfile;
  profileMeta?: { editedFields: string[] };
  appearance: Appearance;
  paletteId: string;
  emotionSet: Emotion[];
  emotions: Record<Emotion, EmotionAssetRef | null>;
  blink?: EmotionAssetRef | null;
  themeSongId?: string;
  energy: Energy;
  activeJobId?: string;
  version: number;
  isSeed: boolean;
  createdAt: string; updatedAt: string; approvedAt?: string; archivedAt?: string; deletedAt?: string;
}

export interface EmotionAsset {
  id: string; characterId: string; emotion: Emotion;
  variant: "default" | "blink";
  status: AssetStatus;
  url?: string; width?: number; height?: number; format?: "webp" | "avif"; bytes?: number;
  vfxPreset: VfxPreset;
  generation?: {
    model: string; technique: "reference_edit" | "expression_sheet" | "prompt_only" | "manual";
    prompt: string; referenceUrls: string[]; seed?: number; costUsd: number; jobId?: string;
  };
  version: number; isActive: boolean;
}

export interface SongBrief { genres: string[]; moods: string[]; bpm: number; instruments: string[]; vibe: string }
export interface ThemeSong {
  id: string; characterId: string; status: AssetStatus;
  url?: string; durationSec?: number; format?: "opus" | "aac" | "mp3"; bytes?: number;
  loop?: { startSec: number; endSec: number };
  gainDb?: number;
  brief: SongBrief;
  instrumental: boolean;
  generation?: { model: string; prompt: string; costUsd: number; jobId?: string };
  licenseNote: string;
}

// ── Session ─────────────────────────────────────────────────────────────────
export interface Participant {
  characterId: string; role: "speaker" | "debater"; side?: Side | null;
  currentEmotion: Emotion; mutedByUser: boolean;
}
export interface GroupConfig { responderPolicy: "auto" | "everyone" | "mentioned"; maxAutoResponders: 2 }
export type DebateTurnPhase = "opening" | "rebuttal" | "closing";
export interface DebateConfig {
  motion: string;
  format: "two_sided" | "panel";
  sides?: { prop: string[]; opp: string[] };
  roundsPreset: "quick" | "standard";
  phases: DebateTurnPhase[];
  turnLength: "short" | "medium" | "long";
  moderator: "user" | "auto_host";
  verdictBy: "arbiter" | "user" | "none";
  rubric: { id: string; label: string }[];
  autoAdvance: boolean; pauseMs: number;
}
export interface Verdict {
  decidedBy: "arbiter" | "user" | "none";
  strongerCase?: Side | null;
  scoresBy?: "side" | "debater";
  scores?: { subjectId: string; criterionId: string; value: number }[];
  summary: { subjectId: string; points: string[] }[];
  keyDisagreement?: string;
  rationale?: string;
}
export interface DebateState {
  phase: DebatePhase; round: number; iteration: number;
  nextSpeakerId?: string;
  verdict?: Verdict;
}
export interface WatchConfig {
  premise: string; maxTurns: 10 | 20 | 40; paceMs: 3000 | 1500 | 500; openingSpeaker: "auto" | string;
}
export interface WatchState {
  status: "playing" | "paused" | "ended"; turnsTaken: number; turnLimit: number; nextSpeakerId?: string;
}
export type MusicPolicy = "character_theme" | "follow_speaker" | "arena" | "scene_bed";
export interface Session {
  id: string; worldId: string;
  title: string; titleIsCustom: boolean;
  mode: SessionMode; status: SessionStatus; pausedReason?: PausedReason;
  participants: Participant[];
  emotionMode: "llm" | "user";
  musicPolicy: MusicPolicy;
  readableMode: boolean;
  config: GroupConfig | DebateConfig | WatchConfig | null;
  state: DebateState | WatchState | null;
  continuedFrom?: string;
  isSeed: boolean;
  costUsd: number; messageCount: number;
  createdAt: string; updatedAt: string; lastMessageAt?: string;
}

/** Mid-session settings change carried by `session.state` (D-57). */
export type SessionSettingsPatch = Partial<
  Pick<Session, "title" | "titleIsCustom" | "emotionMode" | "musicPolicy" | "readableMode" | "config">
>;

// ── Message & trace ─────────────────────────────────────────────────────────
export type MessageKind =
  | "chat" | "steer" | "interject" | "direction" | "narration" | "summary" | "verdict" | "system_note";
export interface MessageAuthor { type: "user" | "character" | "host" | "system"; characterId?: string }
export interface Reaction { characterId: string; emotion: Emotion; p?: number; at: string }
export interface MessageUsage {
  tokensIn: number; tokensCached?: number; tokensOut: number; costUsd: number;
  energySpent?: number; firstTokenMs: number; totalMs: number;
}
export interface Message {
  id: string; sessionId: string; seq: number;
  author: MessageAuthor;
  kind: MessageKind;
  targetCharacterId?: string;
  content: string;
  status: "streaming" | "complete" | "interrupted" | "error";
  interruptedBy?: "user" | "error";
  emotion?: Emotion; emotionSource?: EmotionSource;
  debate?: { phase: DebatePhase; round: number; iteration: number; side?: Side };
  forcedSpeaker?: boolean;
  reactions?: Reaction[];
  variants?: { id: string; content: string; emotion?: Emotion; createdAt: string }[];
  activeVariantId?: string;
  usage?: MessageUsage;
  trace?: TurnTrace;
  error?: { code: ErrorCode; message: string; retryable: boolean };
  createdAt: string;
}

export interface TurnTrace {
  messageId: string;
  model?: {
    id: string; provider: string; quantization?: string; pricePeriod?: "peak" | "off_peak";
    latencyMs: { firstToken: number; total: number };
    tokensIn: number; tokensCached?: number; tokensOut: number; costUsd: number;
  };
  energy?: { characterId: string; spent: number; remaining: number; max: number };
  emotion?: { chosen: Emotion; source: EmotionSource; candidates?: { label: Emotion; p: number }[] };
  routing?: {
    question?: string; selected: string;
    forcedBy?: "user_ask" | "mention" | "nudge" | "round_order";
    candidates?: { characterId: string; p: number }[];
    skipped?: { characterId: string; reason: "exhausted" | "muted" | "archived" }[];
    reason?: string;
  };
  memory?: { recalled: { memoryItemId: string; text: string; sourceSessionId?: string; score?: number }[] };
  contextInSession?: { text: string; messageId: string }[];
  context?: {
    budget: number; cacheHitPct?: number;
    used: { system: number; persona: number; memory: number; knowledge: number; history: number; user: number; mode: number };
  };
  guardrail?: { checks: { name: string; verdict: "pass" | "flag" | "block"; p?: number }[] };
  graph?: { path: string[] };
}

// ── Streaming events (doc 05 §6) ────────────────────────────────────────────
export type StreamEvent =
  | { type: "turn.next"; payload: { nextSpeakerId: string; forcedBy?: string; skipped?: { characterId: string; reason: "exhausted" | "muted" | "archived" }[] } }
  | { type: "turn.thinking"; payload: { characterId: string } }
  | { type: "turn.start"; payload: { messageId: string; author: MessageAuthor; emotion?: Emotion; variantId?: string; message?: Partial<Message> } }
  | { type: "token"; payload: { messageId: string; delta: string; variantId?: string } }
  // messageId absent + source "user" = MANUAL face change (D-51)
  | { type: "emotion"; payload: { messageId?: string; characterId: string; emotion: Emotion; source: EmotionSource } }
  | { type: "turn.end"; payload: { messageId: string; status: Message["status"]; interruptedBy?: "user" | "error"; usage?: MessageUsage; variantId?: string } }
  | { type: "energy"; payload: { characterId: string; current: number; max: number; state: EnergyState; fullAt?: string; spent?: number } }
  | { type: "reaction"; payload: { messageId: string; characterId: string; emotion: Emotion; p?: number; source: EmotionSource } }
  | { type: "insight"; payload: { messageId: string; trace: TurnTrace } }
  | { type: "phase"; payload: { phase: DebatePhase; round: number; iteration: number } }
  | { type: "watch.state"; payload: { status: WatchState["status"]; paceMs: number; turnsTaken: number; turnLimit: number } }
  | { type: "session.paused"; payload: { reason?: PausedReason } }
  | { type: "session.resumed"; payload: { reason?: string } }
  | { type: "budget.warning"; payload: { scope: "daily" | "creation"; spentUsd: number; capUsd: number } }
  | { type: "error"; payload: { code: ErrorCode; message: string; retryable: boolean; messageId?: string } }
  | { type: "message"; payload: { message: Message } } // D-51: whole non-streamed message (user, steer, direction, system_note, verdict)
  | { type: "session.state"; payload: { status?: SessionStatus; pausedReason?: PausedReason; state?: DebateState | WatchState; participants?: Participant[]; settings?: SessionSettingsPatch } }; // D-51, D-57

export type StreamEventType = StreamEvent["type"];

export interface SessionEvent {
  id: string; sessionId: string; seq: number;
  at: string; // ISO-8601; Replay derives pacing from the deltas
  type: StreamEventType;
  payload: StreamEvent["payload"];
}

// ── Generation jobs ─────────────────────────────────────────────────────────
export type GenerationJobKind =
  | "profile_draft" | "profile_regenerate" | "portrait_candidates" | "portrait_tweak"
  | "emotion_set" | "emotion_regenerate" | "song";
export interface GenerationTask {
  id: string;
  type: "profile" | "appearance_summary" | "palette_pick" | "portrait_candidate" | "emotion_image"
    | "expression_sheet" | "blink_frame" | "song_brief" | "theme_song";
  emotion?: Emotion;
  status: "queued" | "running" | "succeeded" | "failed" | "skipped";
  attempt: number; maxAttempts: number;
  resultRef?: string; previewUrl?: string;
  error?: { code: ErrorCode; message: string; retryable: boolean };
}
export interface GenerationJob {
  id: string; characterId: string;
  kind: GenerationJobKind;
  targetField?: string;
  status: "queued" | "running" | "succeeded" | "partial" | "failed" | "cancelled";
  progress: number;
  estimatedCostUsd: number; actualCostUsd: number;
  tasks: GenerationTask[];
  error?: { code: ErrorCode; message: string };
  createdAt: string; startedAt?: string; finishedAt?: string;
}

// ── Ledger, memory, knowledge ───────────────────────────────────────────────
export interface UsageRecord {
  id: string; at: string;
  category: "chat" | "decision" | "image" | "music" | "profile" | "summary" | "memory" | "energy_topup";
  model?: string; provider?: string; pricePeriod?: "peak" | "off_peak";
  sessionId?: string; characterId?: string; jobId?: string;
  tokensIn?: number; tokensCached?: number; tokensOut?: number;
  costUsd: number; estimatedCostUsd?: number; energyPoints?: number; latencyMs?: number;
}
export interface MemoryItem {
  id: string; characterId: string; worldId: string;
  kind: "fact" | "event" | "preference" | "about_user";
  text: string; importance: number; sourceSessionId?: string; sourceMessageId?: string; createdAt: string;
}
export interface KnowledgeSource {
  id: string; characterId: string; worldId: string; title: string;
  type: "text" | "file" | "url"; status: "indexing" | "indexed" | "failed"; bytes?: number;
}
