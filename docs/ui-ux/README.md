# Horizon UI/UX Spec: Lead Rulings & Build Plan (Stage 2)

> **Status:** v1.0 · 2026-10-02 · **Owner:** Lead UI/UX
> **Inputs:** the requirements pack in [`docs/requirements/`](../requirements/README.md), which stays the source of truth, plus three Round-1 position papers in [`papers/`](papers/):
> - [UX Architect](papers/r1-ux-architect.md): IA, compositions, interaction, focus
> - [Visual & Motion Director](papers/r1-visual-motion.md): visual language, motion, placeholders, audio recipes, covers
> - [Experience Engineer](papers/r1-experience-engineer.md): architecture, MockClient, performance, testing
>
> **Precedence:** where this document and a paper disagree, **this document wins**. Where it is silent, the paper for that remit applies. Requirement changes raised by this team are logged as **D-51…D-55** in [doc 09](../requirements/09-decision-log.md).

---

## 1. Lead rulings

All three papers are adopted, with these rulings on overlaps and conflicts.

| # | Ruling | Source |
|---|---|---|
| R1 | **One event pipeline.** Live mock, Replay, demo mode and the future `HttpClient` all emit doc 05 §6 events into one pure `applyEvent(state, evt)` reducer. The MockClient builds an event script for each turn and plays it through the same `ScriptPlayer` that Replay uses, on a virtual clock (demo speed ×1/×2/×4, pause, seek). | EE D1 |
| R2 | **Seed sessions are generated from typed screenplays** (doc 06 transcripts) into committed JSON under repo-root `seed/`. `npm run seed:build` regenerates them, and `seed:check` fails on any diff. `msg_seedD08` must match doc 05 §8 exactly. | EE D2 |
| R3 | **Custom hash router (~150 lines), no react-router.** The transition layer is `pointer-events:none`, the screen swaps at the cover point, and a second navigation supersedes the first. | EE D3 |
| R4 | **Routes are places, overlays are one `LayerStack`** (kinds: `modal`, `drawer`, `popover`, `ceremony`, `ambient`). **Esc order:** popover → dock expansion → modal → drawer → blur text field → pause menu. | UXA D1 |
| R5 | **One `SessionScreen` for S07/S09/S10/S12.** Mode picks the layout, and the bottom **Dock** swaps: `Composer` · `SteeringBar` · `Transport` · `ReplayTransport` · `DemoDock`. Ask…, Interject, Director's note and Step in are **DockExpansions** that slide up from the dock and keep their draft (O12). | UXA D2, D3 · D-53 |
| R6 | **Ceremonies never block input** (D-55). UXA's `useCeremony` and VMD's `MotionConductor` are merged into one module, `motion/conductor`: a single queue, one punctuation at a time. Any key or click skips to the end state in ≤ 120 ms, and the key is replayed. | UXA D4 + VMD D3 |
| R7 | **Slants use `clip-path` polygons, never `skewX` on text containers.** Tilt tokens: `--tilt -12deg`, `--tilt-soft -8deg`, `--stripe 14deg`. | VMD D1 |
| R8 | **"Shadow Self" placeholder portraits** (D-52), rendered by one pure `renderShadowSvg(spec) → string`. The seed build writes them as static `.svg` files, and wizard-made characters use data URLs. The "PLACEHOLDER · EMOTION" tape is a DOM overlay shown only for `/placeholder/` URLs. **The `ShadowSpec` is derived from `Appearance`** (hair length and style, glasses, accessories), so wizard characters get matching silhouettes. | VMD D2 |
| R9 | **Scoped palettes in multi-character scenes** (D-54): chrome stays house orange; a palette lives only in its character's frame, plate and energy bar; the speaker tints the stage band. PROP tape = `horizon-500`, OPP tape = `paper-50`, both with ink text. Single-character screens (S06, S07, the wizard) theme the whole app root. | VMD D4 |
| R10 | **Palette changes snap under the flood**: the class flips at the flood's peak, and CSS variables are never interpolated. Flood opacity is ≤ 0.85 (0.35 on Low, a fade when Off), at most once per second. | VMD + EE |
| R11 | **Procedural "SKETCH" audio** (D-52). Every sound is an `AudioBuffer`: decoded from a file, or rendered once with `OfflineAudioContext` from a spec. **Swapping to real audio is a URL change only** (see §3.6). The mini-player shows `· SKETCH` for procedural tracks. | VMD D5 + EE D5 |
| R12 | **Hot paths bypass React:** token deltas are coalesced to one store write per frame, and a `StreamSmoother` reveals text. Parallax and particles run on refs and one global ticker. Markdown renders on `turn.end`. | EE D4 |
| R13 | **History (S13) is the hub's Sessions tab** (`#/w/:wid?tab=sessions`), and the pause menu deep-links to it (D-53). | UXA |
| R14 | **Group layout = wings** of portraits on both sides of a full-height centred log. **Watch = proscenium row** with a subtitle-style script above it. **Debate = side columns.** 1:1 Insight **compresses the stage, not the log** (log ≥ 520 px). | UXA §2.2 · D-53 |
| R15 | **Demo mode = "recordings play; live actions ask for a key".** Blocked controls look enabled with a small key glyph and open O05. A resumed seed session shows `DemoDock`. **Any string starting `sk-or-` counts as a valid mock key** (`sk-or-bad…` → invalid key). | UXA + EE |
| R16 | **"Continue live" forks from the Replay playhead** (`forkSeedSession(id, atSeq)`, D-51). With no playhead (opened from History), the whole recording is forked. | UXA, BA addendum |
| R17 | **Build order = hero slice first.** M1 Showreel: Title → Worlds → Hub → **Debate Replay** + VS + Insight → Verdict. M2 Talk: 1:1 live + Profile + Energy. M3 Create: Wizard + Summon. M4 Ensemble & states. In practice all four ship before the stakeholder review; the milestones set **polish priority**. | UXA D5 |
| R18 | Fonts: **Latin subsets only** (Dela Gothic One ships CJK otherwise). The title waits on `document.fonts.load`, capped at 800 ms. | VMD, EE |
| R19 | Exhausted desaturation is a **static greyscale duplicate layer** whose opacity fades in. `filter` is never animated. VFX Off and reduced motion keep a **static badge** (💤, blush), so tired and exhausted states still read. | VMD |
| R20 | **Performance budgets** (EE §2.9) are acceptance criteria. A PerfHUD (`Ctrl+Shift+P`) ships in dev builds. | EE |

