# 07: Non-Functional Requirements, Risks & Cost

**Reference machine:** a mid-range laptop with **integrated graphics only** (no dedicated GPU is ever required; all AI runs via OpenRouter), 1920×1080, latest Chrome, broadband. Latency targets exclude provider outages.

## 1. Cost & infrastructure policy (stakeholder constraints)

1. **Cheap above all.** Pick the cheapest acceptable option and always show the cost.
2. **OpenRouter API only (D-38).** Every AI call (LLM, decisions, images, music, and embeddings if used) goes through OpenRouter, with **no local models and no GPU**.
3. **Chinese models preferred:**

   | Role | Model |
   |---|---|
   | Main LLM | **DeepSeek V4.1 Flash** (`deepseek/deepseek-v4.1-flash`), **pinned to DeepSeek's own endpoint** with prompt caching (D-41) |
   | Decisions | **TypeSafe Jev 1.13** |
   | Images | **Qwen Image 3** or **Seedream 4.5**, chosen on *quality* by the Seed Asset Sprint (their real price gap is only ~4–10%) |
   | Music | **Lyria 3 Clip** (Google). The one non-Chinese exception: it is the only music model on OpenRouter |

4. **Lean generation mode is the default (D-40).** Standard is opt-in.
5. **Spending is gamified as character Energy (D-42).** Each character talks from its own ⚡ bar; a global daily cap is the safety net.

## 2. Non-functional requirements

### Performance
- **NFR-01 (first token):** In 1:1 chat, the first token appears within **2.0 s p50 / 4.0 s p90** of send. The "typing" state appears within **100 ms**.
- **NFR-02 (multi-agent pacing):** `turn.next` arrives within **500 ms** of the previous `turn.end`. The next speaker's first token arrives within **3 s p50**. The UI is never idle for more than 500 ms without an activity indicator. Openings generated in parallel are **revealed sequentially at speaking pace**.
- **NFR-03 (animation):** Idle animation, crossfades and VFX hold **60 fps**. Animate only `transform` and `opacity`. No main-thread task exceeds 50 ms while idle.
- **NFR-04 (emotion switch):** A sprite change **starts within 100 ms** of the `emotion` event and **completes within 300 ms**. All participants' sprites are preloaded on session open.
- **NFR-05 (asset budgets):** Sprites ≤ 250 KB (WebP/AVIF, ~768–1024 px tall). Theme loops ≤ 750 KB. ≤ 3 MB per character. The app shell is interactive within 3 s locally.
- **NFR-06 (generation feedback):** All generation runs as async jobs with per-task progress. First visual feedback arrives within 1 s. Each finished asset appears as soon as its task completes. Leaving the screen does not cancel the job.
- **NFR-29 (emotion at stream start):** The emotion is displayed within **800 ms of the first token (p90)**. Otherwise the previous emotion stays (with a "lean-in") and switches when the emotion arrives. The portrait is never blank.

### Cost guardrails
- **NFR-07 (caps):**
  - **Daily cap US$1.00:** covers all spend, including energy top-ups. It is the master safety net.
  - **Per-character creation cap US$0.60:** applies until `approvedAt`. After approval, image and song regenerations count against the daily cap.
  - Warning at 80%. Reaching a cap pauses with a clear prompt. **Spending never silently exceeds a cap.**
  - *There is no per-session cap.* Energy replaces it.
- **NFR-34 (energy):**
  - Each character has **1000 ⚡/day by default** (1 ⚡ = US$0.0001, so US$0.10), with a per-character override.
  - Energy regenerates linearly and is full again after ~24 h (computed lazily).
  - **Only the character's own replies drain it** (actual cost, rounded up).
  - At 0 the character is **Exhausted**: it can't reply, skips turns, and can be topped up after a confirmation, within the daily cap.
  - **Effective allowance:** ≈ **125–250 replies per character per day** (8 ⚡ at peak, 4 ⚡ off-peak, with caching).
