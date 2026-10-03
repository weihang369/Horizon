// HorizonClient: the one interface the UI talks to (doc 05 §6–7, EE paper §2.2). Owner: EE.
// Queries return Promises. Commands acknowledge with Promise<void>; their results arrive as SessionEvents
// (sessions.subscribe), JobEvents (jobs.subscribe) or GlobalEvents (onGlobal). Every rejection is a HorizonError.
// The MockClient implements it now; the FastAPI HttpClient implements the same interface later.
import type {
  AppSettings, Character, CharacterProfile, Appearance, DebateConfig, Emotion, EmotionAsset, Energy, GenerationJob,
  GenerationJobKind, GenerationTask, GroupConfig, KnowledgeChunk, KnowledgeSource, MemoryItem, Message, ModelSet, MusicPolicy,
  Participant, Session, SessionEvent, SessionMode, Side, SongBrief, ThemeSong, TurnTrace, UsageRecord, WatchConfig,
  World, YouCard,
} from "../contract/types";
import type { HorizonErrorShape } from "../contract/errors";

export type Unsubscribe = () => void;
export type DeepPartial<T> = { [K in keyof T]?: T[K] extends object ? (T[K] extends unknown[] ? T[K] : DeepPartial<T[K]>) : T[K] };

// ── Settings ─────────────────────────────────────────────────────────────────
export interface ConnectionResult { ok: true; latencyMs: number; creditsUsd?: number }
export interface ModelTestResult { ok: true; latencyMs: number; model: string }

export interface SettingsApi {
  get(): Promise<AppSettings>;
  update(patch: DeepPartial<AppSettings>): Promise<AppSettings>;
  /** Stores the key (never echoed back). `null` clears it (demo mode). Mock: `sk-or-*` valid, `sk-or-bad*` invalid. */
  setKey(key: string | null): Promise<AppSettings>;
  testConnection(): Promise<ConnectionResult>;
  testModel(role: keyof ModelSet): Promise<ModelTestResult>;
}

// ── Worlds ───────────────────────────────────────────────────────────────────
export interface WorldInput { name: string; cover: World["cover"]; you?: YouCard }
export interface WorldsApi {
  list(): Promise<World[]>;
  get(id: string): Promise<World>;
  create(input: WorldInput): Promise<World>;
  update(id: string, patch: Partial<WorldInput>): Promise<World>;
  delete(id: string): Promise<void>;
}

// ── Characters ───────────────────────────────────────────────────────────────
export interface DraftInput { seedPrompt: string; intent: Character["intent"] }
export type CharacterPatch = Partial<Pick<Character, "seedPrompt" | "intent" | "advisory" | "paletteId" | "creationStep" | "status" | "profileMeta" | "emotionSet">> & {
  profile?: Partial<CharacterProfile>;
  appearance?: Partial<Omit<Appearance, "attributes">> & { attributes?: DeepPartial<Appearance["attributes"]> };
};
export interface CharactersApi {
  list(worldId: string, opts?: { includeArchived?: boolean }): Promise<Character[]>;
  get(id: string): Promise<Character>;
  /** Creates a draft and starts its `profile_draft` job (an AI action: needs a key). */
  createDraft(worldId: string, input: DraftInput): Promise<{ character: Character; job: GenerationJob }>;
  update(id: string, patch: CharacterPatch): Promise<Character>;
  /** "Lock as base" (CHR-07 AC3): the candidate becomes the neutral emotion and EMOTIONS unlocks. */
  lockPortrait(id: string, candidateId: string): Promise<Character>;
  /** review → approved (approval gate: valid profile + locked base portrait). */
  approve(id: string): Promise<Character>;
  archive(id: string): Promise<Character>;
  restore(id: string): Promise<Character>;
  delete(id: string): Promise<void>;
  /** Asset history for O25 Old/New and the gallery. */
  assets(id: string): Promise<EmotionAsset[]>;
  acceptAssetVersion(assetId: string): Promise<Character>;
  song(id: string): Promise<ThemeSong | null>;
  topUpEnergy(id: string, points: number): Promise<Energy>;
  setEnergyMax(id: string, points: number): Promise<Energy>;
  memory(id: string): Promise<MemoryItem[]>;
  forgetMemory(memoryItemId: string): Promise<void>;
  knowledge(id: string): Promise<KnowledgeSource[]>;
  /** D-59: one source with its indexed passages (O28 source viewer). */
  knowledgeSource(sourceId: string): Promise<{ source: KnowledgeSource; chunks: KnowledgeChunk[] }>;
}

