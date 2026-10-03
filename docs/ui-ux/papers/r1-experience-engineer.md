# R1: Experience Engineer, position paper

## 1. Top 5 decisions

**D1. One event pipeline.** Live mock, Replay, demo mode and the future `HttpClient` all emit doc 05 §6 `SessionEvent`s into one pure reducer, `applyEvent(state, evt)`. For each turn the MockClient *generates a script* (`SessionEvent[]`) and plays it through the same `ScriptPlayer` that Replay uses (play/pause/seek/rate on a virtual clock). *Why:* there is one engine to test, and SWE inherits a UI already proven against the wire shapes.

**D2. Seed sessions are generated, not hand-typed.** Doc 06 transcripts become typed **screenplays** (speaker, emotion, text, reactions, steer/direction/face beats, trace overrides). A generator writes the contract JSON, including traces, costs and energy. The output is committed because the backend imports the same files, and `seed:check` fails CI on any regeneration diff. *Why:* about 2,000 hand-written token events and 30 traces would drift within a day.

**D3. Custom router (~150 lines) plus hash sync. No react-router.** The transition is a **non-blocking overlay**: `TransitionLayer` is `pointer-events:none`, the screen swaps at the *cover point*, and a second `navigate()` supersedes the first. *Why:* we need exact swap timing, the Shatter source rect and clear cancel rules, and react-router brings a data model we don't use. Input is never blocked, so APP-03 AC2 holds by construction.

**D4. Hot paths bypass React.**
- Tokens, parallax, particles and energy ticks never call `setState` per frame. They use rAF coalescing, refs, one global `ticker`, and one particle `<canvas>` per stage.
- Palettes **flip under the Palette Flood cover**. We never transition custom properties, because that recalculates style for the whole tree every frame.

**D5. Audio is buffer-only and lives outside React.** Every sound is an `AudioBuffer`: either decoded from a file, or rendered once via `OfflineAudioContext` from a procedural spec (`*.proc.json`). Replacing a placeholder with a real asset is therefore **a URL change only**. The graph has two buses, a duck node and A/B music decks.

## 2. Remit

### 2.1 Folder structure
```
seed/        settings, palettes, style-presets, system-tracks, pricing .json
             worlds/ characters/ memory/ usage/ jobs/ sessions/<id>/{session,messages,events}.json
             assets/placeholder/…  (generated SVG portraits/covers, theme *.proc.json)
             _mock/  (UI-phase-only overlays: exhausted Takeshi, debate variants; backend ignores)
frontend/scripts/seed-build/   screenplays/ build.ts placeholders.ts check.ts budget.ts  (run by vite-node, ships with vitest)
frontend/src/
  contract/  zod schemas = the type source (z.infer), events, errors
  client/    HorizonClient.ts, index.ts (one-line Mock→Http swap)
  mock/      MockClient, db/, time/{Clock,Scheduler}, timing.config.ts, pricing.config.ts,
             engines/{oneOnOne,group,debate,watch,jobs}, banks/, scenarios/
  engine/    sessionReducer, ScriptPlayer, StreamSmoother, emotionHold, musicDirector
  domain/    energy, cost, rushHour, format
  stores/ router/ audio/ vfx/ ui/(primitives) styles/ hooks/
  app/       registries: routes.ts, overlays.ts, shortcuts.ts
  features/  shell worlds creation profile chat ensemble insight history settings dev
```
A tiny Vite plugin serves `seed/assets` at `/assets`, matching backend URLs.

