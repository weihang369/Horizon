# 08: Open Questions & Handoff

> These are **not decisions**. Each item gives options, trade-offs and a **BA recommendation** that the receiving team may accept or override, recording its choice in its own design doc. Constraints already fixed by the stakeholder or by docs 01–07 are listed as **Constraints**.

---

## Part A: Software Engineering team

**Fixed stack:** Python **FastAPI**, **SQLite + filesystem**, React frontend, local-first, no auth.

**OQ-SWE-01: API shape & streaming transport**
- Options:
  - A) REST + **SSE** for server→client streams, with REST POST for commands.
  - B) REST + WebSocket.
  - C) GraphQL subscriptions.
- **Recommendation: A.** One SSE stream per active session and one per generation job, using the event schema in doc 05 §6. SSE is simple, auto-reconnects and is easy to mock.

**OQ-SWE-02: Job queue for generation**
- Options:
  - A) SQLite job table + in-process asyncio workers.
  - B) Celery/RQ + Redis.
  - C) FastAPI `BackgroundTasks` only.
- **Recommendation: A**, with per-provider concurrency limits (e.g. 2 images in parallel) and backoff on 429. B breaks zero-config. C loses jobs on restart (NFR-19).

**OQ-SWE-03: Asset storage layout**
- Options:
  - A) `data/assets/{worldId}/{characterId}/{kind}_{emotion}_v{n}.webp`.
  - B) Content-addressed storage.
- **Recommendation: A.** It's human-browsable (an OSS showcase), and immutable versioned names make caching safe.

**OQ-SWE-04: Persistence stack**
- Options: A) SQLModel/SQLAlchemy + Alembic. B) Raw `sqlite3` + SQL migrations.
- **Recommendation: A**, in WAL mode. Coordinate with the AI team on whether LangGraph checkpointer and store tables share the DB file.

**OQ-SWE-05: Mock → backend swap.** *Agreed:* the typed `HorizonClient` with `MockClient` and `HttpClient`, plus shared fixtures under `seed/` (doc 05 §7). SWE implements `HttpClient` and contract tests.

**OQ-SWE-06: Sprite background handling.** **Resolved (D-45):** portraits are opaque framed cards or radially masked. Neither default image model supports transparency, and local background removal is excluded (OpenRouter only). SWE serves opaque WebP as-is.

**OQ-SWE-07: Budget enforcement point**
- **Recommendation:** a central OpenRouter gateway module that every provider call passes through. It pre-checks the estimate, records the actual `usage.cost`, `provider`, cached tokens and peak/off-peak, and enforces the **daily cap, creation cap and character energy**. It also applies the routing policy (NFR-33). The AI team's code must use it.

**OQ-SWE-08: Run & packaging**
- **Recommendation:** `uv` + `npm` with one root dev command. A "demo run" where the backend serves the built frontend. Docker optional (Later).

**OQ-SWE-09: Concurrency semantics.** *Constraint:* one streaming session at a time (NFR-31). Open question: can a character appear in two *paused* sessions? Recommendation: yes, with memory writes serialised per character.

**OQ-SWE-10: Export/import & reset.** *Constraint:* reset-to-seed is in the MVP. World export/import (zip of JSON + assets) is v1.1.

**OQ-SWE-11: SessionEvent storage** (Replay + demo mode)
- Options: A) Persist every SSE event. B) Reconstruct replay from messages.
- **Recommendation: A** (small text rows). B is the fallback.

**OQ-SWE-12: Secret hygiene.** `.env.example`, key never logged, localhost bind, pre-commit secret scan (e.g. gitleaks) recommended.

**OQ-SWE-13: Energy implementation** (ENG epic, doc 05 `Energy`)
- *Constraints:*
  - Lazy regeneration (`current = min(max, current + max/24 × hours)`); no timers.
  - Drain = actual cost of the character's own reply, rounded up to whole ⚡.
  - Top-ups are bounded by the daily cap.
  - Emit an `energy` event after each change.
- Open questions:
  - **Pre-flight check:** how to decide "can afford a reply" before generating (estimate from the last N replies vs a fixed minimum such as 10 ⚡)?
  - **Overdraft:** what if a reply costs more than the remaining energy mid-stream? Recommendation: allow it to finish and clamp at 0, never cut a reply mid-sentence.
  - **Concurrency:** serialise energy writes per character.
  - **Timezone:** where "today" starts (MYT by default; configurable).

---

## Part B: AI Engineering team

**Fixed:**
- **LangGraph** is the base framework.
- **OpenRouter** is the gateway.
- **Cost is the priority, with Chinese models preferred.**
- Main LLM is **DeepSeek V4.1 Flash** (`deepseek/deepseek-v4.1-flash`, stakeholder-confirmed).
- Images are AI-generated, in one consistent anime house style.
- Each character's theme song is AI-generated.
- Profile = system prompt.
- MANUAL emotion = **face only** (does not change the reply).
- Characters are adults.

