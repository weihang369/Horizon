# 02: Functional Requirements

**Format:** *As a [persona], I want…, so that…*, followed by acceptance criteria (AC).
**Priority** is MoSCoW **for the UI/UX (hardcoded) phase**. In that phase, every AI behaviour is **simulated** by the `MockClient` with realistic timing (APP-07). Field and event names refer to [05-data-contract.md](05-data-contract.md).

---

## Epic APP: Shell, navigation & mock tooling

**APP-01: Title screen** · Must
As any user, I want a stylised title screen, so the app feels like a game from the first second and the browser unlocks audio.
- AC1: On load, "HORIZON" animates in (≤ 1.5 s), then "Press any key" pulses.
- AC2: Any key or click → Slash Wipe to **Onboarding on first run, otherwise World Select**, and the audio context is unlocked (MUS-06).
- AC3: With reduced motion, the title fades in (≤ 300 ms).

**APP-02: Pause menu (global navigation)** · Must
- AC1: `Esc` (outside text fields and modals) or the corner button opens the menu: Resume · Worlds · Current World Hub · History · Settings · Title.
- AC2: It shows the current world and the active character (if any).
- AC3: `Esc` again or Resume closes it and restores focus.

**APP-03: Stylised transitions** · Must
- AC1: Every route change uses a transition from doc 04 §5, lasting 350–600 ms.
- AC2: Input is never blocked for more than 600 ms. A second navigation cancels the first transition.

**APP-04: First-run onboarding** · Should
- AC1: 4 cards (Worlds · Characters · Sessions · Energy) shown once, with Skip.
- AC2: A key step offering "Enter key" or "Explore demo first".
- AC2b: Card copy is in doc 06 §8. The Energy card reads: "Characters spend ⚡ when they talk and recharge over a day."
- AC3: Can be replayed from Settings → About.

**APP-05: Reduced motion** · Must
- AC1: Defaults to the OS `prefers-reduced-motion`. When on, it disables skew animation, shake, parallax, particles and flashes; transitions become fades of ≤ 200 ms; emotion changes still crossfade.

**APP-06: Desktop guard** · Must
- AC1: When the viewport is below **1280×720**, a stylised notice reads "Horizon is designed for desktop (≥ 1280×720)". No mobile layout is built.

**APP-07: Simulated AI behaviour (UI phase)** · Must
As the stakeholder, I want mock AI to stream and load with **realistic** timings, so I approve how the real product will feel.
- AC1: The default timings live in one config file:
  - first token 1.5 s, ~40 tokens/s;
  - profile draft 4 s;
  - base portrait 20 s per candidate (2 in parallel);
  - each emotion 15 s (2 in parallel), or an expression sheet 30 s;
  - theme song 40 s;
  - listener reactions arrive 300–800 ms after `turn.end`.
- AC2: A **Demo speed** multiplier (×1 / ×2 / ×4) speeds everything up for reviews. While it's above ×1, a "×N" badge is visible.

**APP-08: Mock State Switcher (dev overlay)** · Must
As the stakeholder, I want to force any empty, loading or error state, so I can approve those states without waiting for them.
- AC1: `Ctrl+Shift+D` opens a panel of scenarios: No key (demo mode) · Invalid key · Rate limited · Out of credits · Network down · Content refused · Daily cap reached · Character exhausted · Rush hour · Image generation fails (all / partial) · Song fails · Stream cut mid-reply · Empty world · No worlds · Slow stream · Reactions late or missing · Emotion arrives late.
- AC2: A selected scenario applies to the current screen immediately. Reset restores the default.
- AC3: The switcher is a control panel **for the MockClient** (it selects fixture or failure scripts). It is hidden in Presenter Mode.

**APP-09: Demo mode (no API key)** · Must
As Alex, I want to explore everything without pasting a paid key, so I can decide if the repo is worth my time.
- AC1: Without a key, a slim tape at the top reads "DEMO MODE · Browsing seed data · Add your OpenRouter key to chat & create".
- AC2: Seed worlds, characters, portraits, songs and **pre-recorded sessions** are all browsable. Recorded sessions can be **replayed** (MULTI-15) with emotions, banners and Insight data.
- AC3: Any AI action opens the key-required modal (STATE-04).
- AC4: What demo mode allows:

  | Allowed without a key | Blocked (opens STATE-04) |
  |---|---|
  | Browse worlds, characters and galleries; Replay any session; open the Insight drawer on replayed messages; edit text fields; rename/archive; Settings; "Surprise me" (local list) | Send a message; any generation; start a new session; Auto-assign sides; Suggest motions; Test connection without a key |

- AC5: A resumed seed session shows a **disabled composer** with the DEMO-tape call to action.
- AC6: **Seed sessions stay replay-only, even after a key is added** (D-47). A **"Continue live"** button forks a new live session (`continuedFrom`), so "Reset demo data" always restores the recordings as shipped.

**APP-10: Keyboard rules** · Must
- AC1: **Single-key shortcuts** (`I`, `L`, `?`, `Space`, `→`) fire **only when focus is not in a text field**.
- AC2: Shortcuts that must work while typing use a modifier: `Alt+1…7` (set face in MANUAL), `Esc`.
- AC3: In the composer, **Enter = send**, **Shift+Enter = new line**, and `Ctrl+Enter` = send (alias).
- AC4: The full list is in doc 03 §6 and the `?` sheet.

---

## Epic WLD: Worlds

**WLD-01: World Select** · Must
- AC1: Big tilted cards, each showing cover, name, character count, up to 5 character head-crops and last-active date.
- AC2: Hovering tilts and lifts the card with a hover SFX. Clicking runs the Shatter transition into the World Hub.
- AC3: A "+ New World" card is always last.