### 2.2 `HorizonClient`
- **Contract:** queries return Promises. Commands return a `Promise<void>` acknowledgement and deliver their results as events (like SSE). Synchronous failures reject with `HorizonError`.
- **Namespaces:**
  - `settings` (get/update/setKey/testConnection/testModel)
  - `worlds` (CRUD)
  - `characters` (list/get/createDraft/update/approve/archive/restore/delete/acceptAssetVersion/topUpEnergy/setEnergyMax/memory/knowledge)
  - `jobs` (start/cancel/retryTask/listActive/subscribe)
  - `sessions` (list/get/create/rename/delete/fork/messages/trace/events/export/**subscribe(id, {sinceSeq}, cb)**)
  - `chat` · `debate` · `watch` (the doc 05 §6 commands exactly)
  - `usage`
  - `onGlobal(cb)` (budget, job.done, errors → toasts)
- **`sinceSeq`** works like Last-Event-ID: fetch the snapshot, then subscribe from its `seq`, so nothing is lost.

### 2.3 MockClient engine
- **Scheduler:** virtual time = real time × demo speed (×1/×2/×4). Pause freezes it and a speed change rebases it. Tests drive it with `ManualClock.advance()`.
- **Timings:** come from the single APP-07 `timing.config.ts`. Scenarios patch them.
- **Live fake AI:**
  - **Lines:** per-character banks of emotion-tagged lines, matched to the user's text by keyword score, otherwise rotated. A PRNG seeded by `sessionId+turn` makes reviews repeatable. Wizard-made characters use `banks/generic.ts`, which templates over their profile.
  - **Group:** mentions first, then up to 2 by score. Exhausted or muted characters are skipped with a `system_note`, and routing candidates go into the trace.
  - **Debate:** walks the `DebateConfig` phases, alternating sides. Verdict scores come from the PRNG and honour panel / none / You decide.
  - **Watch:** alternates speakers. A director's note switches the bank category.
  - **Emotion timing:** 70% arrive before the first token, 25% within 800 ms, 5% late.
  - **Reactions:** p=0.7 each, 300–800 ms after `turn.end`.
- **Energy:** `domain/energy.ts` is shared verbatim with the mock.
  - Regen: `min(max, cur + max/24·h)`.
  - Drain: `ceil(costUsd/0.0001)`, where cost = tokens × pricing table, ×2 in MYT rush hour.
  - The daily cap warns at 80% and emits `session.paused(daily_budget)` at 100%.
  - Demo mode freezes regen (ENG-07).
- **Jobs:** 2 image tasks in parallel, `job.progress` every 250 ms, and `previewUrl` at 50%. Jobs live in the client, so they survive navigation.
- **Scenarios (O18) are data:** `{settingsPatch, datasetOverlay, faults{command|stream|job}, timingPatch}`.
  - *Stream cut* = an `error(network)` after N tokens, then `turn.end(interrupted)`.
  - *Partial image failure* = task 2 fails at 60%, and Retry succeeds.
  - Applying a scenario re-seeds the DB and emits `mock.reset`. Screens re-query in place.
- **Deep links:** `#/…?scenario=rate_limited&speed=2` opens straight into a state.
- **Persistence:** the mock DB snapshots to localStorage, keyed by a fixture hash. "Reset demo data" clears it.

### 2.4 Screenplay → fixtures
The generator:
- assigns `seq`, `at` (from the timing config) and IDs;
- chunks the text into ~4-token deltas;
- synthesises a trace for every character message (overrides allowed: `msg_seedD08` must equal doc 05 §8);
- **back-computes starting energy** so each session *ends* at the doc 06 values (Mei = 742).

Replay animates the drains in a **sandboxed energy overlay** and never writes to characters. The same build emits placeholder portraits (42 SVGs, ≤ 8 KB each) and themes (`.proc.json` built from each theme brief). Flipping `assetSource:"real"` rewrites the URLs to the sprint's files.

### 2.5 Routing
- **Routes** are a typed union: `title | onboarding | worlds | hub | wizard | profile | chat | setup | session(replay?) | verdict | history | settings`.
- **Navigation:** `navigate(route, {transition, origin})` → `TransitionLayer` runs a CSS/WAAPI animation and calls `commit(id)` at the cover point: Slash 200 ms, Flood 240 ms, Shatter 0 ms (the hub fades in under the shards). A stale `id` is ignored.
- **No stutter:** compositor animations keep running while the screen mounts (inside `startTransition`). Back/forward plays a reversed Slash.
- **Overlays** are a `ui` stack, not routes. `Esc` pops the top one.
- **Prefetch:** route chunks prefetch on idle after the title.

### 2.6 Zustand slicing
- **Stores:** separate vanilla stores, read through selectors.
  - `router` and `entities` (normalised, filled by the client)
  - `session` (the reducer output for the active session)
  - `streamText` (its own map, so only `<StreamingMessage id>` re-renders)
  - `ui` (overlays, toasts, Insight selection), `prefs` (persisted), `audio`, `mock`
- **Streaming:** token deltas coalesce into one write per frame. `StreamSmoother` reveals text at an adaptive rate (lag ≤ 150 ms), so coarse fixtures and bursty SSE both look smooth. `react-markdown` runs once, on `turn.end`.

### 2.7 Theming
- `tokens.css` holds the house tokens. The generated `palettes.css` holds one `.pal-ocean_clinic{--pal-primary:…}` class per palette.
- The class is scoped on the app root, and per portrait card on multi-character stages.
- **Committed change:** the flood scales over the screen and the class flips at full cover (~240 ms), for 400 ms in total.
- **Hover:** an instant swap, debounced 120 ms.
- **Reduced motion:** a 200 ms opacity crossfade.

### 2.8 Audio
- **Graph:** `deckA/B → music → duck → master` and `sfx → master`.
- **Crossfade:** equal-power, ≤ 2 s.
- **Ducking:** to 0.4 with a 60 ms attack and a 600 ms release.
- **Loops:** rescheduled 1 s early with an overlap crossfade. `gainDb` is applied per track.
- **Clicks:** every start and stop gets a 5 ms ramp, so there are no clicks.
- **SFX:** ~20 procedural SFX are pre-rendered into buffers on unlock, so latency is under 5 ms.
- **`musicDirector`:** a pure function `(session, now) → track` that encodes the 20 s dwell and the Arena/verdict rules.
- **Hidden tab:** `ctx.suspend()`.

### 2.9 Performance budgets
| Budget | Target | Verified by |
|---|---|---|
| Entry JS | ≤ 150 KB gz (`motion` via `LazyMotion`); route chunks ≤ 60 KB; react-markdown lazy | `budget.ts` (zlib over `dist/`, fails CI) |
| Fonts | ≤ 450 KB woff2 latin subsets; title waits on `document.fonts.load` (cap 800 ms) | `budget.ts` |
| Frames | 60 fps, < 2% dropped: Debate replay ×4, 5 portraits, VFX Full, Insight open, 4× CPU throttle | **PerfHUD** (Ctrl+Shift+P: fps, `longtask` observer, commit count) + DevTools checklist |
| Idle | no task > 50 ms | PerfHUD |
| Emotion swap | starts ≤ 100 ms, done ≤ 300 ms; sprites `decode()`d at session open | vitest on `emotionHold` + `performance.measure` |

### 2.10 Testing (vitest)
- **Unit:** reducer, energy, cost, rushHour, emotionHold, musicDirector, Scheduler, router cancel, each mock engine.
- **Fixtures:** zod validates every `seed/**` file. Integrity checks: no cross-world references (NFR-23), monotonic `seq`/`at`, and every character message has a trace.
- **Replay equivalence:** reducing `events.json` must reproduce `messages.json` exactly.
- **`clientContract.test.ts`:** runs against MockClient now and HttpClient later. It is SWE's executable spec.

### 2.11 Shared foundation and ownership
**The EE builds the foundation in 2–3 days, before the builders fork:**
- scaffold, contract, the MockClient skeleton, reducer, ScriptPlayer, all stores, router and TransitionLayer (Fade + Slash);
- tokens, palettes and fonts; motion tokens (as CSS variables *and* TS constants); `data-motion` reduced-motion plumbing;
- the focus-aware, overlay-scoped shortcut manager, the audio API, the ticker, and the dev overlays;
- primitives with final APIs: `Button`, `SkewPanel`, `Tape`, `RansomTitle`, `PortraitCard`, `NamePlate`, `EnergyBar`, `Chip`, `Modal`, `Toast`, `Skeleton`, `Icon`.

**Builders:**
- **A, Shell & Worlds:** S01–S04, S13, S14, O01–O03, O19, O22
- **B, Creation & Profile:** S05, S06, O04, O06, O13, O15, O25, job pill
- **C, Conversation:** S07, log/composer, O07–O10, O27, VFX, cut-ins
- **D, Ensemble:** S08–S12, O11, O12, O16, O17, O23, O24, O26

**Ownership rules:**
1. Builders write only in `features/<own>/**`, using CSS Modules.
2. Shared directories change through an EE-reviewed "foundation PR". The API is frozen after day 2; only additive changes after that.
3. Registries (routes, overlays, shortcuts, SFX ids, VFX presets) are **pre-populated** with every entry, pointing at placeholders. Each builder replaces only its own lines.
4. Each bank and screenplay file has one owner, the matching builder.
5. New primitives incubate in their feature, then get promoted.

## 3. Risks, gaps and resolutions
**Inside UI/UX:**
- **Replay dead air.** Gaps over 2.5 s are clamped; the trim is on by default and can be switched off.
- **Slow defaults tire reviewers.** The Switcher remembers ×2, and the ×N badge stays visible.
- **Procedural music sounds cheap.** Keep it to a filtered pad, bass and arpeggio at volume 0.6, and swap the day the sprint delivers.
- **Placeholders look broken.** Each must show palette, name and emotion distinctly.
- **Mock key.** Start keyless (F1); any `sk-or-…` string enables live mock.

**BA loop-back (a tiny doc 05 addendum; schemaVersion stays 1):**
1. **Replay can't reproduce user, steer, direction, system_note or verdict messages.** No event carries them. Add `message {message}`.
2. **MANUAL `setEmotion` has no message.** Make `emotion.messageId` optional, with `source:"user"`.
3. **No event for verdict, mute or state changes.** Add `session.state {state, participants?}`.
4. **No rush-hour signal.** Add `AppSettings.pricing {period, nextChangeAt}`. The UI derives it from the MYT clock meanwhile.
5. **§6 lists commands only.** The queries and creation calls in §2.2 need SWE sign-off (OQ-SWE-01).

## 4. Wow vs. unsatisfied
**Wow in 30 s:**
- The first keypress fires a synced sting as HORIZON slams in.
- Shatter holds a locked 60 fps.
- A palette click floods the UI *and* crossfades the music on the same beat.
- The debate replay streams buttery text while faces react and Insight fills live.
- Ctrl+Shift+D → "Stream cut" lands instantly, mid-screen.

**Unsatisfied:**
- Streaming stutter
- Fonts popping in after an animation
- Audio clicks or loop-seam pops
- Grey-box placeholders
- Transitions that swallow clicks
- 40 s at ×1 with nothing alive on screen