- **NFR-08 (estimate before spend):** Every generation action shows an estimated cost first. The actual cost (`usage.cost`) is recorded in the ledger.
- **NFR-09 (cost visibility):** Spend today and to date by category, character and session, plus estimated vs actual. Energy spent per character.
- **NFR-30 (no hidden spend):** Nothing calls a paid API without a user action or an explicit pre-authorisation setting (e.g. "Auto-generate missing emotions", default **off**).
- **NFR-33 (provider routing):**
  - Committed config pins the main LLM to the **DeepSeek first-party endpoint**, with `require_parameters: true`.
  - Fallback goes only to **full-precision** providers (no fp4/fp8).
  - A data-collection policy is set: `allow` for the main LLM, so the DeepSeek first-party endpoint stays eligible (D-80).
  - The ledger records `provider` and `pricePeriod`.
- **NFR-35 (cache-friendly prompts):** Prompt layout puts static content first (style/persona), then history, with dynamic blocks (memory, retrieval) **last**, to maximise cache hits. The cache-hit % appears in Insight. *Note (AI stage): each character's memory list is frozen for a sitting and sits in the cached system prompt, refreshed only by a Forget or a live commit ([docs/ai/09](../ai/09-memory.md) M8).*

### Setup, key handling, privacy
- **NFR-10 (zero-config):** clone → install → copy `.env.example` → **one command** starts backend and frontend. Prerequisites are **Python + Node only**: no Docker, Redis, external DB, GPU, CUDA or PyTorch. Demo mode is reachable within **≤ 5 min**, and the first live chat within ≤ 10 min.
- **NFR-11 (demo mode):** Without a key, seed worlds, characters, assets and recorded sessions are browsable and replayable. Generation and live chat are disabled with a clear call to action.
- **NFR-12 (key storage):** The OpenRouter key lives **only on the backend** (`.env` or a git-ignored local settings file). The frontend only ever sees `missing/set/invalid`. The key never appears in logs, errors, the ledger or exports.
- **NFR-13 (network exposure):** The backend binds to `127.0.0.1`. The only outbound calls go to OpenRouter. **No telemetry. No runtime font or CDN calls** (fonts are self-hosted). *One documented exception: LangSmith tracing, off by default and switched on only by `HORIZON_LANGSMITH=1` plus the user's own key; it then sends chat and document text to LangSmith ([docs/ai/02](../ai/02-evaluation-observability.md) B11).*
- **NFR-14 (configurable models):** Model IDs, routing preferences and the pricing table live in config. Local overrides are git-ignored. `~latest` aliases are never used in committed config.

### Accessibility & UX safety
- **NFR-15 (reduced motion):** Defaults to the OS setting. When on, transitions become fades, and parallax, shake and flashes are disabled.
- **NFR-16 (photosensitivity):** At most **3 flashes per second**, with configurable flash intensity. Hover never triggers full-screen effects.
- **NFR-17 (audio):** No audio before the first user gesture. Master, music and SFX volumes and mutes, persisted. **Crossfade ≤ 2 s.** One music track at a time. Loudness is matched with a per-track `gainDb` measured once and applied client-side (no runtime transcoding). Loop points are optional; the default is a whole-track loop with a 1 s crossfade.
- **NFR-18 (readability):** WCAG AA contrast for all text under every palette. **Text on brand or signal tapes is always ink** (`ink-900`). Core flows are keyboard-operable.

### Reliability & data
- **NFR-19 (resumable jobs):** Jobs survive a backend restart. Completed assets are never lost when a sibling task fails. Retries are idempotent, max 3 per task.
- **NFR-20 (stop and interrupt):** Any stream can be stopped, or any session paused, within **500 ms**. Partial messages are kept as `interrupted`.
- **NFR-21 (local storage):** One SQLite file + an assets folder under `data/`. Backup means copying the folder. Migrations are versioned.
- **NFR-22 (git hygiene):** `data/`, `.env`, local settings and `private/` are git-ignored. Seed data lives under `seed/`, is imported into `data/` on first run, and can be reset.
- **NFR-23 (world isolation):** No API, memory or retrieval call returns another world's data, verified by automated tests.
- **NFR-31 (one live stream):** Only one session streams at a time in the MVP. Starting another prompts to pause the current one.

### Open-source hygiene & content
- **NFR-24 (asset provenance & licence):** Every committed AI asset has a provenance record (provider, model, date, prompt, technique). `ASSETS.md` states:
  - the code licence (**MIT**);
  - the generated-asset terms and any watermarks (e.g. SynthID on Lyria);
  - credits for free-library audio and fonts.

  Prompts and the README never name copyrighted IPs as style targets.