**WLD-02: Create world** · Must
- AC1: A modal with Name (required, 1–40 chars, unique) and Cover: 1 of 8 preset abstract covers, or upload an image.
- AC1b: An optional **"You in this world"** card (D-43): display name (≤ 30) and one line about you (≤ 160), e.g. "Hana's boyfriend, works in IT". Characters in this world use it; other worlds never see it. In the log, the user's label is this name (otherwise "You").
- AC2: The user lands in the new hub's empty state (STATE-01).
- AC3: There are no lore, rules or setting fields.

**WLD-03: Edit world** · Should. Rename and change the cover from the hub's "⋯" menu.

**WLD-04: Delete world** · Must
- AC1: The confirmation shows how many characters and sessions will be deleted and requires typing the world name.
- AC2: The user returns to World Select with a toast.

**WLD-05: World Hub** · Must
- AC1: Tabs: **Roster** and **Sessions**.
- AC2: CTAs: "+ New Character" and "Start Session ▸".
- AC3: Each character card shows: neutral portrait with idle breathing, name, role, palette stripe, tagline and **energy bar** (ENG-01). Clicking opens the profile; a quick "Chat" button opens 1:1.
- AC4: Archived characters are hidden behind an "Archived" filter.

**WLD-06: World isolation** · Must
- AC1: No screen lists, links to or offers characters or sessions from another world. Cast pickers, history and search are all world-scoped.
- AC2: Switching world always goes through World Select or the pause menu.

**WLD-07: AI-generated world cover** · Could *(full product, opt-in, cost shown)*

---

## Epic CHR: Character Creation Wizard (seed → AI draft → human edit → approve)

A full-screen flow with a skewed step rail: `SEED → PROFILE → LOOK → PORTRAIT → EMOTIONS → PALETTE → THEME → APPROVE`. Completed steps can be revisited. The wizard saves progress to `Character.creationStep`.

**Provisional palette:** the AI draft (CHR-03) also returns an **"AI pick" palette**, which is set as a provisional `paletteId` straight away. The LOOK, PORTRAIT and EMOTIONS steps are framed in it, and the PALETTE step confirms or changes it.

**Step gates:**

| From → To | Gate |
|---|---|
| SEED → PROFILE | Draft returned, or "Write it myself" |
| PROFILE → LOOK | Required profile fields valid |
| LOOK → PORTRAIT | Always |
| PORTRAIT → EMOTIONS | Base portrait locked |
| EMOTIONS → PALETTE | Emotion job started or "Skip for now". The job continues in the background, shown as a progress pip on the step rail |
| PALETTE → THEME | A palette is set (the AI pick is pre-set) |
| THEME → APPROVE | Always. Song composing continues in the background |
| **Approve enabled** | Profile valid + base portrait locked. Running jobs continue after approval |

**CHR-01: Start wizard** · Must
- AC1: Started from "+ New Character" in the hub or from the empty state. The character belongs to the current world.
- AC2: Leaving mid-wizard prompts "Save as draft / Discard / Cancel".

**CHR-02: Seed input** · Must
As Jun, I want to type one line like "Sarah, a doctor", so the AI does the heavy lifting.
- AC1: One large field (≤ 300 chars) with cycling example placeholders.
- AC2: An optional **Intent** chip: `Expert / Advisor` · `Companion / Life-sim` · `Other` (stored as `intent`).
- AC3: A "Surprise me" button fills in a random seed.
- AC4: "Draft with AI ▸" is disabled while the field is empty.

**CHR-03: AI drafting state** · Must
- AC1: The Profile step opens with a scanning-stripe shimmer. When the draft arrives, fields **reveal one by one** (a client-side stagger of 60–120 ms per field; the backend need not stream fields).
- AC2: Cancel stops the draft. Fields that already arrived are kept; the rest stay blank (the same as "Write it myself").
- AC3: If drafting fails, show an inline error with "Retry" and "Write it myself".

**CHR-04: Edit profile (= system prompt)** · Must
- Fields: Name\*, Title, Role\*, **Age\* (integer ≥ 18)**, Pronouns, Tagline (≤ 80), Personality summary + traits (3–8 chips), Backstory, Speaking style (summary + tone + formality + quirks + catchphrases), Expertise (chips), Goals, Boundaries (list), Greeting, Example lines (0–3, optional), Relationship to user (free text, e.g. "your girlfriend"; **not** a link to another character), Advisory flag (auto-set for professional roles, editable).
- AC1: Required fields validate inline. "Next" is disabled until valid. **An age below 18 is rejected**, with the copy "Horizon characters are adults."
- AC2: Each field has a ↻ "Regenerate this field" control that only changes that field.
- AC3: Edited fields show an "edited" dot, and regenerating an edited field asks for confirmation.

**CHR-05: Prompt preview** · Should
- AC1: The "View as prompt" toggle shows a read-only monospace `systemPromptPreview` with a token count. *(The template is the AI team's; it's a mock in the UI phase.)*

**CHR-06: Create-a-Character appearance ("LOOK")** · Must
As Jun, I want Sims-style pickers for appearance, so I can shape the look without writing prompts.
- Layout:
  - Left: a **Spec card** showing the current base portrait, or a stylised silhouette before the first generation, framed in the provisional (AI pick) palette.
  - Right: category tabs with chip and swatch pickers:
    - **Body:** age band (young adult / adult / middle-aged / senior; **no minor option**), build, height, skin tone (12 swatches).
    - **Face:** shape, baseline expression, marks.
    - **Eyes:** shape, colour (12), glasses.
    - **Hair:** length, style (12), colour (16) + streak, fringe.
    - **Outfit:** archetype + 2 colours.
    - **Accessories:** ≤ 3.
    - **Vibe:** ≤ 2.
  - Bottom: an "Extra details" free-text field.