### Lead rulings on gaps none of the papers settled
- **Types:** [`frontend/src/contract/types.ts`](../../frontend/src/contract/types.ts) is the hand-written TypeScript transcription of doc 05 (rev 1.1) and is canonical. Zod schemas in `contract/schemas.ts` validate fixtures and are checked against those types (`satisfies z.ZodType<T>`).
- **`SessionEvent.at` is ISO-8601**, as everywhere else. Replay derives pacing from the deltas, clamping gaps over 2.5 s (the trim can be switched off).
- **Persistence:** the mock DB snapshots to `localStorage`, keyed by a fixture hash. "Reset demo data" clears it. Prefs are persisted separately.
- **First run:** no key, so demo mode, so Onboarding. The O18 switcher has a "Set mock key" shortcut for reviewers.
- **Visual QA:** the foundation ships a **Kit Gallery** at `#/dev/kit` (every primitive, all portraits × 7 emotions, every VFX, energy state and transition). It's used for screenshot review and hidden in Presenter Mode.

---

## 2. Architecture

```
seed/                              # repo root: committed fixtures (doc 05 shapes), imported by the backend later
  settings.json palettes.json style-presets.json system-tracks.json pricing.json
  worlds/ characters/ memory/ knowledge/ usage/ jobs/
  sessions/<id>/{session,messages,events}.json
  assets/placeholder/portraits/<characterId>/<emotion>.svg (+ blink.svg, cand-2.svg)
  assets/placeholder/themes/<characterId>.proc.json
  _mock/                           # UI-phase-only variants (exhausted Takeshi, debate variants…); backend ignores
frontend/
  scripts/seed-build/              # screenplays/, build.ts, check.ts, budget.ts (vite-node)
  src/
    contract/   types.ts (canonical) · schemas.ts (zod) · errors.ts
    client/     HorizonClient.ts (interface) · index.ts (one-line Mock→Http swap)
    mock/       MockClient.ts · db/ · time/{Clock,Scheduler} · timing.config.ts · pricing.config.ts
                engines/{oneOnOne,group,debate,watch,jobs} · banks/ · scenarios/
    engine/     sessionReducer · ScriptPlayer · StreamSmoother · emotionHold · musicDirector
    domain/     energy · cost · rushHour · format
    stores/     entities · session · streamText · ui (layers, toasts, insight) · prefs · mock
    router/     routes · navigate · useRoute · hash sync
    app/        App.tsx · routes registry · overlays registry · shortcuts · providers
    audio/      engine/ (EE: buses, decks, duck, unlock) · synth/ (VMD: procedural renderers) · resolve.ts
    styles/     tokens.css · palettes.css · motion.css · base.css · fonts.ts
    theme/      palettes.ts · PaletteScope · appPalette (flood + snap)
    ui/         primitives (see §3.7)
    character/  PortraitCard · NamePlate · EnergyBar · EmotionVfx · emotionMeta
    vfx/        shadow/ (renderShadowSvg, specFromAppearance) · particles canvas · covers
    motion/     transitions (Slash, Shatter, Flood, Fade) · TransitionLayer · conductor (ceremonies)
    features/   shell · worlds · wizard · profile · session · ensemble · insight · settings · dev
```

