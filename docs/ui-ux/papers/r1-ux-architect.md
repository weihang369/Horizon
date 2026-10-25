# R1 — UX Architect position paper

## 1. Top 5 decisions

**D1. Routes are places, overlays are a single `LayerStack`.** *Why:* otherwise 41 surfaces grow 41 Esc/focus behaviours. *What:* hash router (reload-safe deep links for review); every overlay registers in one zustand `LayerStack` (`{id, kind, onEscape, trapFocus, returnFocusTo}`):

| Kind | Members | Focus | Esc |
|---|---|---|---|
| Modal | O02–O05, O13, O21, O26, O27, O06, O25, O20 | trapped, restored | close (destructive O03: cancel) |
| Drawer | O08 Insight, O10 Backlog, O09 popover | not trapped | close |
| Ceremony | O15, O16, O17-entry, Shatter, Verdict reveal | none | **skip to end state** |
| Ambient | O14, O22, O23 badge, ×N badge, O19 | never takes focus | ignored |

**D2. One `SessionScreen`, four layouts, one swappable Dock.** S07/S09/S10/S12 share one route (`/w/:wid/s/:sid`, mode from data) and one grid: `TopBar 56px / Stage+Log / Dock`. Only the Dock varies: `Composer` (1:1, group), `SteeringBar` (debate), `Transport` (watch), `ReplayTransport` (any mode in replay), `DemoDock` (seed resumed, no key). Replay, demo and "Continue live" are *dock swaps on one screen*.