- AC1: The AI draft **pre-selects** every chip from the seed and profile.
- AC2: Selections compile into an editable **Appearance summary** sentence.
- AC3: **No sliders and no live morphing.** A badge reads "Changes apply on Generate". Only the outfit-colour swatches and the palette frame preview instantly, because they're CSS.

**CHR-07: Portrait candidates → pick → refine** · Must
- AC1: "Generate portrait ▸" shows the cost estimate (CHR-13), then generates **1 candidate in Lean mode (default)** or 2 in Standard mode with a halftone "developing" animation and the steps `QUEUED → PAINTING → FINISHING` plus elapsed time.
- AC2: The user picks one with "Lock as base", regenerates, or **refines by text** (a "Tweak" field such as "shorter hair", which runs a reference edit with its cost shown).
- AC3: The locked base shows 🔒, and EMOTIONS unlocks.
- AC4: A failure is shown per candidate with Retry; the other candidate stays usable.

**CHR-08: Emotion set generation & review** · Must
- AC1: A 7-slot grid (neutral, happy, sad, angry, surprised, thinking, embarrassed). Neutral = the locked base.
- AC2: "Generate emotions ▸" (with cost estimate) runs in one of two reveal variants, and **UI/UX designs both**. The Seed Asset Sprint picks one:
  - **Variant B (per-emotion edit):** slots fill one by one.
  - **Variant C (expression sheet):** a contact sheet develops, then a *slice* animation cuts it into the slots.
- AC3: **Lean mode (default, D-40)** generates happy, sad and angry now. The other 3 slots show "Generate (≈ $0.04)" and can be generated later on demand. **Standard mode** generates all 6 non-neutral emotions now.
- AC4: Clicking a slot opens a lightbox with ↻ Regenerate (cost shown) and **"Doesn't look like them"**, which marks the asset `rejected` and regenerates with a consistency hint.
- AC5: Failed slots show a red "FAILED · Retry" slash. The user can still proceed, and missing emotions fall back to neutral + VFX (EMO-06).
- AC6: "Skip for now" saves the character with neutral only.
- AC7: An optional **blink frame** for neutral is generated with the set (Should). If it's missing or fails the alignment check, there is no blink.

**CHR-09: Palette selection** · Must
- AC1: The AI suggests one palette ("AI pick") from the **fixed 12** (doc 04 §3). All 12 are shown as skewed swatch cards.
- AC2: Hovering live-previews the palette on the wizard chrome with an **instant, 120 ms-debounced colour swap (no flood)**. **Clicking** selects it and plays the Palette Flood once (photosensitivity, NFR-16).
- AC3: No custom palettes. Sharing a palette within a world shows a soft warning.

**CHR-10: Theme song** · Must. *Each character has exactly **one** theme song (D-44).*
- AC1: The AI drafts a **song brief**, all editable: genre chips, mood chips, BPM slider 60–160, instrument chips, a "vibe" line.
- AC2: "Compose ▸" (cost shown) runs **in the background**. The user can continue to APPROVE while a progress pill shows status.
- AC3: When done, a player shows the waveform, ▶/❚❚ and loop preview. "Regenerate" (cost shown) **replaces** the song. There is no song history.
- AC4: On failure: "Retry" or "Approve without song" (the character then uses the ambient fallback, MUS-07).
- AC5: Small print shows the model used and `licenseNote`.

**CHR-11: Review & approve ("Summon")** · Must
- AC1: A summary card shows portrait, name plate, role, tagline, palette, emotion thumbnails, song player, and warnings (missing emotions or song).
- AC2: "Approve & Summon" plays the **Summon reveal** (≈ 1.8 s: palette flood → slash → portrait slide-in → name slam → theme starts) and lands on the profile.
- AC2b: If the song is still composing, the reveal plays the ambient bed. When the song is ready, a toast shows "{name}'s theme is ready ▶", and the theme plays from the next visit.
- AC3: Enabled only when the profile is valid and a locked base portrait exists.

**CHR-12: Drafts** · Should
- AC1: Unfinished characters appear in the roster with a "DRAFT" tape and reopen at `creationStep`.
- AC2: Drafts can't join sessions.

**CHR-13: Cost estimate & confirm before generation** · Must
- AC1: Every image or song Generate/Regenerate button shows "≈ $X.XX". A confirm dialog appears the first time per **app launch** (this can be disabled). Cancelling a running image job shows: "Images already in progress may still be charged."
- AC2: The values come from a config table (mock values in the UI phase).
- AC3: If an action would exceed the creation cap (before approval) or the daily cap (after), it is blocked with STATE-06.

**CHR-14: Quick create** · Could. Seed → "Do everything" with AI picks, stopping at APPROVE.

---

## Epic PRF: Character Profile & Gallery

**PRF-01: Profile screen** · Must
- AC1: The large animated portrait card sits on the left (framed, opaque: doc 04 §4), with the energy panel under it. Tabs: Profile · Gallery · Theme · Sessions · Memory · Knowledge.
- AC2: Themed in the character's palette; the theme song starts (crossfading per MUS-02).
- AC3: CTAs: "Chat ▸", "Add to session ▸".

**PRF-02: Emotion gallery** · Must
- AC1: A grid of 7 emotions. Hovering previews that emotion on the main portrait with its VFX.
- AC2: The lightbox has arrow-key navigation, Regenerate (cost) and Download.