Vite serves `seed/assets` at `/assets` with a tiny plugin, which matches the backend's asset URLs (doc 05 §1).

---

## 3. Seams: interfaces frozen before the builders start

These signatures are a contract between the two foundation owners and the four builders. **After the foundation phase they change additively only.**

### 3.1 Router (EE)
```ts
type Route =
  | { name: "title" } | { name: "onboarding"; card?: number } | { name: "worlds" }
  | { name: "hub"; worldId: string; tab?: "roster" | "sessions"; filter?: string }
  | { name: "profile"; worldId: string; characterId: string; tab?: ProfileTab }
  | { name: "wizard"; worldId: string; characterId?: string; step?: CreationStep; edit?: boolean }
  | { name: "setup"; worldId: string; step?: "mode" | "cast" | "config"; mode?: "group" | "debate" | "watch"; cast?: string[] }
  | { name: "session"; worldId: string; sessionId: string; replay?: boolean; t?: number }
  | { name: "verdict"; worldId: string; sessionId: string }
  | { name: "settings"; tab?: SettingsTab; from?: string }
  | { name: "dev"; page: "kit" };
navigate(route: Route, opts?: { transition?: TransitionKind; origin?: { x: number; y: number }; sourceEl?: HTMLElement; replace?: boolean }): void
back(): void;  useRoute(): Route
```
Default transition is `slash`; World card → Hub is `shatter`; back plays a reversed slash.

### 3.2 Transitions & ceremonies (VMD)
```ts
type TransitionKind = "slash" | "slash-back" | "shatter" | "flood" | "fade" | "none";
runTransition(kind, { origin?, sourceEl?, color?, onCover: () => void }): { cancel(): void; done: Promise<void> }
<TransitionLayer />  // mounted once by App
playCeremony(id: string, opts: { durationMs: number; onSkip?: () => void }): { skip(): void; done: Promise<"done" | "skipped"> }
useCeremony(id): { active: boolean; skipped: boolean }   // components render their end state when skipped
setAppPalette(paletteId: string | null, opts?: { flood?: { x: number; y: number } }): void   // null = house palette
```
Reduced motion turns every transition and ceremony into a fade of ≤ 200 ms (160 ms recommended).

### 3.3 Layers, overlays, toasts, shortcuts (EE)
```ts
openOverlay<Id extends OverlayId>(id: Id, props?: OverlayProps[Id]): void;  closeOverlay(id): void
// overlays registry maps O-ids → { kind, component }; Esc handling and focus trap/restore are central
toast({ variant: "success" | "info" | "warn" | "error", text: string, action?: { label: string; run(): void } }): void
useShortcut(combo: string, handler: (e) => void, opts?: { allowInInput?: boolean; when?: () => boolean }): void
isTypingTarget(el): boolean
```