- **NFR-25 (seed budget):** 2 worlds, 6 characters, ≤ 40 MB of seed assets, no Git LFS.
- **NFR-26 (browser support):** Latest two versions of desktop Chrome, Edge and Firefox. Minimum viewport 1280×720. Safari is best-effort. No mobile.
- **NFR-27 (content floor):** **All characters are adults:** profile `age` is an integer ≥ 18, there is no minor age band, and image prompts always carry the adult-appearance clause. Until the AI team designs the rating and safety system (OQ-AI-08), the interim default is **SFW**.
- **NFR-28 (SME disclaimer):** Sessions with `advisory` characters show "AI simulation · not professional advice".
- **NFR-32 (marketing separation):** Launch and marketing material lives in the git-ignored `private/` folder, never in the public repo.

## 3. Risk register

Likelihood (L) and Impact (I) are rated H / M / L.

| ID | Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|---|
| R-01 | **A character's face drifts across emotion images** | H | H | Locked base portrait → reference edit or expression sheet; the **Seed Asset Sprint spike** decides; per-slot "Doesn't look like them"; fallback to neutral + VFX | AI, UI |
| R-02 | Art style drifts across characters | M | H | Versioned StylePreset on every call (Qwen allows ≤ 3 style refs + base); no IP named | AI |
| R-03 | Image cost runs away on the user's own key | M | H | Lean default, estimates, creation cap, daily cap, ledger, warning after 3 rerolls of one asset | SWE, AI |
| R-04 | Generation is slow (10–40 s per image) | H | M | Async jobs, progressive reveal, can leave and return; realistic mock timings | UI, SWE |
| R-05 | Music provider churn (Lyria is in Preview; MiniMax closed its API) | M | H | Provider interface; song optional; free ambient-bed fallback; seed songs committed with provenance | AI, SWE |
| R-06 | IP or likeness issues | M | H | Generic style descriptor; guardrail against named characters or real people; original seed cast | AI |
| R-07 | Content safety / youthful-looking characters | M | H | Adult floor (NFR-27), adult-appearance clause, Rin revised to 22; full design by AI team | AI, Lead BA |
| R-08 | Multi-agent latency and cost | H | M | Stream every turn; announce the next speaker early; cast ≤ 4 default; responders ≤ 2; turn caps; **energy per character**; rolling summaries | AI, SWE |
| R-09 | Streaming vs emotion timing | M | M | Separate `emotion` event; NFR-29 hold-then-late-switch; tags stripped server-side | AI, SWE, UI |
| R-10 | Browser autoplay blocks music | H | L | Title-screen gesture unlocks audio; "Enable audio" chip | UI |
| R-11 | Repo bloat | M | M | Asset budgets, WebP/Opus, no LFS, runtime data git-ignored | SWE |
| R-12 | API key leak | M | H | Backend-only key, `.env.example`, localhost bind, never logged, pre-commit secret scan | SWE |
| R-13 | Jev is immature (alpha endpoint, varying probabilities, price unconfirmed in the models API) | M | M | `Decider` interface with a deterministic code fallback per question ([docs/ai/01](../ai/01-agent-architecture.md) A4); probability bands; confirm price and billing via `usage.cost` ([docs/ai/13](../ai/13-wrap-up.md) W6, A1) | AI |
| R-14 | DeepSeek V4.1 Flash is very new (2026-09-10); persona quality unproven | M | M | Persona-adherence evaluation ([docs/ai/02](../ai/02-evaluation-observability.md) B1, B4); reasoning off for chat; no fallback model: if V4.1 ever fails the eval, a developer changes the pinned model and re-runs it ([docs/ai/03](../ai/03-llm-parameters.md) C8) | AI |
| R-15 | Mock and backend drift apart | H | M | Doc 05 is the contract; shared fixtures under `seed/`; schema validation | UI, SWE |
| R-16 | Scope creep | H | M | Phasing (doc 01 §4.3), constrained mode definitions, MoSCoW | Lead BA |
| R-17 | Animation performance / photosensitivity | M | M | transform/opacity only, flash cap, reduced motion, no hover floods | UI |
| R-18 | Generation fails partway | H | M | Per-task status, idempotent retries, typed error codes, resume after restart | SWE |
| R-19 | Memory design arrives last although the AI is "the star" | M | H | Memory design spike runs in parallel with UI/UX; the UI reserves Memory tab + Insight surfaces | AI, Lead BA |
| R-20 | Expert-panel credibility | M | M | SME disclaimer; verdict assesses argument quality, not truth; RAG in v1.1 | UI, AI |
| R-21 | Cheap image models weaker at reference editing | M | M | The spike tests 2 models × 2 techniques; premium opt-in fallback | AI |
| R-22 | **Provider variance** on OpenRouter (~30 endpoints, 12× price spread, fp4 quantization, ignored parameters) | H | M | NFR-33: pin first-party, `require_parameters`, full-precision fallback only | AI, SWE |
| R-23 | **Peak-hour 2× pricing** on DeepSeek first-party (Mon–Fri 09–12 and 14–18 MYT) | H | L | Energy drains at the real cost (users *see* a "rush hour" chip); caps sized on peak; seed/eval batch jobs run off-peak | SWE, UI |
| R-24 | **No transparent output** from default image models | H | M | Framed card / soft radial mask is the primary design (D-45); cut-out is out of scope | UI |
| R-25 | Runtime audio processing vs zero-config | M | L | Optional loop points; `gainDb` measured with pure-Python libraries; seed audio processed offline | SWE |
| R-26 | Energy confuses users ("why won't she talk?") | M | M | Clear Exhausted state with Zzz + "back in 3 h" + one-click top-up; energy explained in onboarding; skipped speakers labelled in multi modes | UI |