**PRF-03: Edit character** · Must
- AC1: "Edit" reopens the wizard steps with current values.
- AC2: Changing appearance never silently regenerates. The user sees "Appearance changed: regenerate portraits? (≈ $x)".
- AC3: Profile edits show the note "Changes apply to new messages".
- AC4: Editing ends with **"Save changes"** (no Summon reveal).
- AC5: A regenerated asset on an approved character opens an **Old | New** comparison lightbox with **Use new** / **Keep old**. The old version stays active until the user chooses.

**PRF-04: Theme tab** · Must. Player, song brief, "Regenerate (replaces)" with cost, model and licence note.

**PRF-05: Sessions tab** · Must. Lists sessions that include this character; clicking resumes one.

**PRF-06: Archive / delete character** · Must
- AC1: The default action is **Archive**: the character is hidden from the roster and cast pickers, and history stays intact.
- AC2: The Archived filter offers **Restore** and **"Delete permanently"** (typed confirmation). On permanent delete, the character's **1:1 sessions are deleted** (their count is shown in the confirmation), and their messages in multi-character sessions are kept under a grey silhouette with "(deleted character)".
- AC3: Resuming a multi-character session whose cast includes an **archived** character shows that character greyed out with "Archived", and they are skipped in turn-taking. A 1:1 session with an archived character is read-only, with a "Restore to chat" button.

**PRF-07: Memory tab** · Should *(the mock carries a "Preview: final design by AI team" ribbon)*
- AC1: A list of memory items (text, kind, source session, date, importance badge) with View source and Forget.

**PRF-08: Knowledge tab** · Could *(mock; RAG is v1.1; same ribbon)*. A drop zone and a document list with status.

**PRF-09: Energy panel** · Must. The profile shows the energy bar, ⚡ spent today, "full in …", the daily max selector (500 / 1000 / 2000) and Top up (ENG-03/05).

---

## Epic CHAT: 1:1 Chat

**CHAT-01: Start / resume** · Must
- AC1: "Chat" opens the most recent 1:1 session with that character, or creates one. "New conversation" is in the header.
- AC2: A new session opens with the character's `greeting`.

**CHAT-02: Streaming replies** · Must
- AC1: My bubble appears instantly with a send SFX. The "…" typing state appears within 100 ms, and text streams token by token.
- AC2: Auto-scroll follows unless I've scrolled up, in which case a "↓ New message" pill appears.
- AC3: While streaming, Send becomes **Stop**. Stopping keeps the partial text and marks it "(stopped)" (`interruptedBy: "user"`; no further actions). A network or provider cut is shown differently: "(interrupted)" with Continue · Regenerate (STATE-03).
- AC4: Markdown is rendered (bold, italics, lists, code, links). Raw HTML is not.
- AC5: The composer is capped at **4,000 characters**, with a counter from 3,500. A longer paste is truncated with a warning toast. Enter sends, and Shift+Enter adds a new line (APP-10).

**CHAT-03: Portrait & emotion display** · Must
- AC1: The active emotion portrait is large on the left with idle animation (EMO-04).
- AC2: On change: a crossfade (starts ≤ 100 ms, completes ≤ 300 ms) plus the emotion VFX and SFX.
- AC3: Each character message stores its emotion. Hovering a message in the log shows an emotion icon.
- AC4: **Timing:** the emotion appears at stream start. The portrait holds a subtle "lean-in" for up to 800 ms waiting for it. If the emotion arrives later, it switches late. It is never blank.

**CHAT-04: Emotion mode toggle** · Must
- AC1: A header toggle **AUTO | MANUAL**, defaulting from Settings and saved per session.
- AC2: **AUTO:** the AI provides the emotion for each reply.
- AC3: **MANUAL:** an emotion picker (7 icons, hotkeys **`Alt+1`…`Alt+7`**, which work while typing) sets the portrait. The choice persists until changed. **It changes the face only; the reply text is unaffected** (stakeholder decision D-07).
- AC4: Switching modes shows a toast and never rewrites past messages.
- AC5: In MANUAL, each session starts on **neutral** (or the last face set in that session). AI emotion events are **not applied** to the portrait but are still recorded for the Insight drawer.

**CHAT-05: Theme music in chat** · Must. See MUS-01..04.

**CHAT-06: Regenerate last reply** · Should
- AC1: ↻ on the last character message. Alternatives become `‹ 1/2 ›` swipes. **Only the active variant counts** for context and memory.

**CHAT-07: Edit & resend my last message** · Could

**CHAT-08: Readable Mode** · Must
As Priya, I want long expert answers to be comfortable to read.
- AC1: Messages over 600 characters render in a straight-edged reading panel (no skew, 16 px, ≤ 68 ch line width).
- AC2: A "Readable" toggle in the header forces it for all messages.

**CHAT-09: Backlog view** · Should. A full-screen visual-novel-style log (`L` key) with in-session search.

**CHAT-10: Chat errors** · Must. Errors appear inline in the log with Retry (STATE-03). Typed input is never lost.

**CHAT-11: Copy / export** · Should. Copy a message; export the session as Markdown.

**CHAT-12: SME disclaimer** · Must. When any participant has `advisory: true`, a slim tape on the header reads "AI simulation · not professional advice".

---

## Epic MULTI: Multi-character sessions (within one world)

**MULTI-01: Session setup** · Must
- AC1: Step 1 is mode selection: three skewed cards (**GROUP CHAT · DEBATE · WATCH**), each with a 1-line description and a looping mini-preview.
- AC2: Step 2 is the cast picker (**this world only**, approved characters only): **2–4** characters, with a 5th seat under "Advanced" and a wait-time estimate.
- AC3: Step 3 is mode-specific config. "Start ▸" plays the mode intro (Group: slide-in; Debate: VS splash; Watch: curtain slash).
- AC4: If another session is currently streaming: "Pause *{title}* and continue?" (one streaming session at a time).