**OQ-AI-01: Memory architecture** *(stakeholder: "AI team to discuss deeply")*
- Options:
  - A) LangGraph checkpointer + rolling summary only.
  - B) A + LangGraph long-term **Store** with semantic search (embeddings in SQLite, e.g. sqlite-vec).
  - C) External framework (mem0, Letta, **Zep**).
  - D) Fully custom.
- Sub-questions:
  - **Scope:** per character per world. Does a character remember group or debate sessions from its own perspective?
  - **Write policy:** every turn, or importance-gated (Jev)?
  - **User control:** view and forget, via the PRF-07 Memory tab.
  - **Embeddings:** must come via the OpenRouter API (D-38; no local models). Verify which embedding models OpenRouter offers. If none fit, consider keyword/summary-based recall.
- *Constraint:* only the **active variant** of a regenerated message feeds memory.
- **BA recommendation: B**, per character within a world, importance-gated, exposed in the Memory tab and Insight drawer. C hides the engineering this project wants to showcase. **Run this spike in parallel with UI/UX (R-19).**

**OQ-AI-02: Context engineering**
- Prompt assembly order and **token budget per section**: style/system, persona, memory, knowledge, session summary, recent turns, mode instructions.
- Persona-drift mitigation; multi-agent perspective ("you are X; others said…"); a caching-friendly static prefix.
- The output must populate `TurnTrace.context` (the "context X-ray").
- **Recommendation:** a dynamic budgeter with a fixed static prefix. ~8K input for 1:1, ~12K for multi-agent.

**OQ-AI-03: Knowledge / RAG per character** (v1.1; the stakeholder wants it)
- Sources: pasted text, PDF/MD, URLs.
- Stores: sqlite-vec vs Chroma vs LanceDB.
- Retrieval triggers: always / tool call / Jev-gated.
- **Recommendation:** sqlite-vec (zero-config) with Jev-gated retrieval and an always-on fallback. Show citations.

**OQ-AI-04: Multi-agent orchestration** *(the stakeholder mentioned CrewAI/AutoGen as ideas)*
- Options:
  - A) LangGraph native (supervisor/router node, subgraph per character, `interrupt` for HITL and steering).
  - B) CrewAI on top.
  - C) AutoGen (**maintenance mode since Oct 2025**).
  - D) Microsoft Agent Framework.
- **Recommendation: A only.** A second framework duplicates state and checkpointing, and C is a dead end. Document why in the README; it's a good showcase point.

**OQ-AI-05: Debate orchestration**
- Structure: a deterministic phase state machine vs an LLM-driven moderator.
- Speaker order: fixed vs routed.
- Verdict: LLM structured output vs Jev rubric vs user vote.
- **Rubric criteria are yours to design** (the UI renders any 2–6 criteria from `rubric[]`).
- *Constraints:*
  - Two-sided Quick/Standard + panel (summary only) in the MVP.
  - Moderator: user or auto host.
  - The verdict assesses **argument quality, not truth**.
  - Scores are optional (the UI hides the bars when absent).
- **Recommendation:** a deterministic structure + LLM-voiced host prose. MVP scores via one cheap structured-output call; Jev rubric scoring in v1.1.

**OQ-AI-06: Group & watch turn-taking**
- Who replies (*constraint:* Auto ≤ 2, @mention always replies, "Everyone" button).
- Watch stop conditions (*constraint:* 10/20/40-turn caps + budget).
- Interrupt semantics.
- **Recommendation:** Jev "who would naturally respond?" with the top 1–2 above a probability band. Interrupts cut the stream immediately and keep the partial text.

**OQ-AI-07: Emotion source for AUTO mode**
- Options:
  - A) Inline tag from the main LLM at the start of the stream (stripped server-side).
  - B) Jev post-classification.
  - C) Jev pre-prediction before generation.
  - D) Structured output.
- *Constraint:* **NFR-29**, the emotion must show within 800 ms of the first token (p90), otherwise it switches late. B alone can't meet this.
- **Recommendation: A primary, B as validator/fallback.**
- *Note:* V4.1 Flash exposes `logprobs`/`top_logprobs` on some endpoints, which is a possible zero-cost source of emotion-tag probabilities for the Insight bars. Verify it on the pinned first-party endpoint.

**OQ-AI-08: Content rating, safety & evaluation** *(stakeholder: "evaluation → AI team")*
- Rating levels; guardrail placement (input, output, image prompts); provider refusals (`content_refused`); evaluation plan (persona adherence, emotion accuracy, debate quality, regression set).
- *Constraints (BA floor):* adults only (NFR-27); interim default SFW; image prompts always templated, never raw user text alone; no named IP or real-person likeness.
- **Recommendation:** MVP SFW only; Jev boolean guardrails with a DeepSeek fallback; write a ~30-conversation regression set during the MVP; evaluation harness in v1.1.

**OQ-AI-09: Image identity consistency** *(answered by the Seed Asset Sprint, doc 06 §7)*
- Options:
  - A) Prompt + seed.
  - **B) Base → reference edit per emotion.**
  - **C) Expression sheet → slice.**
  - D) Face inpainting with a mask.
  - E) Per-character LoRA (not available via OpenRouter).
- **Recommendation:** spike B and C on Qwen Image 3 and Seedream 4.5. The UI designs both reveal variants.

