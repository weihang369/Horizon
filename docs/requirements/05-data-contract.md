# 05: Data Contract (contract rev. 1.3)

> **Contract rev. 1.3 (2026-10-03, backend design, D-75):** additive only, `schemaVersion` stays `1`. Adds:
> - error codes `not_found`, `validation` and `conflict`, plus `HorizonErrorShape.details`;
> - the ID prefixes `kno_`, `kch_`, `ksec_` and `cmd_`;
> - knowledge add, delete and reindex, the `keyword_only` status, and `"url"` as a legacy read-only type;
> - world cover upload;
> - `models.embedding` and the `embedding` ledger category;
> - `AppSettings.energy.estReplyPoints` (D-78);
> - `TurnTrace.calls`;
> - `entity.changed.progress` and `task.update` on the global stream.
>
> **Rev 1.3 addendum (M1b `backend-foundation`):** `HorizonClient.admin.resetDemo()` (both clients; the app's "Reset demo data" buttons call it); world names unique case-insensitively, with the shipped seed world names reserved (`conflict`, `details.field: "name"`); `SessionSnapshot` and `UsageSummary` exported to `schema.json` so the backend validates those bodies too.
>
> §6 is reconciled with the code. The machine-readable form is `backend/horizon/contract/schema.json` (`npm run export-schema` in `frontend/`). Full list: [docs/backend/03 §7](../backend/03-api.md#7-contract-rev-13-additive).
>
> **Contract rev. 1.2 (D-59):** citations, `KnowledgeChunk` and knowledge traces.
>
> **Contract rev. 1.1 (2026-10-02, UI/UX stage):** additive only, `schemaVersion` stays `1`. Adds the `message` and `session.state` events, a face-change form of `emotion`, `AppSettings.pricing` and `forkSeedSession(…, atSeq?)` (D-51), plus `session.state.settings` for mid-session settings changes (D-57).
>
> **This is the single source of truth for data shapes.** The UI/UX mock fixtures, the FastAPI backend and the AI layer all use these shapes.
> Types are framework-agnostic, written in TypeScript style. `?` = optional or nullable. SWE may refine the storage, but **must not change the wire shapes** without updating this doc (and bumping `schemaVersion`).

## 1. Conventions

- **IDs:** `^[a-z]+_[0-9A-Za-z]{1,40}$`.
  - Prefixes: `wld_`, `chr_`, `ses_`, `msg_`, `emo_`, `song_`, `job_`, `task_`, `mem_`, `trk_`, `evt_`; rev 1.3 adds `kno_` (knowledge source), `kch_` (child chunk), `ksec_` (knowledge section) and `cmd_` (command receipt).
  - Generated IDs use a **ULID** after the prefix.
  - Seed IDs are **readable** and are *not* ULIDs, e.g. `chr_seedAmara`, `wld_seedMeridian`, `ses_seedDebate4Day`. Validators must accept both forms.
- **Timestamps:** ISO-8601 UTC strings.
- **Asset URLs:** **relative** (`/assets/...`), so mock and backend serve identical paths.
- **Fixtures and exports:** carry `schemaVersion: 1` at the root.
- **World isolation:** every Character, Session, MemoryItem and KnowledgeSource resolves to exactly one `worldId`. No API, memory or retrieval call may cross worlds (NFR-23).
- **Money:** USD numbers. **Energy:** ⚡ points, where **1 ⚡ = US$0.0001** (config `energy.usdPerPoint`). Stored as a real number; the wire floors `current` and `spentToday` to integers (D-78).

## 2. Entity map

```
AppSettings (singleton)
StylePreset (global, versioned) ──< referenced by Appearance / EmotionAsset
Palette (fixed catalogue, doc 04 §3)
SystemTrack (shipped free-library tracks: main theme, arena, ambient bed)
World 1──1 YouCard (embedded, optional)
World 1──< Character 1──1 CharacterProfile (embedded)
                    1──1 Appearance       (embedded)
                    1──1 Energy           (embedded)
                    1──< EmotionAsset      (≤1 active per emotion+variant; history kept)
                    1──? ThemeSong         (exactly ONE theme per character; regenerating replaces it)
                    *──1 Palette
World 1──< Session 1──< Participant >──1 Character
                   1──< Message 1──? TurnTrace
                   1──< SessionEvent   (append-only; powers Replay + demo mode + the MockClient)
Character 1──< GenerationJob 1──< GenerationTask
UsageRecord (cost ledger) ──? Session | Character | GenerationJob
MemoryItem      (AI-owned)               >──1 Character (scoped to its World)
KnowledgeSource (RAG in v1, docs/ai/10)  >──1 Character
```

## 3. Enums

```ts
type Emotion = "neutral" | "happy" | "sad" | "angry" | "surprised" | "thinking" | "embarrassed";
type EmotionSource = "user" | "llm" | "classifier" | "default";
type CharacterStatus = "draft" | "review" | "approved" | "archived";
//   draft    = anywhere in the wizard before APPROVE (progress lives on GenerationJob / activeJobId)
//   review   = on the APPROVE step
//   failures live on GenerationJob / GenerationTask, never on the character
type CreationStep = "seed" | "profile" | "look" | "portrait" | "emotions" | "palette" | "theme" | "approve";
type SessionMode = "one_on_one" | "group" | "debate" | "watch";
type SessionStatus = "active" | "paused" | "ended";
type PausedReason = "user" | "turn_cap" | "daily_budget" | "error" | "navigated_away";
type AssetStatus = "pending" | "generating" | "ready" | "failed" | "rejected";
type VfxPreset = "none" | "sparkle" | "rain" | "anger" | "shock" | "ponder" | "blush" | "sleep";
type EnergyState = "active" | "tired" | "exhausted";      // tired < 20 %, exhausted = cannot afford a reply
type ErrorCode = "missing_key" | "invalid_key" | "insufficient_credits" | "rate_limited" | "content_refused"
               | "provider_error" | "daily_budget_exceeded" | "creation_budget_exceeded" | "energy_exhausted"
               | "timeout" | "network"
               | "not_found" | "validation" | "conflict";   // rev 1.3: missing/other-world record · bad input or limit · forbidden state transition
// Every rejection carries { code, message, retryable, retryAfterSec?, details? }; `details` is machine-readable
// (e.g. { activeSessionId } on a live-session conflict, { limit } on a limit violation).
type DebatePhase = "setup" | "opening" | "rebuttal" | "closing" | "verdict" | "ended";
```

## 4. Entities

### AppSettings (singleton)
```ts
AppSettings {
  openRouterKeyStatus: "missing" | "set" | "invalid";   // the key itself is NEVER sent to the frontend
  demoMode: boolean;                                     // true when no key is set
  models: { chat: string; decision: string; image: string; music: string; embedding: string };  // config defaults (embedding: rev 1.3)
  modelOverrides?: Partial<AppSettings["models"]>;      // local, git-ignored
  generationMode: "lean" | "standard";                   // DEFAULT "lean" (D-40)
  autoGenerateMissingEmotions: boolean;                  // default false
  budget: { dailyCapUsd: number;                         // default 1.00 (master safety net, all spend)
            perCharacterCreationCapUsd: number;          // default 0.60 (applies until approvedAt)
            warnAtPct: number };                         // default 80
  energy: { defaultMaxPoints: number;                    // default 1000 ⚡ (= US$0.10) per character per day
            usdPerPoint: number;                         // 0.0001
            topUpStepPoints: number;                     // default 500
            estReplyPoints: { off_peak: number; peak: number } };  // rev 1.3, read-only (4 / 8): the ONE Exhausted threshold (D-78)
  spentTodayUsd: number;                                 // derived from the ledger
  pricing: { period: "peak" | "off_peak"; nextChangeAt: string };   // D-51: drives the RUSH HOUR chip (ENG-06); derived from the MYT clock
  audio: { masterMuted: boolean; musicMuted: boolean; sfxMuted: boolean;
           master: number; music: number; sfx: number; duckMusic: boolean };   // volumes 0..1
  display: { reducedMotion: "system" | "on" | "off"; vfxIntensity: "off" | "subtle" | "full";
             flashIntensity: "off" | "low" | "full"; parallax: boolean; textSize: "s" | "m" | "l"; speakerCutIns: boolean };
  chat: { defaultEmotionMode: "llm" | "user"; responderDefault: "auto" | "everyone" | "mentioned";
          debateAutoAdvance: boolean; readableDefault: boolean };
  cost: { showEstimates: boolean; confirmBeforeGenerate: boolean; showHud: boolean };
  presenterMode: boolean;
  contentRating: "sfw";                                  // MVP value; extended by OQ-AI-08
}
```

### StylePreset
`{ id: "style_horizon_anime", version: number, promptFragment: string, referenceImageUrls: string[] }`. Every generated image records the preset ID and version it used. *Qwen Image 3 accepts at most 4 reference images, so a call carries the base portrait plus ≤ 3 style references.*

### Palette
`{ id, name, primary, secondary, accent, stage, surface, onPrimary, glow, text }`. The fixed catalogue is in doc 04 §3.

### SystemTrack
`{ id, kind: "main_theme" | "arena" | "ambient_bed", url, durationSec, loop?: { startSec, endSec }, gainDb?: number, source: "free_library", credit: string, licence: string }`

### World
```ts
World {
  id: string; name: string;                       // 1–40 chars (trimmed; empty → "New World"), unique case-insensitively;
                                                  // a shipped seed world's name is reserved for that world (rev 1.3 addendum)
  cover: { kind: "preset" | "upload" | "generated"; presetId?: string; url?: string };
  you?: YouCard;                                  // how characters in THIS world know the user (D-43)
  characterCount: number;                         // derived
  isSeed: boolean;
  createdAt: string; updatedAt: string; lastActiveAt: string;
}
YouCard { displayName: string /* ≤ 30 */; about?: string /* ≤ 160, e.g. "Hana's boyfriend, works in IT" */ }
```
*The UI log label for the user is `you.displayName` when set, otherwise "You". The AI layer includes the YouCard in prompts for that world only.*

### Character
```ts
Character {
  id: string; worldId: string;                    // worldId is immutable
  status: CharacterStatus;
  creationStep?: CreationStep;                    // wizard resume point
  seedPrompt: string;
  intent: "expert" | "companion" | "other";
  advisory: boolean;                              // drives the SME disclaimer (auto from role, editable)
  profile: CharacterProfile;
  profileMeta?: { editedFields: string[] };       // the "edited" dot
  appearance: Appearance;
  paletteId: string;                              // provisional "AI pick" from the draft, confirmed at PALETTE
  emotionSet: Emotion[];                          // all 7
  emotions: Record<Emotion, EmotionAssetRef | null>;   // null = not generated → UI shows neutral + VFX
  blink?: EmotionAssetRef | null;                 // neutral blink frame (optional)
  themeSongId?: string;                           // exactly one theme; optional (valid without one)
  energy: Energy;
  activeJobId?: string;
  version: number;                                // increments on saved edits
  isSeed: boolean;
  createdAt: string; updatedAt: string; approvedAt?: string; archivedAt?: string; deletedAt?: string;
}
EmotionAssetRef { assetId: string; url: string; vfxPreset: VfxPreset }
```

### Energy (embedded in Character; see ENG stories in doc 02)
```ts
Energy {
  max: number;                 // ⚡ per day; default AppSettings.energy.defaultMaxPoints (1000); per-character override
  current: number;             // ⚡ at `asOf`
  asOf: string;                // timestamp the value was computed
  regenPerHour: number;        // = max / 24 → refills from empty to full in ~24 h
  state: EnergyState;          // derived: exhausted if current < AppSettings.energy.estReplyPoints[period]; tired if < 20 % of max
  fullAt?: string;             // when it will be full again (UI countdown)
  spentToday: number;          // ⚡ spent since local midnight (MYT by default), for the profile stat
}
```
- **Regeneration is computed lazily:** `current = min(max, current + regenPerHour × hoursSince(asOf))`. There are no timers.
- **Drain (D-42):** only the **character's own talking** drains its energy: the LLM call that generates that character's reply (1:1, group, debate, watch). The drain equals that call's actual cost in ⚡, rounded up.
- **Does not drain:** routing, listener reactions, host lines, verdicts, memory writes, profile drafting, images, the theme song. These count only against the **daily cap**.
- **Top-up (D-76):** `topUpEnergy(characterId, points)` adds ⚡ (it may exceed `max` for today). It is allowed while `spentTodayUsd + (todayTopUpPoints + points) × usdPerPoint ≤ dailyCapUsd`, else `daily_budget_exceeded`. The ledger row costs $0.
- **One threshold (D-78):** `exhausted` ⇔ `current < estReplyPoints[period]` (4 ⚡ off-peak, 8 ⚡ at peak). The same value decides the displayed state and whether the character may speak.

### CharacterProfile (the source of the system prompt)
```ts
CharacterProfile {
  name: string; title?: string;                   // "Dr.", "Prof."
  role: string;                                   // "Emergency physician"
  age: number;                                    // INTEGER ≥ 18 (content floor, validated by UI + backend)
  pronouns?: string;
  tagline: string;                                // ≤ 80
  personality: { summary: string; traits: string[] };          // traits 3–8
  backstory: string;
  speakingStyle: { summary: string; tone: string; formality: "casual" | "neutral" | "formal";
                   quirks: string[]; catchphrases: string[] };
  expertise: string[];
  goals?: string;
  boundaries: string[];
  greeting: string;
  exampleLines?: string[];                        // 0–3
  relationshipToUser?: string;                    // FREE TEXT ONLY ("your girlfriend"). No links between characters.
  systemPromptPreview?: string;                   // read-only; compiled by the AI layer
}
```

### Appearance
```ts
Appearance {
  attributes: {
    body: { ageBand: "young_adult" | "adult" | "middle_aged" | "senior"; build: string; height: string; skinTone: string };
    face: { shape: string; baseline: "soft" | "neutral" | "sharp"; marks: string[] };
    eyes: { shape: string; color: string; glasses: "none" | "round" | "square" | "half_rim" };
    hair: { length: string; style: string; color: string; streakColor?: string; fringe: string };
    outfit: { archetype: string; primaryColor: string; secondaryColor: string };
    accessories: string[];                        // ≤ 3
    vibe: string[];                               // ≤ 2
    extraDetails?: string;
  };
  appearanceSummary: string;                      // editable sentence compiled from the attributes
  basePortraitUrl?: string;                       // identity anchor for emotions
  candidates: { id: string; url: string; selected: boolean; status: AssetStatus }[];
  stylePresetId: string; stylePresetVersion: number;
}
```
*There is no minor `ageBand` value. Image prompts always include the adult-appearance clause. Vocabulary for every attribute is in doc 06 §8.*

### EmotionAsset
```ts
EmotionAsset {
  id: string; characterId: string; emotion: Emotion;
  variant: "default" | "blink";                   // blink only for neutral
  status: AssetStatus;
  url?: string; width?: number; height?: number; format?: "webp" | "avif"; bytes?: number;
  vfxPreset: VfxPreset;
  generation?: { model: string; technique: "reference_edit" | "expression_sheet" | "prompt_only" | "manual";
                 prompt: string; referenceUrls: string[]; seed?: number; costUsd: number; jobId?: string };
  version: number; isActive: boolean;
}
```
*Portraits are **opaque**: the default image models cannot output transparency (D-45). They are rendered as framed cards or with a soft radial mask (doc 04 §4).*

### ThemeSong (exactly one per character)
```ts
ThemeSong {
  id: string; characterId: string; status: AssetStatus;
  url?: string; durationSec?: number; format?: "opus" | "aac" | "mp3"; bytes?: number;
  loop?: { startSec: number; endSec: number };    // optional; default = whole track, 1 s crossfade loop in WebAudio
  gainDb?: number;                                // measured once for loudness matching; applied client-side
  brief: { genres: string[]; moods: string[]; bpm: number; instruments: string[]; vibe: string };
  instrumental: boolean;                          // default true
  generation?: { model: string; prompt: string; costUsd: number; jobId?: string };
  licenseNote: string;                            // provider + terms reference
}
```
*Regenerating (in the wizard or via Edit) **replaces** the song. There is no song history in the UI.*

### Session
```ts
Session {
  id: string; worldId: string;
  title: string; titleIsCustom: boolean;
  mode: SessionMode; status: SessionStatus; pausedReason?: PausedReason;
  participants: Participant[];                    // 1 for one_on_one; 2–5 otherwise
  emotionMode: "llm" | "user";                    // UI labels AUTO / MANUAL; MANUAL = face only
  musicPolicy: "character_theme" | "follow_speaker" | "arena" | "scene_bed";   // the ONLY music setting
  readableMode: boolean;
  config: GroupConfig | DebateConfig | WatchConfig | null;
  state: DebateState | WatchState | null;
  continuedFrom?: string;                         // e.g. a group session from a verdict, or a live fork of a seed session
  isSeed: boolean;                                // seed sessions are replay-only; "Continue live" forks a new session
  costUsd: number; messageCount: number;
  createdAt: string; updatedAt: string; lastMessageAt?: string;
}
Participant { characterId: string; role: "speaker" | "debater"; side?: "prop" | "opp" | null;
              currentEmotion: Emotion; mutedByUser: boolean }
```
*The user is **not** a Participant. The user is `author.type = "user"`.*

```ts
GroupConfig { responderPolicy: "auto" | "everyone" | "mentioned"; maxAutoResponders: 2 }

DebateConfig {
  motion: string;                                 // ≤ 200
  format: "two_sided" | "panel";
  sides?: { prop: string[]; opp: string[] };      // characterIds (two_sided)
  roundsPreset: "quick" | "standard";             // "extended" (cross-exam) = v1.1
  phases: ("opening" | "rebuttal" | "closing")[]; // derived from the preset
  turnLength: "short" | "medium" | "long";        // ≈ 80 / 150 / 250 words
  moderator: "user" | "auto_host";                // "character" chair = v1.1
  verdictBy: "arbiter" | "user" | "none";         // panel format → "arbiter" (summary) or "none" only
  rubric: { id: string; label: string }[];        // DATA-DRIVEN (2–6 criteria; final rubric = AI team)
  autoAdvance: boolean; pauseMs: number;          // default true, 1500
}
DebateState {
  phase: DebatePhase;
  round: number;                                  // 1-based PHASE INDEX shown in banners ("ROUND 2: REBUTTAL")
  iteration: number;                              // 1-based repeat within the phase ("Extend round" → 2)
  nextSpeakerId?: string;
  verdict?: Verdict;
}
Verdict {
  decidedBy: "arbiter" | "user" | "none";
  strongerCase?: "prop" | "opp" | null;           // null = too close to call / panel / none
  scoresBy?: "side" | "debater";
  scores?: { subjectId: string; criterionId: string; value: number }[];   // long format, 0–10; optional
  summary: { subjectId: string; points: string[] }[];
  keyDisagreement?: string;
  rationale?: string;
}

WatchConfig { premise: string; maxTurns: 10 | 20 | 40;   // initial episode length
              paceMs: 3000 | 1500 | 500;                 // Slow / Normal / Fast gap between live turns
              openingSpeaker: "auto" | string }
WatchState  { status: "playing" | "paused" | "ended"; turnsTaken: number;
              turnLimit: number;                          // starts at maxTurns; "Continue +10" adds 10
              nextSpeakerId?: string }
```
*`playbackRate: 1 | 2 | 4` exists **only** in the Replay player and the MockClient demo speed. It is never part of a live session.*

### Message
```ts
Message {
  id: string; sessionId: string; seq: number;     // seq is monotonic within the session
  author: { type: "user" | "character" | "host" | "system"; characterId?: string };
  kind: "chat" | "steer" | "interject" | "direction" | "narration" | "summary" | "verdict" | "system_note";
  targetCharacterId?: string;                     // "Ask… Mei" / nudges
  content: string;                                // Markdown
  status: "streaming" | "complete" | "interrupted" | "error";
  interruptedBy?: "user" | "error";               // "(stopped)" vs "(interrupted)"
  emotion?: Emotion; emotionSource?: EmotionSource;
  debate?: { phase: DebatePhase; round: number; iteration: number; side?: "prop" | "opp" };
  forcedSpeaker?: boolean;
  reactions?: { characterId: string; emotion: Emotion; p?: number; at: string }[];   // listener reactions
  variants?: { id: string; content: string; emotion?: Emotion; createdAt: string }[];
  activeVariantId?: string;                       // ONLY the active variant feeds context & memory
  usage?: { tokensIn: number; tokensCached?: number; tokensOut: number; costUsd: number;
            energySpent?: number;                 // ⚡ drained from the speaking character
            firstTokenMs: number; totalMs: number };
  trace?: TurnTrace;                              // may be loaded separately
  citations?: Citation[];                         // D-59 (rev 1.2): knowledge quoted by this reply; content carries [n]
  error?: { code: ErrorCode; message: string; retryable: boolean };
  createdAt: string;
}
```
- **One message per character turn, with one emotion** (D-46). There are no multi-bubble replies.
- A director's note is `author.type: "user"`, `kind: "direction"`.
- Moderator steering by the user is `author.type: "user"`, `kind: "steer" | "interject"`.
- An AI host is `author.type: "host"`, `kind: "narration"`.
- "Hana is asleep (⚡ 0)" notices are `author.type: "system"`, `kind: "system_note"`.
- **Citations (D-59, rev. 1.2):** `Citation { n, sourceId, title, type, chunkId, locator?, quote /*≤400*/, score? }`. The reply text carries `[n]` markers (1-based, unique per message); a marker with no matching entry renders as plain text. `title` is a snapshot, so a renamed or deleted source still reads correctly. Markers inside code blocks are ignored.

### TurnTrace (Insight drawer data; AI-owned; **every section optional**)
```ts
TurnTrace {
  messageId: string;
  model?:    { id: string; provider: string; quantization?: string; pricePeriod?: "peak" | "off_peak";
               latencyMs: { firstToken: number; total: number };
               tokensIn: number; tokensCached?: number; tokensOut: number; costUsd: number };
  energy?:   { characterId: string; spent: number; remaining: number; max: number };
  emotion?:  { chosen: Emotion; source: EmotionSource; candidates?: { label: Emotion; p: number }[] };
  routing?:  { question?: string; selected: string;
               forcedBy?: "user_ask" | "mention" | "nudge" | "round_order";
               candidates?: { characterId: string; p: number }[];
               skipped?: { characterId: string; reason: "exhausted" | "muted" | "archived" }[];
               reason?: string };                 // only if an LLM produces one; Jev never does
  memory?:   { recalled: { memoryItemId: string; text: string; sourceSessionId?: string; score?: number }[] };
  knowledge?: { query?: string; trigger?: "always" | "tool_call" | "gated";            // D-59 (rev 1.2)
                retrieved: { chunkId: string; sourceId: string; title: string; locator?: string;
                             text: string; score: number; cited: boolean; n?: number }[] };
  contextInSession?: { text: string; messageId: string }[];   // in-session recall ≠ long-term memory
  context?:  { budget: number; cacheHitPct?: number;
               used: { system: number; persona: number; memory: number; knowledge: number;
                       history: number; user: number; mode: number } };
  guardrail?: { checks: { name: string; verdict: "pass" | "flag" | "block"; p?: number }[] };
  graph?:    { path: string[] };                  // LangGraph node path (INS-03, Could)
  calls?:    { purpose: string; model: string; costUsd: number; latencyMs: number; fallback?: boolean }[];
             // rev 1.3: every paid call behind this turn (Jev route/gate/rerank, embeddings, the reply itself)
}
```

### SessionEvent (append-only; SWE-owned)
`{ id, sessionId, seq, at, type, payload }`. It stores **exactly** the stream events of §6, so **Replay, demo mode and the UI MockClient are the same engine**.

### GenerationJob / GenerationTask
```ts
GenerationJob {
  id: string; characterId: string;
  kind: "profile_draft" | "profile_regenerate" | "portrait_candidates" | "portrait_tweak"
      | "emotion_set" | "emotion_regenerate" | "song";
  targetField?: string;                           // per-field profile regenerate
  status: "queued" | "running" | "succeeded" | "partial" | "failed" | "cancelled";
  progress: number;                               // 0..1
  estimatedCostUsd: number; actualCostUsd: number;
  tasks: GenerationTask[]; error?: { code: ErrorCode; message: string };
  createdAt: string; startedAt?: string; finishedAt?: string;
}
GenerationTask {
  id: string; type: "profile" | "appearance_summary" | "palette_pick" | "portrait_candidate" | "emotion_image"
                  | "expression_sheet" | "blink_frame" | "song_brief" | "theme_song";
  emotion?: Emotion;
  status: "queued" | "running" | "succeeded" | "failed" | "skipped";
  attempt: number; maxAttempts: number;          // max 3
  resultRef?: string; previewUrl?: string;        // optional low-res progressive preview
  error?: { code: ErrorCode; message: string; retryable: boolean };
}
```

### UsageRecord (cost ledger)
`{ id, at, category: "chat" | "decision" | "image" | "music" | "profile" | "summary" | "memory" | "embedding" /*rev 1.3*/ | "energy_topup", model?, provider?, pricePeriod?, sessionId?, characterId?, jobId?, tokensIn?, tokensCached?, tokensOut?, costUsd, estimatedCostUsd?, energyPoints?, latencyMs? }`. `costUsd` comes from the provider-reported cost (`usage.cost`) when available. An `energy_topup` row has `costUsd: 0` and `energyPoints` set: a top-up authorises spend, and the replies it funds are recorded as `chat` (D-76).

### MemoryItem (final: the AI stage kept this shape, [docs/ai/09](../ai/09-memory.md); OQ-AI-01 resolved)
`{ id, characterId, worldId, kind: "fact" | "event" | "preference" | "about_user", text, importance: number /*0..1*/, sourceSessionId?, sourceMessageId?, createdAt }`

### KnowledgeSource (D-59; rev 1.3 per D-65)
`{ id /*kno_…*/, characterId, worldId, title, type: "text" | "file" | "url", status: "indexing" | "indexed" | "keyword_only" | "failed", bytes?, pages?, chunks?, url?, citedCount?, addedAt?, error? }`
- **New sources** are `"file"` (PDF, DOCX, MD, TXT; ≤ 10 MB, ≤ 300 pages) or `"text"` (pasted), with at most 20 per character. `"url"` is **legacy and read-only**: no command creates it.
- **Status:** `indexing` → `indexed` (keyword and vector search) | `keyword_only` (keyword search only, because embedding was unavailable; `reindexKnowledge` upgrades it) | `failed` (`error` says why).
- **Commands (rev 1.3):** `characters.addKnowledge(id, { file } | { type: "text", title, text })`, `deleteKnowledge(sourceId)` and `reindexKnowledge(sourceId)`. Progress arrives as `entity.changed { kind: "knowledge", id, progress: { stage: "extracting" | "chunking" | "embedding", pct } }`.
- **Seed status:** the backend imports seed sources as `keyword_only` until the user runs "Index seed knowledge" (doc [backend/02](../backend/02-storage.md)). The MockClient shows them as `indexed`, so the public demo's citations look the same.

### KnowledgeChunk (D-59, rev. 1.2)
`{ id /*kch_…*/, sourceId, index, locator?, text }`. Read with `characters.knowledgeSource(sourceId) → { source, chunks }` for the O28 Source viewer. Chunking is AI-owned (OQ-AI-03); the UI only needs stable ids and a readable locator.

## 5. Lifecycles

**Character**
```
draft (wizard: seed → … → theme) ─→ review (APPROVE step) ─(Summon)→ approved ─→ archived ─→ (deleted = tombstone)
                                                                       ↑   │            │
                                                                       │   └─(Edit / regenerate; stays approved)
                                                                       └──────(Restore)─┘
```
- **Delete leaves a tombstone (D-70, rev 1.3):** `deletedAt` is set, and the id, name, palette and neutral portrait are kept so old transcripts still render. `get` returns the tombstone, while `list` and `characterCount` skip it. Every command on it rejects with `not_found`, and deleting a character who is speaking in the live session rejects with `conflict`.
- **Approval gate:** profile valid + base portrait locked (= neutral). Other emotions may be `null`. A song is optional.
- **Only `approved` characters with `energy.state ≠ exhausted` can speak.** Exhausted characters stay in sessions but are skipped.
- Regenerating an image on an approved character creates a new version. The old one stays active until the user picks "Use new". **A song regeneration replaces the song.**

**Energy:** `active ⇄ tired ⇄ exhausted`, by lazy regeneration, drain on each reply, and top-ups.
**Session:** `active ⇄ paused → ended`. Watch mode auto-pauses at `turnLimit`. Any mode pauses when the **daily cap** is hit.
**Debate phase:** `setup → opening → rebuttal → closing → verdict → ended`. Steering may insert messages at any boundary.
**Message:** `streaming → complete | interrupted | error`.
**GenerationJob:** `queued → running → succeeded | partial | failed | cancelled`. Jobs resume after a server restart.

## 6. Streaming event contract (SSE; transport per OQ-SWE-01)

| Event | Payload | Notes |
|---|---|---|
| `turn.next` | `{ nextSpeakerId, forcedBy?, skipped? }` | ≤ 500 ms after the previous `turn.end`. `skipped` lists exhausted or muted characters |
| `turn.thinking` | `{ characterId }` | Typing "…" + lean-in |
| `turn.start` | `{ messageId, author, emotion?, variantId?, message? }` | Speaker known. `message?` (a partial `Message`) seeds fields such as `kind`, `debate` or `targetCharacterId` *(rev 1.3: documents existing code)* |
| `token` | `{ messageId, delta, variantId? }` | |
| `emotion` | `{ messageId?, characterId, emotion, source }` | **May arrive before, during or after tokens.** The UI holds ≤ 800 ms, then switches late. Ignored for display in MANUAL. *(D-51)* **without `messageId` and with `source: "user"`** it records a MANUAL `setEmotion` (face change), so Replay reproduces it |
| `message` *(D-51)* | `{ message: Message }` | A whole, **non-streamed** message: user chat, `steer`, `interject`, `direction`, `system_note`, `summary`, `verdict`. Without it, Replay can't show what the user said |
| `session.state` *(D-51, D-57)* | `{ status?, pausedReason?, state?: DebateState \| WatchState, participants?: Participant[], settings?: Partial<Pick<Session, "title" \| "titleIsCustom" \| "emotionMode" \| "musicPolicy" \| "readableMode" \| "config">> }` | Snapshot after a non-message change: verdict set, participant muted, side or cast change, or a mid-session settings change (rename, emotion mode, responder policy, auto-advance, music, Readable mode). Replaces the matching fields |
| `turn.end` | `{ messageId, status, interruptedBy?, usage, variantId?, citations? }` | `citations` arrive here (D-59), so `[n]` chips appear when the reply completes |
| `energy` | `{ characterId, current, max, state, fullAt?, spent? }` | After every drain or top-up; drives the energy bar. `spent?` = ⚡ drained by this event, added to `spentToday` *(rev 1.3)* |
| `reaction` | `{ messageId, characterId, emotion, p?, source }` | Listeners only. May be late or absent |
| `insight` | `{ messageId, trace: TurnTrace }` | After `turn.end`; never delays tokens. **A later `insight` for the same `messageId` replaces the earlier trace** (rev 1.3) |
| `phase` | `{ phase, round, iteration }` | Debate banners |
| `watch.state` | `{ status, paceMs, turnsTaken, turnLimit }` | Transport sync |
| `session.paused` / `session.resumed` | `{ reason? }` | |
| `budget.warning` | `{ scope: "daily" \| "creation", spentUsd, capUsd }` | 80% toast |
| `error` | `{ code, message, retryable, messageId? }` | `messageId?` ties the error to the message it broke (e.g. a stream cut) *(rev 1.3)* |
| `job.progress` / `task.update` / `job.done` | job/task snapshots (+ `previewUrl?`) | Generation jobs. **rev 1.3:** all three are mirrored onto the **global** stream; `jobs.subscribe(jobId)` is a snapshot plus a filter of it |

**Global stream (`onGlobal`, rev 1.3):** `entity.changed { kind, id?, worldId?, progress? }` (`progress = { stage: "extracting" | "chunking" | "embedding", pct }` during knowledge ingestion), `budget.warning`, `budget.reached`, `job.progress`, `task.update`, `job.done`, `error { error: HorizonErrorShape, context? }` and `mock.reset`. Despite its name, `mock.reset` is also emitted by the backend after "Reset demo data", so screens re-query in place.

**Commands (REST):**
- **Chat & sessions:** `send`, `stop`, `regenerate(messageId)`, `setEmotion(characterId, emotion)` (MANUAL), `setEmotionMode`, `setResponderPolicy`, `setMusicPolicy`, `everyoneAnswer`, `nextSpeaker(characterId)`, `muteParticipant(characterId, muted)`, `endSession`, `renameSession`, `forkSeedSession(sessionId, atSeq?)` *(D-51: `atSeq` = "Continue live" from the Replay playhead; omitted = the whole recording)*.
- **Debate:** `pause`, `resume`, `askCharacter(characterId, text)`, `interject(text)`, `extendRound`, `skipToClosing`, `endDebate(withVerdict: boolean)`, `pickStrongerCase(side)` (You decide).
- **Watch:** `step`, `setPace`, `direct(text)`, `extendWatch(10)`, `summarise`.
- **Energy:** `topUpEnergy(characterId, points)` (gated by D-76), `setEnergyMax(characterId, points)`.
- **Knowledge & worlds (rev 1.3):** `addKnowledge(characterId, { file } | { type: "text", title, text })`, `deleteKnowledge(sourceId)`, `reindexKnowledge(sourceId)`, `uploadCover(worldId, file)` (PNG, JPEG or WebP ≤ 5 MB).
- **Characters & jobs:** `cancelJob(jobId)`, `retryTask(taskId)`, `acceptAssetVersion(assetId)`, `archiveCharacter`, `restoreCharacter`, `deleteCharacter`, `forgetMemory(memoryItemId)`.
- **Settings:** `testConnection`, `testModel(role)`.
- **Admin (rev 1.3 addendum):** `admin.resetDemo()` re-seeds seed records only (D-70); `mock.reset` follows on the global stream.

## 7. Mock architecture for the UI phase

- The frontend talks only to a typed **`HorizonClient`** interface. The UI phase ships a **`MockClient`**. SWE later adds an **`HttpClient`**, and swapping them is a one-line change.
- **Fixtures** live as JSON under `seed/` in the shapes above. The backend imports the **same files** for seeding.
- The MockClient **replays SessionEvent scripts** with the timings from one config (APP-07) and a demo-speed multiplier. It simulates energy drain and regeneration with the same formula as the backend.
- The **Mock State Switcher** (APP-08) selects fixture or failure scripts. Required fixtures are listed in doc 06 §9.
- Fixtures are validated against this contract (JSON Schema or zod generated from it).

## 8. Example: debate message (fixture form)
```json
{
  "id": "msg_seedD08", "seq": 8, "sessionId": "ses_seedDebate4Day",
  "author": { "type": "character", "characterId": "chr_seedMei" },
  "kind": "chat",
  "content": "Honestly? Nobody can give you one reliable number…",
  "status": "complete",
  "emotion": "thinking", "emotionSource": "llm", "forcedSpeaker": true,
  "debate": { "phase": "rebuttal", "round": 2, "iteration": 1, "side": "opp" },
  "reactions": [
    { "characterId": "chr_seedVictor", "emotion": "thinking", "p": 0.64, "at": "2026-10-01T10:03:20Z" },
    { "characterId": "chr_seedAmara", "emotion": "thinking", "p": 0.58, "at": "2026-10-01T10:03:20Z" }
  ],
  "usage": { "tokensIn": 9800, "tokensCached": 7800, "tokensOut": 168, "costUsd": 0.00042, "energySpent": 5, "firstTokenMs": 1420, "totalMs": 5600 },
  "trace": {
    "model": { "id": "deepseek/deepseek-v4.1-flash", "provider": "DeepSeek", "pricePeriod": "off_peak",
               "latencyMs": { "firstToken": 1420, "total": 5600 }, "tokensIn": 9800, "tokensCached": 7800, "tokensOut": 168, "costUsd": 0.00042 },
    "energy": { "characterId": "chr_seedMei", "spent": 5, "remaining": 742, "max": 1000 },
    "emotion": { "chosen": "thinking", "source": "llm", "candidates": [ { "label": "thinking", "p": 0.71 }, { "label": "neutral", "p": 0.18 } ] },
    "routing": { "selected": "chr_seedMei", "forcedBy": "user_ask" },
    "contextInSession": [ { "text": "R1: Mei: pilots were voluntary, self-selected firms", "messageId": "msg_seedD03" } ],
    "context": { "budget": 12000, "cacheHitPct": 80,
                 "used": { "system": 900, "persona": 700, "memory": 0, "knowledge": 0, "history": 6900, "user": 40, "mode": 580 } }
  },
  "createdAt": "2026-10-01T10:03:14Z"
}
```
*Cost: 2,000 uncached tokens × $0.15/M + 7,800 cached × $0.003/M + 168 out × $0.60/M ≈ $0.00042 (off-peak, first-party) → 4.2 ⚡, rounded up to 5 ⚡.*