### Group chat
**MULTI-02: Group flow** · Must
- AC1: Replies are **sequential**: each streams, and the next starts after the previous one ends. **Each character turn is exactly one message with one emotion** (no multi-bubble replies, D-46). Exhausted characters are skipped (ENG-04).
- AC2: The speaker steps forward (scale 1.08, full saturation). Others recede (85% brightness, 30% desaturation).
- AC3: A name-plate cut-in plays on each speaker change (300 ms; can be turned off in Settings).

**MULTI-03: Who responds** · Must
- AC1: A responder policy dropdown: **Auto** (the AI chooses **up to 2**) · **Everyone** · **Mentioned only**.
- AC2: `@` opens a mention picker. A mentioned character always replies. With the **Mentioned only** policy and no @mention, an inline hint reads "Mention someone with @ to get a reply." Sending is still allowed.
- AC3: An "Everyone answer" button and a "Next speaker" button (one more character speaks without a user message).

**MULTI-04: Listener reactions** · Must
- AC1: After each message, non-speakers may change emotion, shown as a crossfade + small VFX on their portrait, with no text.
- AC2: Reactions never delay the next speaker. They may arrive late or not at all.
- AC3: In MANUAL mode reactions are off, and I set any character's face via the portrait menu (MULTI-17).

**MULTI-17: Portrait menu** · Must
- AC1: Clicking or right-clicking any portrait on the stage (group, debate, watch) opens a small skewed **portrait menu** (O24) with only the actions valid for the mode:
  - `Speak next` (group, watch);
  - `Set face ▸` (MANUAL only);
  - `Mute / Unmute` (group, watch; Should; skips their turns);
  - `View profile`.
- AC2: There are no other click behaviours on portraits, so the same gesture always means the same thing.

### Moderated debate
**MULTI-05: Debate configuration** · Must
- **Motion** (required, ≤ 200 chars). "Suggest motions" offers 3 (Should).
- **Format:**
  - `Two sides` (Proposition vs Opposition; drag portraits into columns or "Auto-assign"; uneven sides allowed).
  - `Panel` (each debater argues their own position; **summary-only verdict, no winner**).
- **Rounds:** `Quick` (Opening → Closing) · `Standard` (Opening → Rebuttal → Closing). *Extended with cross-examination is v1.1.*
- **Turn length:** Short / Medium / Long (≈ 80 / 150 / 250 words). With 5 debaters the default is Short.
- **Moderator:** `You` (default; the system only plays the phase banners) · `Auto host` (an AI host voices the transitions). *A cast character as chair is v1.1.*
- **Verdict by:** `Arbiter (AI)` · `You decide` · `None (summary only)`. When Format = Panel, only `Arbiter summary` and `None` are offered.
- AC1: Start is disabled until there's a motion and, for two-sided, at least 1 debater per side.

**MULTI-06: Debate run** · Must
- AC1: A round banner slams in ("ROUND 2: REBUTTAL") with a gong.
- AC2: Layout:
  - Two-sided: Proposition on the left, Opposition on the right, the motion banner top-centre.
  - Panel: an arc.
  - In both, the speaker slides toward the centre and listeners react (MULTI-04).
- AC3: A **timeline rail** shows the rounds, the current turn and the speaker queue ("NEXT ▸").
- AC4: Every log entry is labelled with round, side and speaker.

