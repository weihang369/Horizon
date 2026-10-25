# QA round 1: E2E suite and UX findings

Branch `feat/ui-hardcoded-frontend` @ `5074dc7` · 3 Oct 2026 · Test engineering.
For: the UI/UX team (act before the design freeze) and the project owner.

## 1. Summary

| | |
|---|---|
| Suite | 24 specs in `frontend/e2e/` (9 files); 30 runs across two projects |
| Result | **30 passed**, 0 failed, 0 flaky. 2 of the passes are `test.fail()` specs that pin real bugs (QA-01, QA-02) and will flip to "unexpected pass" when they are fixed |
| Run time | 2.2 min, 1 worker (Edge 154, Windows 11) |
| Findings | **P0: 0 · P1: 2 · P2: 6** |
| Gates | `npm run typecheck`, `npm run lint` and `npm test` are green. The e2e folder is now type-checked by `tsc -b` |

**Bottom line:** no demo blockers. Every path a LinkedIn viewer would take works: onboarding, World Select, hub, debate replay to verdict, citations and O28, Insight, Knowledge, Theme, the wizard to Summon, and the live mock. Fix the two P1 keyboard defects before recording a demo. They hit exactly the keys the README tour advertises (End/←/→ on a replay, and L).

### How to run

> **Since M6 (`http-client-parity`) the suite runs on both clients.** The projects are now `mock-desktop`, `mock-min` (the `@layout` specs at 1280×720) and `http-desktop`. `http-desktop` runs every spec against a test-mode backend on :8786 through a `--mode http` Vite on :5187, with a factory reset before each test. Mock-only steps became client-aware fixtures (`setKey` through Settings → Connection, `setScenario`, `genTimeout`), and a 4xx the test expects is declared with `expectHttpError`. The commands below describe round 1; today run `npm run e2e` (both clients), `npm run e2e:mock` or `npm run e2e:http`.

```bash
cd frontend
npm install                      # adds @playwright/test (+ playwright, playwright-core)
npm run e2e                      # starts Vite on :5186, runs both projects, stops Vite
npx playwright test e2e/wizard.spec.ts            # one file
npx playwright test --project=desktop-1440        # one project
```

- **Browser:** the system **Microsoft Edge** (`channel: "msedge"`), so there's no browser download. On a machine without Edge, run `PW_CHANNEL= npx playwright test` after `npx playwright install chromium`.
- **Projects:**
  - `desktop-1440` runs every spec at 1440×900.
  - `min-1280-reduced-motion` runs the 7 specs tagged `@layout` at 1280×720 with `prefers-reduced-motion: reduce`.
  - The desktop guard spec uses its own 1000×600 viewport.
