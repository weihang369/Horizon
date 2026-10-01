# 01: Vision & Scope

## 1. Positioning

**One-liner:** *Horizon is an open-source multi-agent character sandbox. You summon AI personas, give them faces, moods and theme songs, and have them advise you, debate each other, or just live their lives.*

**Elevator pitch:** Horizon lets you create AI characters inside isolated "worlds". You might build a panel of a doctor, a lawyer and an economist, or a sitcom family you hang out with. Each character has a persistent personality, an anime portrait that changes with their mood, and an AI-composed theme song. You can chat 1:1, run a group chat, moderate a formal debate with an assessed outcome, or watch them talk among themselves. Under the hood it's LangGraph multi-agent orchestration with memory and context engineering, and **Horizon shows you that machinery live** as it runs. Bring your own OpenRouter key.

**Core thesis (agreed by the whole BA team):** the stakeholder wants the AI to be the star, and nobody can *see* memory, routing or context engineering unless the UI puts them on screen. So:
1. The UI **makes the AI visible** (Insight drawer, live routing and emotion probabilities, context budget, cost).
2. The anime and Persona-style layer exists to make those AI moments **feel dramatic**.

### Dual use
| Mode of use | Example | What matters most |
|---|---|---|
| **Serious** | "Summon an expert panel: public-health doctor, constitutional lawyer and labour economist. Debate a four-day work week." | Distinct, opinionated experts; steering; readable long answers; a summary you can export; an honest "AI simulation" label |
| **Casual / life-sim** | "My girlfriend Hana, her dad Takeshi and her sister Rin. Dinner group chat." | Characters that feel alive, react emotionally, have their own music, and remember you |

## 2. Personas

| Persona | Who | Jobs-to-be-done | Design implications |
|---|---|---|---|
| **P1 Priya, the Panel Convener** (serious) | 34, strategy/policy analyst | Pressure-test an idea against several expert views at once; get a crisp summary and outcome; return next week and have the economist remember | Readable Mode, debate steering, Markdown export, opinionated personas, memory |
| **P2 Jun, the Life-Sim Storyteller** (casual) | 27, plays The Sims and visual novels | Create a character that looks exactly right; chat and see them react; put characters in a scene and watch | Create-a-Character wizard, emotion VFX, theme songs, Watch mode with director's notes |
| **P3 Alex, the Repo Cloner** (OSS dev / AI engineer) | 30, found the repo on GitHub | Running with demo data in ≤ 5 min; see *why* the agents did something (which node, what was recalled, cost); swap models without code changes | **No-key demo mode**, Replay, Insight drawer, cost HUD, editable model IDs |

## 3. Signature moments (the experience the UI must nail)

These are the moments that define Horizon. UI/UX should treat them as the "hero flow" and polish them first:

1. **Title → World Select:** a kinetic "HORIZON" title, "Press any key", and tilted world cards that shatter into the hub.
2. **Creation with a human in the loop:** seed → fields reveal → appearance chips → 2 portrait candidates → pick → emotions develop → palette pick **re-themes the whole UI** → Summon reveal with the theme song.
3. **Debate live:** VS splash, round banners, the speaker steps forward, **listeners react with their faces**, the user steers ("Ask… Mei"), and the **Insight drawer** shows routing, emotion probabilities, context budget and cost.
4. **Verdict:** animated rubric bars, "STRONGER CASE", summary, export.
5. **Casual group chat:** the palette flips, family banter, faces react, and music hands off between characters.
6. **Energy:** each reply ticks a character's ⚡ bar down; a tired character yawns, an exhausted one falls asleep (Zzz) until recharged. Cost control as a game mechanic.
7. **Replay:** any of the above can be replayed deterministically (also powers no-key demo mode and screen recording via Presenter Mode).

## 4. Scope

### 4.1 In scope (MVP: first public release)
- Worlds: create, rename, delete; isolated.
- Character creation wizard: seed → AI draft → edit → appearance → portraits → emotions → palette → theme song → approve.
- Character profile, gallery, edit, archive.
- 1:1 chat with streaming, AUTO/MANUAL emotion, theme music.
- **All three multi-character modes:** group chat, moderated debate, watch-them-talk.
- Insight drawer, cost HUD, budget caps, **character energy bars (⚡)**.
- Per-world **"You" card** so characters know who you are.
- Session history, resume, Replay, Markdown export.
- **No-key demo mode** with seed worlds and pre-recorded sessions.
- Settings: API key, audio, chat defaults, display/accessibility, models, cost, data reset.

### 4.2 Explicitly out of scope (all phases unless the stakeholder reopens them)
- Authentication, accounts, multi-user, hosting/deployment, payments, production security hardening.
- Mobile/tablet layouts; i18n (English only).
- Relationship graph, affinity meters, graph database.
- Anything cross-world (characters, memory, sessions).
- World lore or themed world settings (a world is a name + cover).
- Game engine, 3D, Live2D, skeletal animation, **video generation**.
- **TTS / voice** and speech input.
- Real-time slider morphing of the character image.
- Telemetry, a character marketplace, web search/live internet grounding.

### 4.3 Phasing

| Phase | UI/UX (hardcoded) | SWE (FastAPI + SQLite/FS) | AI (LangGraph) |
|---|---|---|---|
| **Spikes** (parallel with UI/UX) | none | Contract review of doc 05; SSE replay harness | **Seed Asset Sprint** = image-consistency spike (≤ US$5); music provider and licence check; DeepSeek V4.1 Flash persona test + routing/caching test (first-party endpoint, record cached tokens); Jev smoke test; **memory design spike** |
| **MVP** | All screens in doc 03, every state, MockClient + State Switcher, Insight drawer, demo mode, Replay | CRUD, job runner, asset storage, SSE streams, event log, cost ledger + caps, seed import/reset, key handling | Profile generation with HITL, portraits + 7 emotions, theme song, 1:1 chat with memory, emotion tagging, group / debate / watch, baseline guardrails |
| **v1.1** | Richer memory/context inspector, Knowledge (RAG) tab, debate Extended format (cross-exam), character-as-chair | World export/import, evaluation run storage | Per-character RAG, debate rubric scoring via Jev, memory importance scoring, evaluation harness, optional full-length songs |
| **Later** | Custom emotions, more palettes, graph trace view | Optional Docker | Character-initiated messages, task-based model routing |

## 5. Success criteria (first public release)

| # | Criterion | Measure |
|---|---|---|
| SC-1 | A cloner sees something impressive fast | ≤ 5 min from `git clone` to demo mode (Python + Node installed); seed sessions replay with full animation without a key |
| SC-2 | The AI is visibly the star | Insight drawer shows model, emotion probabilities, routing, context budget and cost for every live character message (where applicable to the mode) |
| SC-3 | It looks like nothing else | Stakeholder sign-off on the UI phase; a full showcase can be screen-recorded using only Presenter Mode + Replay |
| SC-4 | It's cheap to run | Creating a character costs ≤ US$0.25 (Lean, default) / ≤ US$0.55 (Standard); a typical reply ≈ 4–8 ⚡ (US$0.0004–0.0008); a 3-debater debate ≤ US$0.03 (worst case at peak); each character's talking is bounded by its daily energy (1000 ⚡ = US$0.10) |
| SC-5 | It's safe to show publicly | All characters adult; SFW by default; SME sessions labelled "AI simulation"; no IP named in prompts |