**MULTI-07: Steering controls** · Must
- AC1: Controls: ❚❚/▶ · Next turn (when auto-advance is off) · **Ask…** (pick a character and type a directed question) · **Interject** (a moderator note seen by all) · Extend round · Skip to closing · End debate.
- AC2: An auto-advance toggle (default ON, 1.5 s between turns).
- AC3: Steering appears in the log as **MODERATOR** messages in house style (not any character's palette).
- AC4: **End debate** before closing asks: **"Go to verdict now (≈ $x)"** or **"End without verdict"**.
- AC5: **Auto host presentation:** a "HOST" name plate on a `horizon-500` tape, with **no portrait** and no palette. Host lines appear under the motion banner and are logged in house style.

**MULTI-08: Verdict & summary** · Must
- AC1: A full-screen card shows: the motion; **"STRONGER CASE: {side}"** (two-sided with Arbiter or You) or "Summary" (panel/none); **rubric bars** per criterion (the criteria are **data**, from `rubric[]`; mock fixtures use Evidence · Rebuttal · Clarity · Persuasion); 3–5 bullet summary per side; a "Key disagreement" line; a short rationale.
- AC2: The copy depends on `decidedBy`. **Arbiter:** "Arbiter's assessment of **argument quality**, not of which side is factually right." **User:** "**Your call** · stronger case: {side}".
- AC2b: If the Arbiter finds no clear winner (`strongerCase: null` in two-sided mode), the banner reads **"TOO CLOSE TO CALL"** and the Arena track continues.
- AC3: In "You decide" mode, the summary comes first, then I **pick the stronger side** (one click; no scoring form, D-48), then the reveal plays. Rubric bars appear only if the Arbiter also scored, behind "Show Arbiter's view".
- AC4: If the backend provides no scores, the bars are hidden and the summary shows alone.
- AC5: Actions: Export Markdown · Rematch · Back to Hub · **Continue as group chat** (creates a **new** group session seeded with the debate summary and linked via `continuedFrom`).

### Watch them talk
**MULTI-09: Watch configuration** · Must
- Premise/scene (required, ≤ 300 chars) · Length **10 / 20 / 40 turns** (default 20) · Pace **Slow / Normal / Fast** (3 s / 1.5 s / 0.5 s between turns) · Opening speaker (Auto / choose) · Music (Follow speaker / Scene bed).

**MULTI-10: Playback controls** · Must
- AC1: Transport: ❚❚/▶ · Step · Pace **Slow / Normal / Fast** · Stop. *(×1/×2/×4 is reserved for Replay and the mock demo speed, never the Watch pace.)*
- AC2: At the turn limit, an "Episode end" card offers: Continue +10 · Summarise · Back.
- AC3: The turn limit, the **daily cap** (STATE-06) and each character's **energy** (ENG-04: exhausted characters are skipped; if everyone is asleep, playback pauses with a top-up prompt) bound every run. **There are no unbounded runs.**

**MULTI-11: Step in & director's notes** · Must
- AC1: **Step in** pauses playback, and a composer slides up from the transport bar so I can speak as myself. Up to 2 characters respond (the same rule as group Auto), then a prompt appears: "▶ Resume the scene".
- AC2: **Director's note** 🎬 injects a scene event ("The rain stops.") shown as a stage-direction strip. I'm not a participant.
- AC3: The portrait menu's `Speak next` nudges that character to speak next (MULTI-17).

### Shared
**MULTI-12: Music in multi sessions** · Must. See MUS-08.
**MULTI-13: Leave & resume** · Must. Leaving pauses the session. Resuming restores cast, config and playback state (paused).
**MULTI-14: Export transcript** · Should. Markdown with mode, cast, config, messages (emotions as tags) and verdict.
**MULTI-15: Replay** · **Must**
As the stakeholder recording the demo (and Alex in demo mode), I want to replay a past session with its original pacing, emotions, reactions and banners, so I get a perfect take for free.
- AC1: History → session → "Replay" plays it read-only with transport controls and Insight data.
- AC2: A "REPLAY" badge is visible during playback.
- AC3: Seed sessions are replayable in demo mode, and stay replay-only with a key (APP-09 AC6).
**MULTI-16: Speaker queue visibility** · Must. The "NEXT ▸" chip is always visible in group and debate modes.

---

## Epic EMO: Emotions & portrait animation

**EMO-01: Emotion set** · Must. 7 emotions, each with an icon, hotkey, VFX and SFX (doc 04 §6).
**EMO-02: Crossfade** · Must. Crossfade starts ≤ 100 ms, completes ≤ 300 ms, with a 1.02→1.0 scale settle. No hard swaps.
**EMO-03: VFX layer** · Must. A one-shot overlay on change (≤ 1.2 s) plus a subtle loop for some emotions. Off with reduced motion or VFX Off.
**EMO-04: Idle life** · Must
- AC1: Breathing: scale 1.000→1.008 over a 4 s loop, with the transform origin at the bottom.
- AC2: Parallax: 6–10 px opposite the cursor (chat and profile only).
- AC3: Blink (Should): neutral only, every 3–6 s, 80 ms, only when a blink asset exists.
**EMO-05: Mode semantics** · Must. AUTO and MANUAL per CHAT-04; global default in SET-03.
**EMO-06: Missing-emotion fallback** · Must. Show neutral + the emotion's VFX + a tint, and never a broken image. In Lean mode a small chip offers "Generate *embarrassed* (≈ $x)". Auto-generating missing emotions is **off by default** (Settings).
**EMO-07: Custom emotions** · Could *(full product)*

---

## Epic MUS: Music & SFX

**MUS-01: Theme in 1:1** · Must. The character's theme plays on loop (fade-in 1.5 s) on their profile and in chat.
**MUS-02: Crossfade** · Must. Changing context crossfades over **≤ 2 s**. Moving between the same character's profile and chat doesn't restart the track.
**MUS-03: Ducking** · Must. Music ducks to 40% under stings (gong, VS, verdict, Summon) and recovers over 600 ms.
**MUS-04: Mini-player** · Must. A skewed chip at the top right with track name, mini-equaliser, mute and a volume popover.
**MUS-05: Hub music** · Must. World Select and the hub play a **free-library** main theme (system track).
**MUS-06: Autoplay unlock** · Must. No audio before the first gesture. If audio is blocked, the mini-player shows "▶ Enable audio".
**MUS-07: Missing-song fallback** · Must. Use the free-library ambient bed; the mini-player shows "No theme yet · Compose".
**MUS-08: Music in multi sessions** · Must
- Group and Watch default to **Follow speaker**, with a minimum dwell of 20 s and a 2 s crossfade (alternative: Scene bed).
- Debate plays the **Arena** system track, then a verdict sting, then on the verdict card the theme of the **highest-scoring debater on the stronger side** (otherwise the first-listed debater on that side). With no winner (tie, panel or none), Arena continues.
- All cast themes are preloaded at session open. Only one track plays at a time.
- **Follow speaker** starts with the first speaker's theme (otherwise the first cast member's). If a speaker has no theme, the current track keeps playing.
**MUS-09: SFX** · Must. ~20 SFX from a **free CC0 pack** (doc 04 §7), with SFX mute and volume.
**MUS-10: Pause when the tab is hidden** · Should.

---

## Epic ENG: Character Energy (⚡): the budget as a game mechanic

Every character has an **energy bar**, like stamina in a game. Talking costs energy, and the bar refills over time. It is how Horizon keeps spending low and visible without interrupting conversations with budget pop-ups (stakeholder idea, D-42).

**ENG-01: Energy bar** · Must
As any user, I want to see each character's energy at a glance, so I know how much they can still talk today.
- AC1: A slim ⚡ bar sits under the name plate everywhere a character appears: roster card, profile, 1:1 chat, and stage portraits in group, debate and watch.
- AC2: Display: `⚡ 640 / 1000`.
  - The bar fills in the character's palette `primary`.
  - It turns **amber below 40%** and **red below 20%** (Tired).
  - It shows a subtle shimmer while regenerating.