## 4. Verified facts used in planning (live checks, 2026-10-01)

| # | Fact | Source | Note |
|---|---|---|---|
| F1 | **Jev** (`typesafe/jev-1.13`): typed decisions with probabilities, **no free text**; separate Decisions API (alpha); ~$0.042/M input, free output; 32K state budget | [OpenRouter Jev guide](https://openrouter.ai/docs/guides/community/jev), [OpenRouter blog](https://openrouter.ai/blog/insights/what-is-jev/) | Price not visible in the models API; confirm via `usage.cost` |
| F2 | **DeepSeek V4.1 Flash** = `deepseek/deepseek-v4.1-flash` (released 2026-09-10; 1M context; streaming, tools, `response_format`, reasoning). Served by ~30 providers on OpenRouter ($0.024–0.60/M in, $0.40–2.40/M out; some fp4/fp8) | [OpenRouter model page](https://openrouter.ai/deepseek/deepseek-v4.1-flash), [endpoints API](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints) | Stakeholder-confirmed model |
| F3 | **DeepSeek first-party:** $0.15 in / $0.60 out / **$0.003 cache read** off-peak; **×2 at peak** (Mon–Fri 01–04 and 06–10 UTC = **09–12 and 14–18 MYT**). The only endpoint with implicit caching | [Endpoints API](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints), [OrcaRouter summary](https://www.orcarouter.ai/blog/deepseek-v4-1-flash-openrouter) | Basis of D-41 |
| F4 | OpenRouter default routing is price-weighted; `require_parameters` defaults to false; sticky caching only when cache reads are cheaper | [Provider routing](https://openrouter.ai/docs/features/provider-routing), [Prompt caching](https://openrouter.ai/docs/features/prompt-caching) | Hence NFR-33 |
| F5 | `:batch` variant: DeepInfra only, ~20% below its list price, unreliable at check time | Endpoints API (`:batch`) | **Not used** |
| F6 | **Qwen Image 3:** $0.03 per output image + **$0.003 per input reference**; ≤ 4 references; 3:4; `seed`; **no transparency** | [Qwen Image 3](https://openrouter.ai/qwen/qwen-image-3) | |
| F7 | **Seedream 4.5:** $0.04 per output image; references **free** (≤ 14); `seed`; **no transparency** | [Image models collection](https://openrouter.ai/collections/image-models) | |
| F8 | OpenRouter Unified Image API supports reference images (`input_references`) | [OpenRouter announcement](https://openrouter.ai/blog/announcements/image-api/) | Enables "base → edit" with one key |
| F9 | **Lyria 3 Clip** (30 s, ~$0.04) and **Lyria 3 Pro** (~$0.08) on OpenRouter, Preview; no Chinese music model on OpenRouter | [Lyria 3 Clip](https://openrouter.ai/google/lyria-3-clip-preview) | Price not visible in the API; confirm via `usage.cost` on the first sprint call. Read Google's licence terms |
| F10 | MiniMax closed its paid music APIs to new users (2026-08-20) | [teamday.ai](https://www.teamday.ai/blog/best-ai-music-models-2026) | Provider churn risk |
| F11 | AutoGen has been in maintenance mode since Oct 2025 | [LangChain comparison](https://www.langchain.com/resources/langchain-vs-autogen) | Supports LangGraph-only |
| F12 | Browsers block audio autoplay before a user gesture | [Chrome autoplay policy](https://developer.chrome.com/blog/autoplay) | Title screen solves it |

## 5. Cost model (planning-grade; replace with measured `usage.cost` after the spike)

### 5.1 Per character creation

| Line item | **Lean (default)** | Standard | Expression-sheet variant (if the spike picks it) |
|---|---|---|---|
| Profile + palette pick + appearance + song brief (DeepSeek) | ~$0.002 | ~$0.002 | ~$0.002 |
| Portrait candidates | 1 | 2 | 2 |
| Emotions up front | 3 (+ neutral = base) | 6 + blink | 1–2 sheets + blink |
| Images incl. reference fees, × 1.3 rerolls | ~$0.18–0.21 | ~$0.39–0.47 | ~$0.15–0.22 |
| Theme song (Lyria 3 Clip, 1 try) | ~$0.04 | ~$0.04 | ~$0.04 |
| **Total per character** | **≈ $0.22–0.25 (≈ RM1)** | **≈ $0.44–0.51 (≈ RM2)** | **≈ $0.19–0.27** |

*Range: Qwen Image 3 (with base + style references) to Seedream 4.5. MYR at ~4.5/USD. In Lean mode, each of the 3 deferred emotions costs ≈ $0.033–0.04 when generated on demand.*

### 5.2 Per reply (DeepSeek V4.1 Flash, first-party, 6.5K in / 300 out)

| Scenario | Cost per reply | ⚡ | Replies per 1000 ⚡ |
|---|---|---|---|
| Off-peak, 80% cache hit (**typical**) | ≈ $0.00039 | 4 | ~250 |
| Peak, 80% cache hit | ≈ $0.00078 | 8 | ~125 |
| Off-peak, no cache (cold start) | ≈ $0.00116 | 12 | ~85 |
| Peak, no cache (worst case) | ≈ $0.00231 | 24 | ~42 |

**Output tokens dominate once input is cached**, so **per-mode reply-length limits** are the most reliable chat lever.

### 5.3 Multi-character (each speaker's reply drains *their own* energy)

| Scenario | Off-peak, cached | Peak, no cache (worst) |
|---|---|---|
| Group turn (2 responders + routing) | ≈ $0.0009 | ≈ $0.0055 |
| Debate, 3 debaters, Standard, moderator = You | ≈ $0.007 | ≈ $0.027 |
| Debate, 5 debaters + auto host | ≈ $0.018 | ≈ $0.070 |
| Watch, 20 turns | ≈ $0.014 | ≈ $0.060 |

Jev routing and reactions add ≈ $0.0001 per turn (daily cap, not energy).

### 5.4 What a day costs (illustrative)
A heavy user chatting with 3 characters, using about half of each energy bar, spends ≈ **US$0.15/day**. A full day at every bar's limit is ≈ $0.10 × (number of active characters). The **daily cap of US$1.00** is the hard ceiling.

### 5.5 Cost levers (ranked)
1. **Expression sheet** (one image for all emotions), if the spike shows acceptable quality: ~2× cheaper emotions.
2. **Pinned first-party endpoint + cache-friendly prompt layout** (NFR-33/35): ~3× cheaper input.
3. **Reply-length limits per mode** (output is 45–90% of each cached turn's cost).
4. **Lean mode default** (D-40).
5. **Energy per character** (D-42) bounds daily spend per character.
6. Use one shared style-reference set (each Qwen reference costs $0.003).
7. Cache and content-hash assets; never regenerate unchanged ones.
8. Jev for cheap decisions (routing, emotion, guardrails).
9. Rolling summaries / bounded context in multi-agent modes.
10. Run seed and evaluation batch jobs **off-peak** (2× saving).