**D3. All secondary input expands from the Dock, never a modal.** O12 (Ask…, Interject, Director's note, Step in) is a `DockExpansion`: slides up 120px over the log, 240ms `cubic-bezier(0.2,0.9,0.3,1.3)`, keeps its draft. Eyes and hands stay in the bottom 20%.

**D4. Ceremonies queue input, never block it (APP-03 AC2).** Summon (1.8s), VS splash, Verdict reveal and Shatter run on `useCeremony()`: any key/click jumps to the end state; the pressed key is replayed after settle. Reduced motion = one ≤200ms fade.

**D5. Hero-slice-first build: Replay of the seed debate is the first thing the stakeholder sees.** It exercises title→hub→stage→reactions→banners→Insight→verdict with zero composer logic, and is the LinkedIn clip.

## 2. Remit

### 2.1 Information architecture

| Route | Screen |
|---|---|
| `/` | S01 Title |
| `/onboarding/:card` | S02 |
| `/worlds` | S03 |
| `/w/:wid?tab=roster\|sessions&filter=` | S04 **+ S13** (History *is* the Sessions tab, HIST-01 AC1; pause-menu "History" deep-links to it) |
| `/w/:wid/c/:cid?tab=` | S06 |
| `/w/:wid/create/:step`, `/w/:wid/c/:cid/edit/:step` | S05 (steps addressable for review) |
| `/w/:wid/setup/:step` | S08 |
| `/w/:wid/s/:sid?replay=1&t=<seq>` | S07/S09/S10/S12 (+O23 when `replay=1`) |
| `/w/:wid/s/:sid/verdict` | S11 |
| `/settings/:tab` | S14 (world context kept as `?from=`) |

**Back (◂, browser Back, Alt+←):** in-app history clamped to the world; never re-enters a ceremony or finished wizard; empty history → logical parent (hub). Leaving a live session pauses it (MULTI-13) with toast "Paused · *{title}*".

**Esc precedence:** (1) popover/picker (O11, O24, O09) → (2) DockExpansion (collapses, draft kept) → (3) Modal → (4) Drawer (top-most opened last) → (5) focused text field: **blur only** → (6) O01 Pause (Esc again resumes). O19 undismissable.

### 2.2 Compositions (W×H in px; gutter 32 @1440, 24 @1280; DEMO tape adds 28px on top and shrinks Stage, never Dock)

**S03 World Select.** Ransom "WORLDS" 72px at (48,48). Centred rail: cards 380×520 @1440 / 300×410 @1280, −8°, 40px overlap, "+ New World" last. Focus straightens to −4°, lifts −12px, 180ms.

**S04 Hub.** Cover header 240 / 168, world name ransom 64 / 48, You-card chip, ⋯. Tab row 48 with CTAs right ("+ New Character", primary "Start Session ▸"). Roster: 5 / 4 columns of 3:4 cards 236×315 + 72px plate (name, role, energy bar 6px). Demo: "FEATURED RECORDING ▶" strip (96px) heads Sessions; "▶ Watch the debate" CTA in the cover.

**S07 1:1.** TopBar 56. Stage column 600 / 520, Log column 840 / 760 with an 8° left cut (~120px overlap onto stage). Portrait card 520×693 / 420×560 anchored bottom-left at x=40, bleeding 40px below viewport. Name plate y=96 over the card's right edge, energy bar 10px under. MANUAL: vertical strip of 7×44px buttons on the seam. Composer **inside** the log column, 88 / 76. Messages ≤680 wide; Readable 640 (68ch).
*Insight open (push):* Stage 440 / 360 (card translates −80 behind the cut; eyes at 30–35% stay visible), Log 600 / 520, Drawer 400.

**S09 Group.** The reference row-under-log leaves a 300px log at 1280×720. → **Wings**: Log column centred 640 / 560, full height between TopBar+NEXT strip (40) and Dock (96 / 84). Cast split into left/right wings (400 / 360 wide), bottom-anchored portraits 380 / 274 tall (≥ 38% vh), overlapping ≤ 45%; 5th seat stacks behind at 0.8. Speaker: scale 1.08, translateX 24 toward centre. *Insight (overlay):* right-wing portraits FLIP into the left wing at 0.8.

**S10 Debate.** TopBar 56, motion banner tape 64 (−3°, ransom), timeline rail 36 under it. Columns Prop 340 / 300 · Log 760 / 680 · Opp 340 / 300. Per column: front slot 280×373 / 240×320, second debater behind (offset 56 outward, −40 up, 0.88), third at 0.8. Speaker comes to front + translateX 40 toward centre. Auto host: no portrait, "HOST" tape centred under banner. SteeringBar 72. *Insight (overlay):* covers Opp; drawer header shows the selected speaker's 72px head-crop + emotion.

**S11 Verdict.** Full-bleed. Banner "STRONGER CASE: PROPOSITION" 96 / 72 at y=96. Left 360 / 300: winning side's portraits. Centre 720 / 640: rubric bars (row 28, bar 12, two sides interleaved), summaries in 2 columns, Key disagreement tape, rationale. Actions dock 88: Export · Rematch · Back to Hub · **Continue as group chat** (primary). Reveal: 0 sting → 0–700 Banner Slam → 900 bars fill (600ms each, 80ms stagger) → 1900 summary → 2400 actions. *You decide:* summary first, then two 480×120 skewed side buttons; pick triggers the reveal.

**S12 Watch.** Theatre, distinct from Group: proscenium **row** of portraits, bottom-anchored, 46% vh. Script log above: 760 / 680 "subtitle" column, last ~8 lines, top fade mask; full log via `L`. Transport 72: ❚❚/▶ · Step → · Pace [Slow|Normal|Fast] · ■ | Step in · 🎬 Note | episode rail "TURN 6 / 10" with ticks.

**S05 Wizard.** Step rail 64 (8 skewed chips, progress pips for background jobs). Spec card column 440 / 360 (portrait 360×480 / 300×400, palette frame). Work area remainder. Action bar 80: ◂ Back · "≈ $0.04" estimate · Next / Generate ▸ (right). Approve step = summary card centred 880 wide.

### 2.3 Interaction details

**Composer.** `<textarea>` + mirrored highlight layer (no contenteditable). Grows 1→6 lines (max 160) upward over the log; counter from 3,500. Send = 120×48 parallelogram (−12°) morphing in place to a 48×48 Stop square while streaming. Draft persists per session in the store (survives errors, nav, Esc).

**@mentions (O11).** Picker above the caret, ≤5 rows: head-crop, name, state ("asleep · ⚡0 · Top up", "Muted"). ↑↓/Tab/Enter; Esc closes picker only. Mentions are atomic chips in that character's `primary`; Backspace removes the chip. Group dock row: `[Responders ▾]  [composer]  [SEND]`, with "Everyone answer" and "Next ▸" as 28px chips above the right end. "Mentioned only" hint sits inline above the composer.

**Portrait menu (O24).** Click, right-click, Enter, Shift+F10 or ContextMenu key on a focused portrait. Skewed 200px menu anchored to the name plate. Stage portraits use roving tabindex (←/→). S07 portrait has no click action.

**SteeringBar.** `❚❚ · Next · Ask… · Interject · Extend · Skip to closing · End` | auto-advance toggle. Opening Ask…/Interject **holds the queue at the next boundary** (NEXT chip: "HELD"); send/cancel releases. Ask…: debater chips, then field.

**ReplayTransport (O23).** ❚❚/▶ · scrubber with event markers (round, emotion change, steer, director's note) · ×1/×2/×4 · "● REPLAY" tape top-left of the stage · **Continue live ▸** at the right. Seek re-reduces events to `seq` instantly, ceremonies suppressed. Energy drains replay as recorded.

**Demo coherence.** One story: *recordings play; live actions ask for a key.* Blocked controls look enabled with a small key glyph and open O05 (a wall of disabled buttons kills demos). Resumed seed = `DemoDock`: "Recorded · ▶ Replay · Continue live (needs key)". With a key, Continue live forks (`continuedFrom`) → Slash Wipe → toast "Live copy of *{title}*".

### 2.4 Keyboard and focus
F6 cycles landmarks TopBar→Stage→Log→Dock→Drawer. Live sessions open with focus in the composer, replays on ▶. Log is `role="log"`, announcing **completed** messages only. With Insight open, ↑↓ in the log moves selection. Focus ring: 2px `glow`, 3px offset, follows skew. Single-key shortcuts gated by `isTypingTarget()`. Proposed: `Ctrl+.` = Stop.

### 2.5 States placement

| Class | Where |
|---|---|
| Page empty | Centred in the content region (below TopBar/tabs), silhouette + tape, 1 CTA |
| Page loading | Skewed skeletons at **final geometry** (no layout shift); stage portraits render from preload immediately |
| Turn loading | In-log "…" row + lean-in; NEXT chip pulse |
| Chat errors | Inline log row, full log width, red WARNING tape + one action |
| Generation errors | Per slot (FAILED slash) |
| Background/job | Toast + rail/status pill |
| Session paused (`pausedReason`) | 32px tape under TopBar; Dock shows Resume |
| Blocking | Modal only for key, budget, destructive, one-stream conflict |

Top order fixed: DEMO tape → TopBar → paused tape; toasts right, under the mini-player.

### 2.6 Build order and stakeholder milestones
- **M1 "Showreel" (debate replay):** S01 → S03 → S04 → S10 Replay + O16 + O08 + O23 → S11.
- **M2 "Talk":** S07 live (stream, emotions, MANUAL, Stop, errors) + S06 + energy/O27.
- **M3 "Create":** S05 all steps (both emotion variants) + O15 Summon.
- **M4 "Ensemble & states":** S09, S12, S08, S14, S02, O18 full scenario list, Presenter Mode.

### 2.7 Four builders, minimal overlap
Day 0 (½ day): freeze `HorizonClient` types, `LayerStack`, `Dock` slot API, `PortraitCard` props, `useCeremony` as stubs. Features self-register via `features/*/register.ts` (routes, overlays, shortcuts, O18 scenarios) collected by `import.meta.glob`, so nobody edits shared registries.

| Builder | Owns (dirs) | Scope |
|---|---|---|
| B1 Platform | `app/`, `client/`, `state/`, `audio/`, `seed/` | router, LayerStack, keyboard/focus, MockClient + replay engine + timings, zod fixtures, WebAudio synth, O01/O03/O04/O05/O14/O18–O22, S14 |
| B2 Character & World | `kit/character/`, `features/world/`, `features/profile/`, `features/title/` | PortraitCard, emotion crossfade/VFX, NamePlate, EnergyBar, placeholders; S01, S02, S03, S04(+S13), S06, O02, O06, O25, O27 |
| B3 Session runtime | `features/session/` | SessionScreen, 4 layouts, Log, all Docks, mentions, O08, O10–O12, O17, O23, O24, O26 |
| B4 Creation & Ceremony | `kit/motion/`, `features/wizard/`, `features/setup/`, `features/verdict/` | Slash Wipe, Shatter, Banner Slam, Palette Flood, `useCeremony`; S05, O13, O15, S08, O16, S11 |

Only shared file: `kit/tokens.css` (Visual Director's, merged via B1).

## 3. Risks, ambiguities, resolutions
1. **S09 row layout starves the log at 1280×720.** → Wings (§2.2). The reference layout is not an AC, and MULTI-02's size and step-forward rules are kept.
2. **400px push in S07 at 1280 leaves a 360px log.** → Compress the stage, not the log (minimum log width 520).
3. **Insight in S10 hides the Opp speaker.** → Head-crop in the drawer header. In S09, FLIP the right wing left.
4. **APP-03 "≤600ms block" vs the 1.8s Summon and the VS splash.** → Skippable ceremonies with queued input (D4).
5. **Esc inside a text field is unspecified.** → Blur first, pause menu on the second Esc.
6. **O12 named as an overlay, interaction unspecified.** → DockExpansion; steering holds the queue at the boundary.
7. **Replay seek semantics are undefined.** → Event-reducer seek, ceremonies suppressed during the seek.
8. **One-stream rule vs Replay.** → Replay is local playback and never counts as streaming (NFR-31 doesn't apply).
9. **The "Pause *{title}* and continue?" prompt has no overlay ID.** → Reuse O03's simple-confirm style.

**BA loop-back (optional, small):** "Continue live" from the *playhead* ("take over from here") is the most demo-worthy variant, but `forkSeedSession(sessionId)` has no `atSeq`. MVP forks the whole recording; adding `atSeq?` changes doc 05.

## 4. Wow vs unsatisfied
**Wow (first 30s):** a key press on the kinetic title → world cards rail in → Shatter into Meridian → "▶ Watch the debate" → VS slam → Amara steps forward while Mei's face flips to *thinking*, and the Insight drawer's probability bars fill `0.71 · HIGH` as she speaks. Then the user hops to Sunny Hollow and the whole UI floods Sakura pink. Every boundary is punctuated, and the steady state stays calm.

**Unsatisfied:** grey-box portraits; a "dark SaaS dashboard" hub/settings; inconsistent Esc; jank or unskippable ceremonies; a cramped log at 1280×720; demo mode as a wall of disabled buttons.