- AC3: Hover tooltip: "⚡ 640 / 1000 · ≈ US$0.064 left today · full in 8 h 38 m".
- AC4: Each reply visibly **ticks the bar down** (a short drain animation with a "−5 ⚡" float). The Insight drawer shows the same number (`TurnTrace.energy`).
- AC5: Seed characters ship with varied energy so every state can be seen: most are full, **Rin is Tired (180 / 1000)**, and **Takeshi is Exhausted (0 / 1000)** in one seed variant (doc 06 §9).

**ENG-02: What drains energy** · Must
- AC1: **Only the character's own talking** drains their energy: their replies in 1:1, group, debate and watch. The drain equals the actual cost in ⚡ (1 ⚡ = US$0.0001), rounded up.
- AC2: These **do not** drain energy (they count only against the daily cap): routing, listener reactions, host lines, verdicts, memory, profile drafting, images and the theme song.
- AC3: In multi-character sessions, **each speaker pays for their own lines**. A family dinner chat drains Hana, Takeshi and Rin separately.

**ENG-03: Regeneration** · Must
- AC1: Energy refills **gradually**, from empty to full in ~24 h (`max / 24` per hour), and never above `max` by regeneration.
- AC2: Default `max` = **1000 ⚡/day** (= US$0.10). It is editable per character on the profile (500 / 1000 / 2000) and as a global default in Settings → Cost.

**ENG-04: Exhausted state** · Must
- AC1: When a character can't afford a reply, they become **Exhausted**:
  - the portrait shows the neutral face, desaturated, with a **"Zzz" sleep VFX** (no extra image);
  - the name plate shows "EXHAUSTED · back in 3 h 12 m".
- AC2: **1:1:** sending a message shows an inline system note, "{name} is asleep (⚡ 0)", with **Top up** and **Wait** buttons. My typed text is kept.
- AC3: **Multi-character:** Exhausted characters stay on stage asleep and are **skipped** in turn-taking. The log notes "{name} is asleep, skipping." An @mention of an exhausted character triggers the same note with a Top up option.
- AC4: **Tired** (< 20%) is cosmetic only: an occasional yawn VFX and the red bar. They still talk.

**ENG-05: Top up** · Must
- AC1: "Top up" opens a small confirmation: "Give {name} +500 ⚡ (≈ US$0.05)?" with ⚡ +500 / +1000 options. It counts against the **daily cap** and is recorded in the ledger.
- AC2: A top-up plays a short "recharge" animation (the bar fills with a spark burst) and wakes the character.
- AC3: If the daily cap would be exceeded, the top-up is blocked with STATE-06.

**ENG-06: Rush hour** · Should
- AC1: During DeepSeek peak pricing (Mon–Fri 09:00–12:00 and 14:00–18:00 Malaysia time), a small **"RUSH HOUR · replies cost 2× ⚡"** chip shows next to the energy bars. The energy actually drained reflects the real cost.

**ENG-07: Energy in demo mode** · Must. Energy bars render from seed data and animate during Replay (recorded drains), but nothing regenerates or drains live.

---

## Epic SET: Settings (tabs: Connection · Audio · Chat · Display · Models · Cost · Data · About)

**SET-01: API key** · Must
- AC1: A masked OpenRouter key field with Show/Hide, **Test connection** (✓ / ✗ with reason) and Clear.
- AC2: After saving, only `sk-or-…a1b2` is shown. The key is stored on the user's machine only, and the UI says so.
- AC3: Without a key, the app runs in demo mode (APP-09).
**SET-02: Audio** · Must. Master, Music and SFX sliders; global mute; "Duck music under stings".
**SET-03: Chat defaults** · Must. Default emotion mode, group responder policy, debate auto-advance, Readable Mode default, speaker cut-ins on/off.
**SET-04: Display** · Must. Reduced motion, VFX intensity (Off/Subtle/Full), **flash intensity (Off/Low/Full)**, parallax, text size (S/M/L).
**SET-05: Models (Advanced)** · Should. Editable model IDs for: Main chat model · Decision model (System One) · Image model · Music model. Each has a "Test" button and an "Unverified model" warning; Reset to defaults is available. Overrides are saved locally, never to committed config.
**SET-06: Generation mode** (Cost tab) · Must. **Lean (default)**: 1 candidate, 4 emotions, the rest on demand. **Standard**: 2 candidates, all emotions at creation. "Auto-generate missing emotions" defaults to off.
**SET-07: Cost controls** · Should. Cost estimates on/off, confirm-before-generate on/off, cost HUD on/off.
**SET-08: Budget & energy** (Cost tab) · Must. Daily cap (default US$1.00), per-character creation cap (US$0.60), warn at % (80), and **default character energy** (1000 ⚡/day). There is **no per-session cap**: energy replaces it (D-42).
**SET-09: Spend view** · Should. Spend today and to date, by category (chat, decision, image, music), character and session, with an "estimated vs actual" delta.
**SET-10: Data** · Should. Reset demo data, delete all data (typed confirmation), show the data folder path.
**SET-11: About** · Must. Version, GitHub link, licence, asset credits (`ASSETS.md`), replay onboarding, keyboard shortcuts.
**SET-12: Presenter Mode** (Display tab) · Should. Hides the key and dev overlay, forces text size L, compact Insight drawer, and shows ×N/REPLAY badges.

---

## Epic INS: Insight ("see the AI think")