### 3.4 Client & data hooks (EE)
- `client: HorizonClient`: namespaces `settings`, `worlds`, `characters`, `jobs`, `sessions`, `chat`, `debate`, `watch`, `usage`, plus `onGlobal(cb)` (EE §2.2). Queries return Promises. Commands acknowledge, and their results arrive as events. Errors reject with `HorizonError { code: ErrorCode; message; retryable }`.
- **Hooks:** `useSettings()`, `useWorlds()`, `useWorld(id)`, `useCharacters(worldId, { includeArchived? })`, `useCharacter(id)`, `useSessions(worldId)`, `useJob(jobId)`, `useUsage()`, `useMemory(characterId)`, `useKnowledge(characterId)`.
- **Session runtime:** `useSessionRuntime(sessionId, { replay?: boolean })` returns:
  - **State:** `{ session, messages, order, participants (with displayEmotion), energyById, phase, watch, nextSpeakerId, thinkingId, streamingId, paused, pausedReason, errors }`.
  - **Controls:** `{ play, pause, seek, rate }` for replay.
- `useStreamText(messageId)`: the smoothed live text.
- `useEnergy(characterId)`: the live energy with lazy regen applied, `{ current, max, state, fullAt, pct }`.
- `useRushHour()`: `{ peak, nextChangeAt }`.

### 3.5 Portrait, plate, energy (VMD)
```tsx
<PortraitCard character={c} emotion={e} size="hero" | "stage" | "card" | "thumb" | "head"
  speaking? listening? dimmed? energyState? parallax? reaction?  // reaction = mini VFX burst
  showPlate? showEnergy? onClick? onContextMenu? />
<NamePlate character={c} size="lg" | "md" | "sm" subtitle? />
<EnergyBar characterId={id} | energy={…} size="stage" | "chat"   // 6 px | 10 px
  showLabel? onTopUp? />                                            // drain ghost, regen sheen, top-up sparks, −N float
<EmotionVfx emotion={e} prev={p} intensity="full" | "subtle" | "off" mini? />
emotionMeta: Record<Emotion, { label; icon; hotkey: 1..7; vfx: VfxPreset; sfx: SfxId }>
```
`PortraitCard` preloads and `decode()`s all of a character's emotion images on mount, crossfades in ≤ 300 ms with a 1.02→1 settle, and falls back to neutral + VFX + tint for `null` emotions (EMO-06).

### 3.6 Audio (EE engine + VMD synth)
```ts
audio.unlock(): Promise<void>                  // first gesture (APP-01)
audio.playSfx(id: SfxId): void
audio.setMusic(url: string | null, opts?: { crossfadeMs?: number; label?: string }): void   // null = silence
audio.duck(): void                              // stings: 40 %, 600 ms release
audio.setVolumes(…) / mute(…)                   // from prefs
resolveAudio(url: string): Promise<AudioBuffer> // VMD
```
`resolveAudio` URL schemes:
- `*.proc.json`: fetch the spec, then `renderTheme(spec)`.
- `placeholder:sfx/<id>`: a built-in SFX recipe.
- `placeholder:system/<main_theme | arena | ambient_bed>`: a built-in system track.
- Anything else: fetch + `decodeAudioData`.