// ── Jobs ─────────────────────────────────────────────────────────────────────
export interface StartJobInput {
  characterId: string;
  kind: GenerationJobKind;
  /** profile_regenerate: the field to redo. */
  targetField?: string;
  /** emotion_set (defaults from generationMode) / emotion_regenerate (one). */
  emotions?: Emotion[];
  /** emotion_set reveal: per-emotion edits (Variant B) or one expression sheet (Variant C). */
  technique?: "per_emotion" | "expression_sheet";
  /** portrait_tweak text, or the "Doesn't look like them" consistency hint. */
  prompt?: string;
  /** song: the edited brief. */
  brief?: SongBrief;
}
export type JobEvent =
  | { type: "job.progress"; job: GenerationJob }
  | { type: "task.update"; jobId: string; task: GenerationTask }
  | { type: "job.done"; job: GenerationJob };
export interface JobsApi {
  /** Estimate before confirming (CHR-13). */
  estimate(input: StartJobInput): Promise<{ estimatedCostUsd: number }>;
  start(input: StartJobInput): Promise<GenerationJob>;
  get(jobId: string): Promise<GenerationJob>;
  cancel(jobId: string): Promise<void>;
  retryTask(jobId: string, taskId: string): Promise<void>;
  listActive(): Promise<GenerationJob[]>;
  /** Snapshot first, then live updates until job.done. */
  subscribe(jobId: string, cb: (e: JobEvent) => void): Unsubscribe;
}

// ── Sessions ─────────────────────────────────────────────────────────────────
export interface SessionSnapshot { session: Session; messages: Message[]; lastSeq: number }
export interface CreateSessionInput {
  worldId: string;
  mode: SessionMode;
  characterIds: string[];
  title?: string;
  emotionMode?: Session["emotionMode"];
  musicPolicy?: MusicPolicy;
  config?: Partial<GroupConfig> | DebateConfig | WatchConfig | null;
  /** Debate two-sided: sides by characterId. */
  sides?: Record<string, Side>;
  continuedFrom?: string;
  /** Seed text for "Continue as group chat" (the debate summary). */
  seedSummary?: string;
}
export interface SessionsApi {
  list(worldId: string): Promise<Session[]>;
  get(id: string): Promise<SessionSnapshot>;
  /** Starts a live session (needs a key). 1:1 greets; debate/watch start their run. */
  create(input: CreateSessionInput): Promise<SessionSnapshot>;
  rename(id: string, title: string): Promise<Session>;
  delete(id: string): Promise<void>;
  /** "Continue live" (D-51, R16): a new live session from a seed recording, cut at `atSeq` when given. */
  forkSeedSession(id: string, atSeq?: number): Promise<SessionSnapshot>;
  messages(id: string): Promise<Message[]>;
  trace(messageId: string): Promise<TurnTrace | null>;
  /** The recorded event log (Replay). */
  events(id: string): Promise<SessionEvent[]>;
  /** Markdown transcript (CHAT-11, MULTI-14). */
  export(id: string): Promise<string>;
  /** Like Last-Event-ID: events with seq > sinceSeq, then live ones. */
  subscribe(id: string, opts: { sinceSeq: number }, cb: (e: SessionEvent) => void): Unsubscribe;
  /** Leaving a live session pauses it (MULTI-13). */
  leave(id: string): Promise<void>;
  end(id: string): Promise<void>;
}

