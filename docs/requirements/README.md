# Horizon: Requirements Pack (BA Stage)

> **Status:** v1.0, ready for stakeholder review · **Date:** 2026-10-01
> **Authors:** BA team: Lead BA, BA-Product (experience and journeys), BA-Tech (feasibility, cost and data contracts)
> **Stakeholder:** Tan Wei Hang (product owner)

Horizon is an open-source **AI multi-character platform with a game-like anime interface**. You create isolated *worlds*, fill them with AI characters (a doctor, a lawyer, a girlfriend and her family), and chat 1:1, run group chats, moderate formal debates, or sit back and watch them talk. Each character has an anime portrait that changes with their mood, a signature colour palette, and an AI-composed theme song. **The AI is the star. The anime and Persona-style UI is the wrapper that makes it unforgettable.**

---

## Delivery pipeline

| Stage | Team | Output | Gate |
|---|---|---|---|
| **1. Requirements** (this pack) | BA team | These documents | Stakeholder approves this pack |
| **1b. Seed Asset Sprint** (in parallel with stage 2) | AI lead or maintainer | Real seed portraits and theme songs (≤ US$5) + image-consistency findings | Assets committed with provenance |
| **2. Frontend (hardcoded)** | UI/UX designers | React app, **no backend**, all data mocked via `MockClient` | **Stakeholder is satisfied with the UI** |
| **3. Backend** | Software engineers | FastAPI + SQLite + filesystem, implementing the data contract | Contract tests pass; mock is swapped for HTTP |
| **4. AI** | AI engineers | LangGraph agents, memory, context engineering, multi-agent, generation | Evaluation and demo-ready |

## Documents

| # | Document | Primary reader | What it answers |
|---|---|---|---|
| 01 | [Vision & Scope](01-vision-and-scope.md) | Everyone | Why, for whom, signature moments, what's in and out, phasing |
| 02 | [Functional Requirements](02-functional-requirements.md) | UI/UX, SWE | Epics → user stories → acceptance criteria (with IDs) |
| 03 | [Screens & Flows](03-screens-and-flows.md) | UI/UX | Screen inventory, overlays, navigation map, reference layouts |
| 04 | [Visual, Motion & Audio Direction](04-visual-motion-audio.md) | UI/UX | Design principles, tokens, 12 palettes, transitions, emotion VFX, SFX, music behaviour |
| 05 | [Data Contract](05-data-contract.md) | UI/UX, SWE, AI | Entities, lifecycles, streaming events, mock rules. **The single source of truth for shapes** |
| 06 | [Seed & Mock Data](06-seed-data.md) | UI/UX, AI | 2 worlds, 6 characters, 5 transcripts, asset list, Seed Asset Sprint |
| 07 | [NFRs, Risks & Cost](07-nfr-risk-cost.md) | SWE, AI | Performance, budget guardrails, setup, accessibility, risk register, cost model |
| 08 | [Open Questions & Handoff](08-open-questions-handoff.md) | SWE, AI | Deferred decisions with options and recommendations |
| 09 | [Decision Log](09-decision-log.md) | Everyone | What the BA team debated, what was decided, and why |

## How to read the IDs

- `APP-`, `WLD-`, `CHR-`, `PRF-`, `CHAT-`, `MULTI-`, `EMO-`, `MUS-`, `SET-`, `INS-`, `HIST-`, `STATE-`: user stories (doc 02)
- `S01…`, `O01…`: screens and overlays (doc 03)
- `NFR-xx`: non-functional requirements · `R-xx`: risks (doc 07)
- `OQ-SWE-xx`, `OQ-AI-xx`: open questions for later teams (doc 08)
- `D-xx`: decisions (doc 09)

**Priority (MoSCoW)** is stated **for the UI/UX (hardcoded) phase** unless marked *(full product)*.

## Ground rules from the stakeholder (non-negotiable)

1. **Not production.** No login, auth or security hardening. Runs locally with your own OpenRouter key.
2. **Desktop only, English only.**
3. **Game-like, not a game.** React with heavy animation; **no game engine**, no Live2D, no 3D.
4. **Worlds are isolated parallel universes.** Nothing crosses worlds.
5. **No relationship graph** between characters. Relationships exist only as profile text.
6. **Everything AI-generated where it matters:** profile, portraits and emotions, and each character's theme song. *UI sound effects and system background tracks come from free, licence-clean libraries.*
7. **Cost matters a lot.** Prefer cheap models, with Chinese models first (DeepSeek, Qwen, Seedream…).
8. **Every AI call goes through the OpenRouter API. No local models and no GPU requirement** (hardware limitation). Music is the one non-Chinese exception (Google Lyria), because it is the only music model on OpenRouter.
9. **AI design (memory, context engineering, RAG, multi-agent framework, safety and evaluation) belongs to the AI team.** These docs frame it as questions, not answers.

## Glossary

| Term | Meaning |
|---|---|
| **World** | An isolated container of characters and sessions (a "parallel universe"). Name and cover only, no lore. |
| **Character** | An AI persona. Its profile **is** its system prompt. Has a portrait set, a palette and a theme song. |
| **Session** | A conversation in one of 4 modes: `one_on_one`, `group`, `debate`, `watch`. |
| **Emotion set** | 7 portraits: neutral, happy, sad, angry, surprised, thinking, embarrassed. |
| **AUTO / MANUAL emotion** | AUTO: the AI picks the emotion per reply. MANUAL: the user sets the face (face only). |
| **Lean / Standard** | Image generation modes. Lean (default): 1 portrait + 4 emotions, rest on demand (≈ US$0.25/character). Standard: 2 portraits + all 7 (≈ US$0.50) |
| **Energy (⚡)** | Each character's stamina bar. Talking costs ⚡ (1 ⚡ = US$0.0001), it refills over ~24 h, and an empty character falls asleep until topped up. It is the per-character budget |
| **You card** | Optional per-world card (your display name + one line) so characters in that world know who you are |
| **Insight drawer** | A side panel showing what the AI did per message (model, cost, emotion probabilities, routing, memory, context budget). |
| **Jev** | TypeSafe Jev 1.13: a cheap "System One" decision model (typed answers + probabilities, no prose). |
| **MockClient** | The frontend's fake backend that replays recorded event streams with realistic timing. |
| **Demo mode** | Running without an API key: browse the seed data and replay recorded sessions, no generation. |
| **Seed Asset Sprint** | A one-off, budget-capped run that generates the real seed art and music and tests image consistency. |