- **Workers:** one worker locally (the owner's machine is CPU-bound) and 2 on CI, with `fullyParallel: false`.
- **Failures:** traces and screenshots of failures go to `frontend/test-results/`, which is git-ignored.
- **Console guard:** an auto fixture fails any test that logs a console error, a console warning or an uncaught page error. The only allow-listed message is Chromium's `The AudioContext was not allowed to start…` autoplay warning. The whole suite runs clean.

### What the suite covers

| # | Path | Spec |
|---|---|---|
| 1 | First visit: title → 5 onboarding cards → World Select. A second tab skips the intro. "Skip intro" goes to the key step. "How it works" (World Select) and Esc menu → "How it works" replay the intro | `onboarding.spec.ts` |
| 2 | World Select: ←/→ from anywhere, Enter opens the hub | `worlds-and-profile.spec.ts` |
| 3 | Hub Roster/Sessions tabs, a card opens the profile, `[` `]` cycle all six profile tabs and wrap, Replay from the Sessions tab focuses ▶ | `worlds-and-profile.spec.ts` |
| 4 | Debate replay: Space play/pause, ×1/×2/×4, ←/→ step; "See the verdict" → verdict (rubric, key disagreement, Export Markdown download, Back to Hub) | `debate-replay.spec.ts` |
| 5 | 1:1 headache: the `[1]` chip opens O28 on the highlighted § 2.4 passage; Esc closes it and returns focus to the chip | `citations.spec.ts` |
| 6 | Dinner: Hana's cited line has a Sources strip, and its entry opens O28. At 1280 with Insight open, Hana, Rin and Takeshi all end left of the drawer, and the Sources strip stays in view | `citations.spec.ts` |
| 7 | Insight → Knowledge: "1/2 cited", one cited passage and one "retrieved · not used" | `citations.spec.ts` |
| 8 | Amara's Knowledge tab: cards open O28, and focus returns on Esc. Mei's failed CSV shows the reason and ↻ Retry | `profile-knowledge-theme.spec.ts` |
| 9 | Theme tab: player, liner notes, and the play/pause toggle | `profile-knowledge-theme.spec.ts` |
| 10 | Wizard: Seed → AI draft → Look → O04 cost check → Portrait → Emotions (skip) → Palette → Theme → Approve → Summon (skipped with a key) → profile | `wizard.spec.ts` |
| 11 | Live mock: mock key via Ctrl+Shift+D → Continue live → send → Send becomes Stop while streaming → reply lands | `live-and-session-tools.spec.ts` |
| 12 | Backlog (L): full log, search highlight, Export .md download (`three-day-headache.md`), Esc closes it. Readable toggles on and off | `live-and-session-tools.spec.ts` |
| 13 | `?` shortcuts sheet, then Esc (and Esc does not also open the pause menu) | `shell.spec.ts` |
| 14 | 1000×600 shows "Desktop only" with the measured size. Widening to 1280×720 clears it | `shell.spec.ts` |
| 15 | Console clean across all of the above | `fixtures.ts` (auto) |

### Notes for the backend team (acceptance reuse)

- The specs use only URLs, roles, accessible names, visible text and keys. No `data-testid` was needed, and none was added. No app code was changed.
- Two mock-only affordances need swapping when the real API lands:
  1. `setMockKey()` (Ctrl+Shift+D → "Set mock key"), used by the wizard and live specs. Replace it with entering a key in Settings → Connection.
  2. The `?speed=4` query in `open(…, { speed: 4 })`. A real backend ignores it, but the wizard spec then needs a longer timeout.
- The tests check seed content by its visible text, such as "ED triage guidelines", "1/2 cited" and "0:57", so the backend's seed must match `seed/`.
- **The brief's onboarding-skip recipe is out of date.** Prefs are stored at `localStorage["horizon.prefs.v1"]` as a flat object (`{"seenOnboarding":true}`), not at `horizon.prefs` with a `{state,version}` wrapper. `returningVisitor()` in `fixtures.ts` does it the right way.

## 2. Findings (ranked)

### QA-01 · P1 · Replay (O23 inside S07/S09/S10): the first keyboard seek is thrown away

- **Screen:** any replay, e.g. `#/w/wld_seedMeridian/s/ses_seedDebate4Day?replay=1`.
- **Repro:**
  1. Open the replay.
  2. Press Tab (focus moves from ▶ to the Seek slider).
  3. Press End.
- **Expected:** the playhead jumps to 0:57, the log fills, and "See the verdict ▸" appears.
- **Actual:** the time flashes "0:57" and then snaps back to **0:00**. Nothing is delivered. A second End works. This reproduced 6/6 in scripted runs, with and without reduced motion, and also when End came 1.5 s after load.
- **Related symptom:** ←/→ turn steps are sometimes dropped as well. In one manual script, the second → at 0:03 did nothing. Mouse clicks on the track were not affected.
- **Why it matters:** Space, ←/→ and the scrubber are the tour's headline replay controls, and a viewer who presses End sees the replay "reset".
- **Hint for devs:** the Seek `<input type=range>` has `step=100`, but the initial position is `seek(50)`, so its value (50) is not on the step grid. That is worth checking together with the runtime's first `seek()`/`rebuildTo()`.
- **Pinned by:** `debate-replay.spec.ts` › "the first seek after opening a replay sticks…" (`test.fail`). The `seekToEnd()` helper and the step spec retry around it.

### QA-02 · P1 · Backlog (O10): L does not close the backlog, and the button promises it does

- **Repro:**
  1. In any replay, press L. The Backlog opens with focus in "Search this conversation".
  2. Press L again.
- **Expected:** the Backlog closes. Its close button is labelled "Close backlog (L)".
- **Actual:** "l" is typed into the search box, and every "l" in the conversation is highlighted ("6 hits"). The overlay stays open. This follows APP-10 (single keys don't fire in text fields), but auto-focusing the search breaks the toggle that the label advertises.
- **Fix options:** don't auto-focus the search (focus the dialog or the close button instead), or let L close the backlog while the search is empty.
- **Screenshot:** `img/qa-02-backlog-l-typed-into-search.jpg`
- **Pinned by:** `live-and-session-tools.spec.ts` › "Backlog: pressing L again closes it…" (`test.fail`).

### QA-03 · P2 · Profile → Knowledge: Mei's "↻ Retry" is a dead end

- **Repro:** open `#/w/wld_seedMeridian/c/chr_seedMei?tab=knowledge` and click ↻ Retry on *Working-time pilots dataset.csv*.
- **Actual:** a toast says "Retry ready in v1.1." and nothing else happens. A demo viewer who tries the obvious recovery hits a "not implemented" message.
- **Expected:** a mock retry, e.g. indexing → indexed, or failing again with the same reason. Otherwise hide the button in the preview.

### QA-04 · P2 · Shortcuts sheet (O20) is incomplete

- **Repro:** press `?`.
- **Missing:**
  - `[` / `]` (profile tabs) and `Ctrl+.` (stop a reply). The README lists both.
  - `←/→ · Enter` on World Select.
  - `E` (export on the verdict screen).
  - `Home/End` on the replay scrubber.
- **Expected:** the sheet is the single source of truth for keys.

### QA-05 · P2 · Pause menu (O01): the "How it works" hint is truncated

- **Repro:** at 1440×900, press Esc on World Select.
- **Actual:** the row reads "HOW IT WORKS … REPLAY THE INT…". The two-line title squeezes the hint into an ellipsis on the item that first-time visitors are most likely to use.
- **Screenshot:** `img/qa-05-pause-menu-hint-truncated.jpg`

### QA-06 · P2 · Group stage at 1280×720 with Insight open: Rin's name plate is hidden

- **Repro:**
  1. Open `#/w/wld_seedSunnyHollow/s/ses_seedDinner?replay=1` at 1280×720.
  2. Seek to the end and press I.
- **Actual:** all three speakers stay clear of the drawer (the spec checks this). But Hana's card sits on top of Rin's, so Rin's plate reads "RIN MORISA…" and her TIRED tag is barely visible. Rin is the speaker the Insight drawer is describing at that moment.
- **Expected:** the active or "NEXT" speaker comes to the front, as the debate layout does ("the speaker always comes to the front", doc 03 §5).
- **Screenshot:** `img/qa-06-dinner-insight-1280.jpg`

### QA-07 · P2 · Theme tab claims "Now playing" before audio is unlocked

- **Repro:** in a fresh tab, open `#/w/wld_seedMeridian/c/chr_seedAmara?tab=theme` directly.
- **Actual:** the tab shows "● Now playing", the button is "Pause Amara's Theme" (pressed), and a "loading…" status appears. Meanwhile the header mini-player says "Enable audio" and nothing plays until the first click or key.
- **Expected:** "Play" (not pressed) until audio is unlocked, or a "Click to enable audio" hint in the player.
- This doesn't happen when the tab is reached by clicking, because the click unlocks audio.

### QA-08 · P2 · Leaving the page after music starts is slow (needs manual confirmation)

- **Observed:** in headless Edge, once audio has started (after the title key press), navigating away or reloading takes **~2.4 s** before the next page even commits. Before audio starts it takes 15 ms. Under CPU load this grew to 28 s and timed out a test, so the suite now opens a new tab for the "returning visitor" check.
- `src/` has no `beforeunload`/`pagehide` handler, which points at the AudioContext/music teardown.
- **Ask:** check with a real headed browser: start the app, press a key, then press F5.

## 3. UX suggestions (not bugs)

Ranked by how much they help a first-time visitor understand Horizon in 60 seconds.

| # | Suggestion | Expected impact | Size |
|---|---|---|---|
| U1 | **Make the first replay move on its own.** Replays open paused on an empty stage that reads "Debaters take their marks…" (`img/ux-replay-opens-on-empty-stage.jpg`). When the viewer arrives from "Watch the debate", autoplay it, or overlay a large "▶ Press Space to watch". | The viewer sees agents argue within 2 s instead of hunting for ▶. | small |
| U2 | **Put "Watch a 60-second AI debate ▸" on World Select (and optionally on the title)** as a direct link to the featured replay. Today it takes 3 clicks: world → hub → Watch the debate. | The viewer reaches the strongest feature in one click. | small |
| U3 | **Retire the "PLACEHOLDER · NEUTRAL" sticker on every portrait** for the demo build: hide it, or show one discreet "art placeholder" note per screen. It appears on every card, the stage and the profile. | Screenshots and video read as finished, not WIP. | small |
| U4 | **Let demo visitors talk to a character.** Every hub card shows "(needs API key) Chat", and the mock key is hidden behind Ctrl+Shift+D. Add "Try with a demo key (mock replies)" to the O05 Key-required modal and to the DEMO tape. | Turns a viewer into a user, so they see streaming, emotions and citations live. | medium |
| U5 | **"Skip intro" should skip to the worlds in demo mode.** It lands on the key form, which is one more decision. Keep the key step for "Next ▸" only. | Fewer steps before the first wow. | small |
| U6 | **Pulse the Insight button once on the first replay** (or open the drawer on the featured debate). Insight (routing, recall, cost, citations) is the differentiator, but it's a small header button. | Viewers discover the "how it thinks" layer. | small |
| U7 | **Hint the citations once.** On the first cited reply, show "Tap [1] to see the exact source passage". The chips are small. | Makes "grounded answers" visible, which is a key credibility point. | small |
| U8 | **Show the replay keys on the transport for the first few seconds** ("Space play · ←/→ step · I insight"). Today they are only in `?` and the README. | Keyboard-first design becomes discoverable. | small |

## 4. Accessibility quick pass

- **Keyboard-only main flows: pass, with QA-01 and QA-02.**
  - These paths work without a mouse, and the suite drives them with keys: title → onboarding → World Select (←/→/Enter) → hub → profile (`[` `]`) → replay (Space, ←/→, End) → verdict, plus Esc menu, `?`, `I`, `L` and O28 Esc.
  - Not walked keyboard-only: the wizard (the suite clicks through it).
- **Focus management: good.**
  - The Paused menu, the Shortcuts sheet and O28 take focus on open, and Tab stays inside the dialog (8 Tabs cycled within Paused).
  - O28 returns focus to the chip or card that opened it (asserted).
  - Replays put focus on ▶ (asserted).
- **Focus visibility: good.** Custom frames replace the outline: a white frame on hub buttons and an inverted ink block in the pause menu. Both were clearly visible in screenshots.
- **Names and roles: strong.**
  - Every control the suite needed had an accessible name, so no `data-testid` or `aria-label` was added.
  - Good examples: portrait buttons ("Amara Okafor, neutral"), energy `meter`s, the Seek slider with `aria-valuetext` ("0:16 of 0:16"), citation chips ("Source 1: ED triage guidelines, § 2.4. Open source"), and "Retrieved, not used: …" in Insight.
  - Minor: the log's `listitem`s contain nested `list`s (Sources, Reactions), so screen-reader item counts include them.
- **Reduced motion: pass for the covered paths.** `data-motion="reduced"` is applied, and the 7 `@layout` specs (onboarding, verdict, dinner + Insight, Backlog, Theme, wizard + Summon) pass at 1280×720 with `reducedMotion: "reduce"`. I did not visually audit every animation (VFX, cut-ins) under reduced motion.

## 5. Out of scope / not tested

- **Screens and flows:**
  - Watch mode (S12) and Session Setup (S08).
  - Settings (S14) and Create World (O02).
  - Energy top-up (O27, F5b).
  - The failure scenarios in O18 (F6: rate limit, stream cut, budget reached, image/song failures).
  - Edit or archive a character.
- **Wizard:** regenerate, tweak, emotion generation and theme compose. The suite skips emotions and the theme song.
- **Audio and playback:** audio output and the mini-player. The suite asserts the theme toggle state, not sound.
- **Downloads:** the Markdown export is asserted by filename only, not by content.
- **Browsers and devices:** Firefox and Safari, mobile, touch, and zoom.
- **Non-functional:** visual regression, performance budgets, and bundle size (`npm run budget`).
- **Accessibility:** no screen-reader runs (NVDA/VoiceOver) and no automated axe scan.

## 5. Resolution (UI/UX adapt round, 2026-10-03)

| ID | Status | Fix |
|---|---|---|
| QA-01 | Fixed | React's range `onChange` also fires on the native `change`, which re-seeked to the stale controlled value (a backward `rebuildTo`). The scrubber now writes the seek through to its state at once and drives the keyboard itself: ←/→ by turn, Home/End to the true ends, PgUp/PgDn ±10 s, and `step=1` so dragging reaches the end. Spec un-pinned; `seekToEnd()` presses once. |
| QA-02 | Fixed | The Backlog focuses its panel on open, not the search, so L closes it; `/` jumps to the search (placeholder hint added). Spec un-pinned and extended. |
| QA-03 | Backlog | Retry stays a v1.1 toast (no contract method yet). |
| QA-04 | Fixed | The sheet adds a Browsing group (World Select ←/→ · Enter, profile `[`/`]`, intro ←/→), replay ←/→ and Home/End, `Ctrl+.`, the verdict's E and the Setup `Ctrl+Enter`. Alternatives render as "← / →". Two columns, keys aligned per group. |
| QA-05 | Fixed | Pause-menu items are wider, and labels never wrap. |
| QA-06 | Fixed | When nobody is speaking, the next (or last) speaker's seat comes forward. |
| QA-07 | Fixed | The Theme tab says "Now playing" only once audio is unlocked; before that Play turns audio on ("Press Play to turn audio on"). |
| QA-08 | Backlog | Needs a headed-browser check; not reproduced in a real window. |
| U1 | Done | Replays open with a large "▶ Watch · Space" call to action over the stage (hidden once playing, past 0:00, or deep-linked). New spec. |
| U2 | Done | World Select's header has "▶ Watch a 60-second AI debate", one click to the featured replay. New spec. |
| U3 | Done (D-60) | The PLACEHOLDER tape shows only on the profile hero portrait; stages and cards are clean. |

Suite after the round: **32 passed** (`npm run e2e`, 2.1 min).
