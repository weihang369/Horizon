# 09: Decision Log

How these requirements were produced:
1. Stakeholder interview (2 rounds of questions).
2. BA-Product and BA-Tech each wrote an independent Round-1 position paper.
3. Round-2 cross-critique: each rebutted the other's paper.
4. The Lead BA ruled on the remaining disputes and asked the stakeholder about 4 decisions outside the BA team's authority.
5. Round 3 was an independent audit of the consolidated pack by both BAs (67 defects and gaps found and fixed), followed by a second stakeholder round (cost, routing, energy, You card, OpenRouter-only).

**Source:** S = stakeholder · BA = team consensus · LB = Lead BA ruling.

| ID | Decision | Source | Alternatives considered | Rationale |
|---|---|---|---|---|
| D-01 | **The AI is the star; the UI makes it visible** (Insight drawer is a Must) | S + BA | Insight as a debug-only view | Memory, routing and context are invisible otherwise; the drawer also forces the AI team to emit traces early |
| D-02 | Worlds are isolated containers (name + cover only) | S | Themed worlds with lore | Stakeholder: "parallel universes, independent" |
| D-03 | **No relationship graph**; `relationshipToUser` is free text only | S | Graph + affinity meters | Stakeholder wants it simple; avoids a graph DB |
| D-04 | Create-a-Character = chip pickers → 2 candidates → pick → refine by text; **no sliders** | BA | Sims-style live sliders | Each image costs money and takes 10–40 s; live morphing is impossible |
| D-05 | 7 emotions. **Lean** generates 4 at creation and the rest on demand; **Standard** generates all 7. *Default superseded by D-40 (Lean)* | LB → S | Lazy-by-default (BA-Tech R1); 4-eager default (BA-Product R2) | Human review at creation still catches bad faces; Lean ≈ US$0.25, Standard ≈ US$0.50 per character |
| D-06 | Identity-consistency technique decided by a spike (reference edit vs expression sheet); UI designs both reveal variants | BA | Pick now | The evidence doesn't exist yet; the spike is cheap |
| D-07 | Emotion mode AUTO/MANUAL; **MANUAL changes the face only** | S | MANUAL also steers reply tone (BA-Product) | Stakeholder: no speech, face only |
| D-08 | Emotion shown at stream start, ≤ 800 ms hold, then late switch (NFR-29) | BA | Emotion only after the message ends | Face changing *as they start talking* sells it; narrows OQ-AI-07 |
| D-09 | **Character themes AI-generated**; **SFX and system tracks from free libraries** | S | Everything AI-generated | Stakeholder: AI only for each character's BGM; saves cost and licence risk |
| D-10 | Multi-session music: follow speaker (20 s dwell) for group/watch; Arena for debate; crossfade ≤ 2 s | LB | One track per session; ≤ 1 s crossfade | Theme songs are a signature feature; 1 s between unrelated tracks sounds like a skip |
| D-11 | Group responders: Auto ≤ 2, @mention always, "Everyone" button | BA | Everyone replies | 4–6 sequential streams are slow and noisy |
| D-12 | Debate MVP: two-sided Quick/Standard + panel (summary only); moderator **You or Auto host**; rubric **data-driven**; scores optional; copy says "Stronger case" and assesses argument quality, not truth | LB | Extended + cross-exam in MVP; character as chair; fixed rubric | Scope control; the rubric is evaluation design (AI team); avoids "rulings" on facts |
| D-13 | Watch: 10/20/40 turns (default 20), Continue +10, always bounded by budget | BA | "Until I stop" | No unbounded loops on a user's own key |
| D-14 | Cast **2–4**, 5th seat under Advanced | LB | 2–3; 2–5 | Latency and context growth, not cost, is the limit |
| D-15 | **Replay is a Must**, built on a persisted `SessionEvent` log | LB | Should / not modelled | One engine serves the mock, Replay, demo mode and screen recording |
| D-16 | **No-key demo mode is a Must** | BA | Ask for a key on first run | Visitors won't paste a paid key before seeing value |
| D-17 | MockClient with **realistic** timings + ×1/×2/×4 demo speed + Mock State Switcher | LB | Optimistic timings (BA-Product R1) | The stakeholder must approve how the real product feels, including failures |
| D-18 | Doc 05 is the single data contract; fixtures are shared with the backend | BA | Separate UI-only shapes | Prevents a rewrite when SWE swaps in the backend |
| D-19 | 12 fixed palettes; contrast fixes to Crimson, Forest Sage, Ember Ash (dark onPrimary), Royal Verdict (`#6E5FE6`), Midnight Ink (`#6286BA` + dark onPrimary) | LB | Original values | 5 of 12 failed WCAG checks (verified by script) |
| D-20 | **Content floor: adults only** (age int ≥ 18, adult-appearance clause); interim SFW; rating/safety/evaluation design → AI team | S + LB | BA designs the rating system | Stakeholder deferred evaluation to the AI team; the adult floor is non-negotiable for a public project |
| D-21 | **Rin aged to 22**, with adult styling | S | Keep 19; replace | Avoids youthful-coded design next to a romance character in a public showcase |
| D-22 | **Cost-first, Chinese-models-first** (DeepSeek, Qwen Image, Seedream, Jev) | S | Premium defaults | Stakeholder is cost-sensitive (MYR); premium models are opt-in |
| D-23 | **Seed Asset Sprint approved**, hard cap US$5, in parallel with UI/UX | S | Placeholders only | Real art is needed to approve the look; it doubles as the consistency spike |
| D-24 | Fonts self-hosted; no runtime CDN calls | BA | Google Fonts at runtime | Local-first, offline-friendly, NFR-13 |
| D-25 | Delete character → **Archive** by default; permanent delete separate | BA | Hard delete | Preserves multi-session history |
| D-26 | Blink frame: Should, optional, kept only if the alignment check passes | LB | Must; skip | Cheapest "alive" cue, but a misaligned blink looks like a twitch |
| D-27 | SME disclaimer tape when a character has `advisory: true` | BA | None | Credibility and honesty for expert panels |
| D-28 | Readable Mode is a Must | BA | Style everywhere | Long expert answers must stay readable |
| D-29 | Presenter Mode: Should | BA | None | Clean screen recordings |
| D-30 | Main LLM = **`deepseek/deepseek-v4.1-flash`** (stakeholder-confirmed; BA-Tech's first search missed it). Jev = typed decisions, 32K, alpha API | S + BA | V4 Flash / -0731 | Verified on OpenRouter; very new (2026-09-10), so V4 Flash is the fallback |
| D-31 | Profile drafting: client-side staggered reveal; backend doesn't need to stream fields | BA | Streamed structured output | Same feel, simpler backend |
| D-32 | One streaming session at a time | BA | Concurrent streams | Simplicity, cost and memory-write ordering |
| D-33 | "Continue as group chat" creates a **new** session (`continuedFrom`) | BA | Mutate the session's mode | Keeps the session model and Replay sound |
| D-34 | Regenerated replies are variants; only the active one feeds context and memory | BA | Ambiguous | A memory-design constraint made explicit |
| D-35 | Debate sides are `prop` / `opp` | LB | pro/con | Matches the UI copy |
| D-36 | **Launch/marketing material lives in git-ignored `private/`**; public docs stay product-focused | S | Marketing in public docs | Stakeholder: it's an open-source project |
| D-37 | LangGraph-only multi-agent recommended (not decided) | BA → AI team | CrewAI, AutoGen | AutoGen is in maintenance mode; a second framework duplicates state |
| D-38 | **Every AI call goes through the OpenRouter API; no local models, no GPU.** Music = **Lyria 3 Clip** via OpenRouter | S | ACE-Step local, Mureka (second key) | Stakeholder's hardware limitation; one key keeps setup at ≤ 5 min |
| D-39 | Debate role: **moderate only**; verb **"Summon"**; Lean **defers** (not removes) emotions; licence **MIT** | S | Argue a side; Create/Awaken; permanent 4; Apache/AGPL | Stakeholder answers to Q-S1..S4 |
| D-40 | **Lean is the default generation mode** (Standard opt-in) | S | Standard default | "Make sure it's cheap": ≈ US$0.25 vs ≈ US$0.50 per character |
| D-41 | Main LLM pinned to the **DeepSeek first-party endpoint**, `require_parameters`, full-precision fallback, cache-friendly prompt layout | S | OpenRouter default routing (cheapest providers) | With caching it costs about the same as the cheapest third-party, without fp4 quality drift or ignored parameters. 2× at MYT peak hours is accepted |
| D-42 | **Character Energy (⚡)** replaces the per-session cap. 1000 ⚡/day per character (= US$0.10); **only the character's own talking drains it**; gradual 24 h regen; Exhausted = asleep (Zzz), skips turns, top-up after confirmation; daily cap stays as the safety net | S (idea) + LB (spec) | Per-session cap US$0.10 / US$0.25 | Stakeholder's idea. It gamifies cost control and never interrupts 1:1 chats with budget pop-ups |
| D-43 | Per-world **"You" card** (display name + one line) | S | Global name; none | Life-sim warmth; respects world isolation |
| D-44 | **Exactly one theme song per character**; regenerating replaces it | S | Song history / versions | Stakeholder: "only one song… the character theme song" |
| D-45 | **Opaque portraits:** framed card / radial mask is the primary design | LB | Transparent cut-outs, rembg, chroma key, premium model | Default models can't output transparency; local tools are excluded by D-38 |
| D-46 | **One message with one emotion per character turn** (no multi-bubble replies) | LB | Up to 3 bubbles per turn | Matches the contract, NFR-29 and one-trace-per-message; seed transcripts fixed |
| D-47 | **Seed sessions stay replay-only**; "Continue live" forks a new session | LB | Resume seeds in place | Keeps demo recordings pristine; reuses `continuedFrom` |
| D-48 | "You decide" verdict = **pick the stronger side only** | LB | Score each criterion; remove the mode | One click; keeps the verdict card design |
| D-49 | Seed Asset Sprint: **script-enforced stop at US$4.50**, go/no-go after the spike, image model chosen on quality | LB | Raise the cap; shrink the spike | Corrected estimate ≈ US$3.10–4.15 against the US$5 cap |
| D-50 | Round-3 UX fixes: provisional AI-pick palette in the wizard, step-gate table, **portrait menu** (one gesture, one meaning), **Alt+1…7** face keys and focus-safe shortcuts, Watch pace = Slow/Normal/Fast (×N only for Replay), toasts top-right, palette hover without flood, "TOO CLOSE TO CALL", Archive/Restore rules | LB | (various) | Fixes 29 + 38 audit defects that would have made UI/UX build the wrong thing |
| D-51 | **Contract rev. 1.1 (additive, `schemaVersion` 1):** `message` and `session.state` events; `emotion` without `messageId` = MANUAL face change; `AppSettings.pricing`; `forkSeedSession(…, atSeq?)` | LB (raised by the UI/UX team) | Keep the contract and fake replay of user lines in the UI | Without them Replay can't reproduce user lines, steering, face changes, mutes or verdicts, and the rush-hour chip has no source |
| D-52 | **UI-stage placeholders:** "Shadow Self" SVG silhouette portraits (palette rim-light, glowing emotion glyphs, "PLACEHOLDER" tape) and **procedurally synthesised WebAudio** SFX, system tracks and per-character theme sketches (labelled "SKETCH") | LB (UI/UX team) | Grey boxes; download a CC0 pack now | Licence-clean, zero assets, swap to real WebP/audio by URL only. The Seed Asset Sprint and the CC0 pack (D-09) still replace them before release |
| D-53 | **Layout refinements inside the reference layouts' intent:** Group stage uses two **wings** of portraits beside a full-height log (the row layout leaves a ~300 px log at 1280×720); History (S13) **is** the hub's Sessions tab, with the pause menu deep-linking to it; S07/S09/S10/S12 share one session screen whose bottom **Dock** changes by mode (Composer / Steering / Transport / Replay / Demo) | LB (UI/UX team) | Follow doc 03 ASCII literally | The ASCII layouts are references, not ACs. Size, step-forward and portrait-menu rules are unchanged |
| D-54 | **Palettes in multi-character scenes are scoped:** chrome stays house `horizon-500`; each palette lives only in its character's frame, plate and energy bar; the active speaker tints the stage band. Debate sides: PROP = `horizon-500` tape, OPP = `paper-50` tape (ink text) | LB (UI/UX team) | Flood the whole UI per speaker | Five palettes at once breaks doc 04's "one loud colour" rule and the 3-flashes/s limit |
| D-55 | **Ceremonies are skippable:** Summon, VS, Shatter, Banner Slam and the Verdict reveal resolve to their end state on any key or click (≤ 120 ms), and the key is replayed. Palette CSS variables **snap under the flood** (never interpolated) | LB (UI/UX team) | Block input during ceremonies | Keeps APP-03 AC2 ("input never blocked > 600 ms") and NFR-03 (transform/opacity only) |
| D-56 | **Exhausted portrait shows the `blink` (eyes-closed) image** when a character has one, falling back to `neutral`. Neutral stays **silent** in sessions (its kit sound is used only for UI hover in the picker) | LB (UI/UX team) | Neutral image while exhausted (doc 04) | Eyes closed reads as "asleep" at a glance, on top of the greyscale layer and 💤 badge (R19) |
| D-57 | **Contract rev. 1.1, additive:** `session.state` gains `settings?` (title, emotion mode, music policy, Readable mode, config such as responder policy and auto-advance) for **mid-session settings changes** | LB (raised by the UI/UX team) | Re-fetch the session on `entity.changed` | One event pipeline (R1): Replay and the future `HttpClient` see settings changes in order, with no extra round-trip |
| D-58 | **"Continue" on an interrupted reply re-generates it** in the hardcoded stage (`chat.regenerate`, original kept as a variant). A true `chat.continue` (append to the cut text) is **deferred to SWE** as a contract rev. 1.2 candidate | LB (raised by the UI/UX team) | Add `chat.continue` to the contract now | Keeps the contract frozen during the UI stage; the button and the variant UI already work, and only the command behind them changes later |
| D-59 | **Knowledge citations in the UI** (contract rev. 1.2, additive): `Message.citations[]` + `[n]` markers in `content`, `TurnTrace.knowledge` (every retrieved passage, `cited` or not), `KnowledgeChunk` + `characters.knowledgeSource()`, overlay **O28 Source viewer**, and `citations` on `turn.end`. Shown as inline `[n]` chips with a hover quote, a Sources strip under the bubble, and a Knowledge section in Insight. **How** passages are retrieved and cited is left to the AI team (OQ-AI-03) | S (stakeholder request, 2026-10-03) + LB | A Sources strip only; leave it all to v1.1 | The BA recommendation already said "Show citations". Showing which sentence came from which page makes the RAG visible (D-01), and the fields are optional, so a backend without RAG still conforms |

## Round 3 audit highlights

- **BA-Product found:**
  - a palette used before it was chosen;
  - single-key shortcuts firing while typing;
  - two conflicting Watch pace controls;
  - one portrait click meaning three things;
  - seed transcripts implying undefined behaviour (multi-bubble, unprompted replies);
  - 20 places where designers would have to guess (vocabulary, fixtures, copy).
- **BA-Tech found:**
  - DeepSeek peak pricing (2× during Malaysian working hours);
  - OpenRouter routing to quantized endpoints;
  - Qwen's per-reference fee;
  - a wrong `:batch` claim;
  - no transparency on cheap image models;
  - contract enums contradicting stories;
  - seed IDs that weren't valid ULIDs;
  - brand-colour text failing contrast;
  - the per-session cap breaking 1:1 chats, which led to the stakeholder's **Energy** idea.

## Debate highlights (where the team changed its mind)

- **BA-Tech conceded:**
  - the Insight drawer, Replay and listener reactions are Musts;
  - all emotions are generated at creation by default;
  - BA-Product's 12-palette system.
- **BA-Product conceded:**
  - no Create-a-Sim sliders;
  - BA-Tech's data contract is canonical;
  - realistic mock timings;
  - watch-mode turn caps;
  - Archive instead of delete;
  - demo mode is a Must.
- **The Lead BA ruled on:**
  - emotion-generation default (Standard = all 7);
  - cast size (2–4 + 5 advanced);
  - crossfade ≤ 2 s;
  - blink as an optional Should;
  - moderator options (You / Auto host);
  - Replay as a Must.
- **The stakeholder decided:**
  - Seed Asset Sprint, kept cheap with Chinese models;
  - MANUAL = face only;
  - free SFX, AI-generated only for character themes;
  - Rin aged 22;
  - launch and marketing material kept in the git-ignored `private/` folder.
- **Errors caught in cross-review:**
  - 5 palettes failed contrast;
  - a mock-transcript arithmetic error ("a fifth" → "a quarter" more staff hours);
  - routing "reasons" can't come from Jev;
  - in-session recall was mislabelled as memory;
  - a forced speaker was shown with a meaningless router probability.