// ── Commands (doc 05 §6) ─────────────────────────────────────────────────────
export interface SendOptions { mentions?: string[] }
export interface ChatApi {
  send(sessionId: string, text: string, opts?: SendOptions): Promise<void>;
  stop(sessionId: string): Promise<void>;
  regenerate(sessionId: string, messageId: string): Promise<void>;
  /** MANUAL face change (D-51: `emotion` event without messageId, source "user"). */
  setEmotion(sessionId: string, characterId: string, emotion: Emotion): Promise<void>;
  setEmotionMode(sessionId: string, mode: Session["emotionMode"]): Promise<void>;
  setResponderPolicy(sessionId: string, policy: GroupConfig["responderPolicy"]): Promise<void>;
  setMusicPolicy(sessionId: string, policy: MusicPolicy): Promise<void>;
  setReadableMode(sessionId: string, on: boolean): Promise<void>;
  everyoneAnswer(sessionId: string): Promise<void>;
  /** One more character speaks without a user message (`characterId` = Speak next). */
  nextSpeaker(sessionId: string, characterId?: string): Promise<void>;
  muteParticipant(sessionId: string, characterId: string, muted: boolean): Promise<void>;
}
export interface DebateApi {
  pause(sessionId: string): Promise<void>;
  resume(sessionId: string): Promise<void>;
  /** Next turn (auto-advance off). */
  next(sessionId: string): Promise<void>;
  setAutoAdvance(sessionId: string, on: boolean): Promise<void>;
  askCharacter(sessionId: string, characterId: string, text: string): Promise<void>;
  interject(sessionId: string, text: string): Promise<void>;
  extendRound(sessionId: string): Promise<void>;
  skipToClosing(sessionId: string): Promise<void>;
  endDebate(sessionId: string, withVerdict: boolean): Promise<void>;
  pickStrongerCase(sessionId: string, side: Side): Promise<void>;
}
export interface WatchApi {
  play(sessionId: string): Promise<void>;
  pause(sessionId: string): Promise<void>;
  step(sessionId: string): Promise<void>;
  setPace(sessionId: string, paceMs: WatchConfig["paceMs"]): Promise<void>;
  direct(sessionId: string, text: string): Promise<void>;
  /** Step in: pause, speak as yourself, up to 2 reply, then wait for play(). */
  stepIn(sessionId: string, text: string): Promise<void>;
  extendWatch(sessionId: string, turns?: number): Promise<void>;
  summarise(sessionId: string): Promise<void>;
}

// ── Usage ────────────────────────────────────────────────────────────────────
export interface UsageSummary {
  todayUsd: number; totalUsd: number; capUsd: number;
  byCategory: Record<UsageRecord["category"], number>;
  byCharacter: Record<string, number>;
  bySession: Record<string, number>;
  estimatedUsd: number; actualUsd: number;
}
export interface UsageApi {
  list(opts?: { sinceDays?: number }): Promise<UsageRecord[]>;
  summary(): Promise<UsageSummary>;
}

// ── Global events ────────────────────────────────────────────────────────────
export type EntityKind = "settings" | "world" | "character" | "session" | "usage" | "memory" | "knowledge" | "job";
export type GlobalEvent =
  | { type: "entity.changed"; kind: EntityKind; id?: string; worldId?: string }
  | { type: "budget.warning"; scope: "daily" | "creation"; spentUsd: number; capUsd: number }
  | { type: "budget.reached"; scope: "daily" | "creation"; spentUsd: number; capUsd: number; sessionId?: string; jobId?: string }
  | { type: "job.progress"; job: GenerationJob }
  | { type: "job.done"; job: GenerationJob; characterName?: string }
  | { type: "error"; error: HorizonErrorShape; context?: string }
  /** The mock DB was re-seeded (scenario or "Reset demo data"): screens re-query in place. */
  | { type: "mock.reset" };

export interface HorizonClient {
  readonly kind: "mock" | "http";
  settings: SettingsApi;
  worlds: WorldsApi;
  characters: CharactersApi;
  jobs: JobsApi;
  sessions: SessionsApi;
  chat: ChatApi;
  debate: DebateApi;
  watch: WatchApi;
  usage: UsageApi;
  onGlobal(cb: (e: GlobalEvent) => void): Unsubscribe;
}

export type { Participant };