### 3.7 Primitives (VMD), in `src/ui/`
`Button` (slash shape; variants `primary | secondary | ghost | danger`; sizes; `cost` badge; `keyLocked` glyph), `IconButton`, `Tape`, `RansomText`, `Chip`/`ChipGroup` (single and multi, with max), `Swatch`, `Tabs`, `Toggle`, `Segmented`, `Slider`, `TextField`/`TextArea` (counter, error, edited dot, ↻ regenerate slot), `Select`/`Menu` (skewed popover), `Modal` (frame; stacking is EE's), `Drawer` frame, `ToastView`, `Skeleton` (skewed), `EmptyState` (silhouette + tape + CTA), `ErrorTape` (red WARNING + action), `ProbBar` (`0.71 · HIGH` band), `StackedBar`, `CostBadge` (`≈ $0.04`), `Kbd`, `Tooltip`, `Spinner`-free loaders (scanning stripe, halftone develop), `WorldCover` (8 presets).

---

## 4. File ownership

**Foundation phase** (two agents in parallel, then integration by the Lead):

| Owner | Writes only in |
|---|---|
| **EE: Engine & Platform** | `seed/**`, `frontend/scripts/**`, `frontend/vite.config.ts`, `frontend/package.json` (scripts and deps), `src/contract/**`, `src/client/**`, `src/mock/**`, `src/engine/**`, `src/domain/**`, `src/stores/**`, `src/router/**`, `src/audio/engine/**`, `src/app/**`, `src/main.tsx`, `src/features/dev/**`, and **stub files for every feature screen and overlay** (one exported component each, so registries compile) |
| **VMD: Visual Kit** | `src/styles/**`, `src/theme/**`, `src/ui/**`, `src/character/**`, `src/vfx/**`, `src/motion/**`, `src/audio/synth/**`, `src/audio/resolve.ts`, `src/features/dev/kit/**` (Kit Gallery) |

**Builder phase** (four agents in parallel). Each builder writes only in its own feature folders, using CSS Modules, and **replaces the stubs it owns**. Changes to shared directories are additive, and each is listed in the builder's hand-back.

| Builder | Owns | Screens & overlays |
|---|---|---|
| **A: Shell & Worlds** | `features/shell/`, `features/worlds/`, `features/settings/` | S01 Title, S02 Onboarding, S03 World Select, S04 Hub (+S13 Sessions tab), S14 Settings (all 8 tabs, Spend view), O01 Pause, O02 World, O03 Confirm, O05 Key required, O19 Desktop guard, O20 Shortcuts, O21 Budget, O22 Demo tape, mini-player + O09 |
| **B: Creation & Profile** | `features/wizard/`, `features/profile/` | S05 Wizard (8 steps, both emotion variants B/C), O04 Cost confirm, O13 Unsaved draft, O15 Summon, S06 Profile (6 tabs + energy panel), O06 Lightbox, O25 Old/New, job pill |
| **C: Session core & 1:1** | `features/session/`, `features/insight/` | SessionScreen frame, Log + message rendering (bubbles, Readable panel, system notes, errors, stopped/interrupted), Composer (+O11 mentions), S07 layout, O07 Emotion picker, O08 Insight, O10 Backlog, O23 ReplayTransport, DemoDock, O27 Top-up, speaker cut-in, mini-player music hookup for sessions |
| **D: Ensemble** | `features/ensemble/` | S08 Setup, S09 Group, S10 Debate, S12 Watch layouts; SteeringBar, Transport, DockExpansions (O12); O16 VS / Round banner; O17 Episode end; O24 Portrait menu; O26 End debate; S11 Verdict |

**SessionScreen seam:** C owns `features/session/SessionScreen.tsx`, and it picks `layouts[mode]` and `docks[kind]` from `features/session/registry.ts`. EE pre-fills that registry with stubs that point into `features/ensemble/`, and D replaces those stubs. D uses C's exported `<SessionLog>` and `<Composer>`. Until C lands them, D works against the foundation's minimal versions.

---

## 5. Definition of done (stakeholder review gate)

1. `npm run dev` opens Title → Onboarding (first run) → World Select. Every screen S01–S14 and overlay O01–O27 is reachable.
2. **F1–F6 (doc 03 §4) run end to end** against the MockClient at ×1, and every O18 scenario lands on the current screen.
3. All 5 seed sessions **replay** with emotions, reactions, energy drains, banners and Insight data. Each one can "Continue live" (with a mock key).
4. `npm run typecheck`, `npm test` (reducer, energy, rush hour, musicDirector, fixture validation, replay equivalence, client contract) and `npm run build` all pass. Bundle budgets pass.
5. Reduced motion, VFX Off, Presenter Mode and the 1280×720 layouts have all been checked.
6. Every placeholder is labelled, and real assets swap in **by URL only**.