**INS-01: Insight drawer** · Must
As Alex (and anyone watching a demo), I want a drawer that shows what the AI did for each message, so the engineering is visible.
- AC1: Toggled with `I` or a header button; slides in from the right. Clicking any character message selects it.
- AC2: Sections, from `TurnTrace` (doc 05):
  - **Model:** ID, provider, first-token and total latency, tokens in / **cached** / out, cost, peak/off-peak.
  - **Energy:** ⚡ spent by this reply and remaining (e.g. "−5 ⚡ · 742 / 1000").
  - **Emotion:** chosen label, source, top-3 probabilities as bars.
  - **Routing:** decision question, candidates with probabilities, or "forced by you / mention".
  - **Memory:** long-term items recalled.
  - **In-session recall:** shown separately from memory.
  - **Context:** a token budget bar by section.
  - **Guardrail:** checks with pass/flag.
- AC3: **Sections without data are hidden, not shown empty.**
- AC4: Probabilities show a band label, e.g. `0.71 · HIGH`, never false precision. A routing "reason" in prose appears only if the backend provides one.
- AC5: **Behaviour:**
  - On opening, it selects the **latest character message**.
  - Selecting a user or host message shows "Insight is available for character messages."
  - It is a **400 px panel**: it pushes the log in S07 and overlays the right column in S09, S10 and S12.
  - **Compact** (Presenter Mode) = Model + Energy + Emotion + Routing at 300 px.
  - With nothing to show, it reads: "Send a message to see how {name} thinks."
**INS-02: Cost HUD** · Should. A header ticker ("$0.0042 · 3.1k tok") updated per message.
**INS-03: Graph trace view** · Could *(full product)*. A mini node diagram of the LangGraph path.

---

## Epic HIST: Session history

**HIST-01: History list** · Must
- AC1: Shown in the hub's Sessions tab and from the pause menu (world-scoped).
- AC2: Each row shows: mode icon, title (auto-generated, renameable), cast heads, message count, last updated, verdict badge.
- AC3: Filter by mode and character; sort by most recent.
**HIST-02: Resume** · Must. Resumes in the correct mode, with music and palette restored. An **ended** debate opens its Verdict (S11) read-only, with Rematch / Continue as group. An **ended** watch opens the Episode-end card.
**HIST-03: Rename / delete / export** · Must (rename, delete) · Should (export).
**HIST-04: Search across sessions in a world** · Could.

---

## Epic STATE: Empty, loading & error states

**STATE-01: Empty states** · Must. Each has an illustration (a silhouette with diagonal tape), one sentence and one CTA:

| Where | Copy | CTA |
|---|---|---|
| No worlds | "No universes yet. Every story needs a horizon." | + Create world · Restore demo data |
| Empty world | "This world is quiet. Summon someone." | + New Character |
| < 2 characters (multi setup) | "Multi-character sessions need at least 2 characters." | + New Character |
| No sessions | "No conversations yet." | Start chatting |
| Memory (mock) | "Nothing remembered yet. Talk to {name}." | Chat |
| Knowledge (mock) | "Drop documents to teach {name}." | Upload |
| History filter, no results | "Nothing matches these filters." | Clear filters |
| Archived filter, empty | "No archived characters." | none |
| Profile Sessions tab, empty | "{name} hasn't joined any conversations yet." | Chat |
| Spend view, empty | "No spending yet. Everything so far was free." | none |
| Backlog search, no hits | "No lines match '{query}'." | Clear |

**STATE-02: Loading states** · Must. Whole pages never get spinners; use skewed skeleton cards instead.

| Situation | Treatment | Cancel? |
|---|---|---|
| Profile drafting | Scanning stripe, "DRAFTING…" kinetic label, staggered field reveal | Yes |
| Portrait generating | Silhouette with halftone "developing" shimmer, steps + elapsed time | Yes |
| Emotion batch / sheet | Per-slot shimmer or contact-sheet develop, then reveal | Yes (stops remaining) |
| Song composing | Spinning vinyl + waveform skeleton; background pill if the user navigates away | Yes |
| Awaiting first token | "…" bubble + portrait "lean-in" | Stop |
| Next speaker (multi) | "NEXT ▸ {name}" pulses; their portrait brightens | Pause |

**STATE-03: Error states** · Must. Red-ink "WARNING" tape, plain language and one action. **Typed input is never lost.**

| Error code | Copy | Action |
|---|---|---|
| `missing_key` | "Horizon needs your OpenRouter key to think." | Open Settings |
| `invalid_key` | "That key was rejected by OpenRouter." | Update key |
| `insufficient_credits` | "Your OpenRouter balance ran out." | Open OpenRouter · Retry |
| `rate_limited` | "Too many requests. Retrying in 12 s…" | Retry now · Cancel |
| `network` | "Can't reach the Horizon server." | Retry |
| `content_refused` | "The model declined this request. Try different wording." | Rephrase · Regenerate |
| `provider_error` (image) | Per-slot "FAILED" slash | Retry slot |
| song failed | "The composer stalled." | Retry · Skip |
| stream cut | Partial text kept + "(interrupted)" | Continue · Regenerate |
| `timeout` | "That took too long." | Retry |
| `energy_exhausted` | "{name} is asleep (⚡ 0)." (inline system note) | Top up · Wait |
| job resumed after restart | Toast: "Picked up where we left off." | n/a |

**STATE-04: Key-required gating** · Must. AI actions without a key open a compact modal ("Add key" / "Not now"); browsing stays available.
**STATE-05: Toasts** · Must. **Top-right, under the mini-player** (never covering the composer), skewed; auto-dismiss after 4 s; max 3; success/info/warn/error variants with SFX.
**STATE-06: Budget states** · Must. A toast at 80% of the **daily** or **creation** cap. At 100%, a **"Budget reached"** modal pauses the session or generation with "Raise cap" (deep link to Settings → Cost) or "Stop here", and a session shows a `pausedReason: daily_budget` banner. *(Per-character limits are handled by Energy, ENG-04, not by this modal.)*