**OQ-AI-10: Image model & style lock**
- Default model; premium opt-in; resolution; StylePreset enforcement (prompt fragment + style reference images on every call); transparency.
- **Recommendation:** pick the default on **quality** from the spike (the price gap between Qwen Image 3 and Seedream 4.5 is only ~4–10% once Qwen's $0.003 per reference fee is counted). Pass style references whenever the model supports `input_references`. **Qwen allows at most 4 references (base + ≤ 3 style refs); Seedream allows 14, free.** Output is always opaque (D-45).

**OQ-AI-11: Music generation provider** *(constraint: per-character themes AI-generated; system tracks and SFX are free library)*
- *Constraint (D-38):* **OpenRouter API only, no local GPU.** This rules out local models (ACE-Step) and second-key providers (Mureka, ElevenLabs, Suno).
- Remaining options: **Lyria 3 Clip** (30 s, ~$0.04) vs **Lyria 3 Pro** (full song, ~$0.08), both Preview on OpenRouter.
- **Recommendation:** Lyria 3 Clip by default, behind a provider interface (so a future OpenRouter music model can be swapped in). Instrumental 30–60 s loops with loop points. If Lyria is unavailable, the character falls back to the free ambient bed. **Read Google's primary licence terms before committing any song.**

**OQ-AI-12: Jev usage points**

| Candidate | Value | Recommendation |
|---|---|---|
| Emotion validation/fallback | Medium | MVP |
| Listener reactions (batched, 1 call per turn) | High (demo) | MVP |
| Next-speaker routing | High (latency) | MVP |
| Input/output guardrails | High | MVP + fallback |
| Memory importance scoring | Medium | MVP if OQ-AI-01 = B |
| Intent detection / RAG gating | Medium | v1.1 |
| Debate rubric scoring | High | v1.1 |
| Watch "conversation exhausted?" | Low–Med | v1.1 |

Constraints: 32K state budget, alpha endpoint, varying probabilities. Use bands and wrap every call in a `Decider` with a DeepSeek fallback.

**OQ-AI-13: Main LLM parameters** *(model fixed: `deepseek/deepseek-v4.1-flash`; routing fixed: **DeepSeek first-party endpoint**, `require_parameters: true`, full-precision fallback only (D-41, NFR-33))*
- Open:
  - reasoning on or off per task;
  - temperature per mode;
  - a stronger model for host/verdict?
  - **reply-length limits per mode** (output tokens dominate cost once input is cached);
  - fallback behaviour during first-party outages.
- *Constraint:* a cache-friendly prompt layout (NFR-35): static style/persona prefix → history → dynamic memory/retrieval **last**.
- **Recommendation:** reasoning off for character turns, low for host/verdict/profile. `deepseek/deepseek-v4-flash` as model fallback. Reply caps ≈ 120 / 180 / 250 words for 1:1 / group / debate Long. Never `~latest` aliases in committed config.

**OQ-AI-14: Character creation pipeline.** **Recommendation:** a LangGraph graph with `interrupt` after the profile and after the base portrait (HITL), so emotions are never paid for on a rejected portrait.

**OQ-AI-15: Observability.**
- Options: A) Local structured logs + ledger. B) LangSmith (opt-in env flag). C) Self-hosted Langfuse (breaks zero-config).
- **Recommendation: A by default, with B opt-in.** `TurnTrace` is the user-facing view of the same data.

**OQ-AI-16: Prompt template for `systemPromptPreview`.** The profile → prompt compiler, including:
- the adult and SFW clauses;
- the world's **You card** (D-43);
- per-mode variants (1:1, group, debate, watch);
- the rule that each turn produces **one message with one emotion** (D-46).

**OQ-AI-17: Energy-aware orchestration**
- How routing treats exhausted characters: they are skipped and listed in `TurnTrace.routing.skipped`.
- What happens when a debate side is fully exhausted: pause with a top-up prompt (recommended) vs forfeit.
- Whether watch mode should prefer characters with more energy.
- *Constraint:* only a character's own reply generation drains their energy. Orchestration overhead (routing, reactions, host, verdict, memory) goes to the daily cap.

---

## Part C: Stakeholder questions (all resolved)

| # | Question | Answer |
|---|---|---|
| Q-S1 | Can the user also argue a side in debates? | **Moderate only** |
| Q-S2 | Verb for approving a character? | **"Summon"** |
| Q-S3 | Does Lean mode cut the emotion set permanently? | **No**: the other 3 are generated later on demand |
| Q-S4 | Licence? | **MIT** |
| Q-S5 | Default generation mode? | **Lean** (D-40) |
| Q-S6 | LLM routing? | **DeepSeek first-party endpoint** with caching (D-41) |
| Q-S7 | Per-session budget cap? | **Replaced by character Energy** (D-42) |
| Q-S8 | How do characters know the user? | **Per-world "You" card** (D-43) |
| Q-S9 | Local GPU / local models? | **No.** OpenRouter API only (D-38) |
| Q-S10 | Theme songs per character? | **Exactly one** (D-44) |
