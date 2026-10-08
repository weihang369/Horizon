# 04: Gateway, Budget & Energy

> **v1.0.** This revision applies the review debate (Rounds 1–2, 2026-10-03).

## 1. The gateway (OQ-SWE-07): the only code that talks to the network

```
caller ──► gateway.<client>(request, ctx: CallContext)
            1. preflight   caps check incl. in-flight RESERVATIONS → reserve(estimate)      (raise before any spend)
            2. request     httpx, pinned routing, per-purpose timeout, ≤ 1 retry only when nothing was charged
            3. record      ledger row: actual usage.cost, or estimate + generation_id → corrected later
            4. settle      release reservation; drain energy iff ctx.purpose == 'reply'
            5. emit        energy / budget.warning / budget.reached; gateway.on_call hook (no-op until the AI stage)
            errors → ErrorCode; the key is redacted everywhere
```

```python
CallContext = { category, purpose, world_id, character_id?, session_id?, job_id?, message_id?, creation: bool }
# Built ONLY by the actor or job worker via turn_ctx.call_ctx(purpose) / job_ctx.call_ctx(purpose), so AI code can't mislabel
# a call. There is no drains_energy flag to set: draining is derived from purpose == 'reply'.
```

| Client | Endpoint (OpenRouter) | API |
|---|---|---|
| `chat` | `POST /api/v1/chat/completions` | `stream(req: ChatRequest, ctx) → AsyncIterator[ChatChunk]` · `complete(req, ctx) → ChatResult` |
| `decisions` | `POST /api/alpha/decisions` (Jev, alpha) | `decide(state, questions, ctx, timeout_ms) → DecisionsResponse` (only the `Decider` calls it) |
| `images` | `POST /api/v1/images` | `generate(prompt, refs: list[DataURL], resolution, aspect_ratio, seed?, ctx) → ImageResult`. Body (the shape the D-61 run proved, M4): `model`, `prompt`, `n: 1`, `aspect_ratio`, `resolution`, and references as `input_references: [{type: "image_url", image_url: {url}}]` with data URLs; the image comes back in `data[0].b64_json`, the cost in `usage.cost` |
| `embeddings` | `POST /api/v1/embeddings` | `embed_batch(texts ≤ 32, ctx, model, dimensions, hooks)` (pinned provider; one paid call and one row per batch). The model and dimensions come from the **active embedding space**, not `models.embedding` (D-95); `simulated_embedding_batch` is the scripted twin (D-81) |
| `music` | `POST /api/v1/chat/completions`, streamed, model `google/lyria-3-clip-preview` (D-87; the bare `google/lyria-3-clip` was a 404 in M2) | `generate(model, prompt) → MusicResult` (creation-followups design D1). Body: `model`, `messages`, `modalities: ["text","audio"]`, `stream: true`, `usage.include`; **no** main-LLM routing block and **no** fallback model. The clip is the joined base64 `choices[0].delta.audio.data` pieces (an MP3), the cost `usage.cost` ($0.04 per 30 s clip). When Lyria can't make the song (provider error, timeout, refusal, rate limit, unusable audio) the task falls back to the free procedural theme; key, credit and cap failures still fail the task (design D7). The scripted profile keeps the procedural theme ($0, D-83) |
| `meta` | `GET /api/v1/key`, `/api/v1/credits`, `/api/v1/generation?id=` (verified in M2) | `testConnection`, credits display, cost correction. Free; no ledger |

```python
ChatRequest = { model, messages, max_tokens, temperature?, reasoning?, response_format?, tools?, tool_choice?,
                logprobs?, top_logprobs?, stop?, extra? }
ChatChunk   = { generation_id (required; taken from the first chunk), content?, reasoning?, tool_call?, logprobs?,
                finish_reason?, usage? }
```

**Routing for the main LLM (NFR-33, D-41):**

```json
{ "provider": { "order": ["DeepSeek"], "require_parameters": true, "allow_fallbacks": true,
                "quantizations": ["bf16", "fp16", "fp32", "unknown"], "data_collection": "allow" },
  "usage": { "include": true } }
```

- Model IDs are pinned in config. The fallback model is `deepseek/deepseek-v4-flash`.
- **`data_collection: "allow"` (D-80).** DeepSeek's first-party endpoint may train on inputs, so under `deny` OpenRouter removes it and routes to the cheapest third party. The user's OpenRouter privacy settings must also allow paid endpoints that may train on inputs; otherwise OpenRouter's guardrail still removes DeepSeek (verified in the M2 live run).
- **If the provider that served the call isn't DeepSeek, a warning goes into the trace.** `require_parameters` can route a call away from the first-party endpoint when a parameter such as `logprobs` isn't supported there (verify in M2), which loses caching and breaks the price assumptions.

**Timeouts.**

| Calls | Timeout |
|---|---|
| Chat time to first token | 20 s |
| Images | 180 s |
| Music: first audio chunk (then the chat idle timeout between chunks) | 120 s |
| Embeddings | 30 s |
| **Decisions, per purpose** (config, defaults below) | |
| `route` | 400 ms |
| `gate` + input guardrail (batched) | 500 ms |
| `rerank` | 600 ms |
| `emotion` pre-prediction | 300 ms |
| Off the hot path | 3 s |

The fallbacks live in the `Decider` (doc 05 §3).

**Error mapping.**

| OpenRouter / transport | ErrorCode |
|---|---|
| 401 | `invalid_key` (also flips `openRouterKeyStatus` to `invalid`) |
| 402 | `insufficient_credits` |
| 403 moderation, or a refusal finish reason | `content_refused` |
| 429 | `rate_limited` + `retryAfterSec` |
| 408, or our own timeout | `timeout` |
| 5xx, or a malformed response | `provider_error` |
| An error chunk in the middle of a stream | `provider_error`; the partial text is kept and the message status is `error` |

**Retries** happen only when nothing can have been charged: a connection failure before any response, or 429/5xx with no body. A paid call that succeeded but whose body was lost is **not** retried automatically (that's the paying-twice rule).

## 2. Ledger

- **One row per paid call.** `category` is the contract enum; **`purpose`** is the internal detail (`reply`, `route`, `gate`, `rerank`, `guardrail`, `reaction`, `emotion`, `importance`, `query_embed`, `host`, `verdict`, `summary`, `profile`, `image_*`, `song`, `embed_doc`…).
- **`cost_source = 'provider'`** when `usage.cost` arrives.
- **A cancelled or broken call** that may have been charged (a stopped stream, a Jev or embedding request cancelled after it was sent) is recorded with **the estimate** (`cost_source = 'estimate'`) plus its `generation_id`. A background task then looks up `GET /generation?id=` with backoff, corrects the row **once**, and emits `energy` if it drained.
- `estimated_cost_usd` is always recorded, so the Usage screen shows estimated vs actual (NFR-09). The row also records `price_period`, `provider`, `tokens_cached`, `latency_ms` and `counts_to_creation_cap`.
- **`Message.usage`** = the ledger rows with `message_id = X AND purpose = 'reply'`, plus the actor's timings.
  - `firstTokenMs` is measured **from the turn's trigger**: receiving `send` for the first responder, the previous `turn.end` for later speakers.
- **`TurnTrace.calls[]`** (rev 1.3) lists every row for that `message_id`. The `messageId` is allocated **before** the first pre-generation call.

## 3. Caps (NFR-07, NFR-30) and reservations

The gateway keeps an in-memory **reservation book** (`gateway/reservations.py`).

| Check (preflight) | Rule | On failure |
|---|---|---|
| **Daily cap** | `spentToday + reserved + estimate ≤ dailyCapUsd`, for **every** paid call | 402 `daily_budget_exceeded`; live sessions pause with `daily_budget`; `budget.reached` |
| **Creation cap** | While the character isn't approved: `creationSpent + reservedFor(character) + estimate ≤ perCharacterCreationCapUsd` | 402 `creation_budget_exceeded` |
| **Warning** | Emitted **on crossing**: `before < warnAt ≤ after`, for the daily scope or a character's creation scope. No stored flag is needed | `budget.warning` |

- **Reserving.** Preflight reserves the estimate, and settling releases it. `jobs.start` reserves the **whole remaining job estimate** and releases it task by task. Prefetched openings and hot-path Jev and embedding calls reserve too.
- **The overrun bound.** A cap can be exceeded only by **Σ(actual − estimate)** of the calls in flight at that moment, which is small because estimates are upper-bound-ish. A reply is never cut mid-sentence. Every later call is blocked, and the overrun is recorded and shown. Spending never *silently* exceeds a cap.
- **No hidden spend (NFR-30).**
  - Every paid call comes from a user action or an explicit pre-authorising setting (`autoGenerateMissingEmotions`).
  - Seed knowledge is embedded only through the explicit **"Index seed knowledge"** action offered after `setKey` (< $0.001).
  - Background re-embedding of `keyword_only` sources covers **user-added** sources only.

### Estimates (`domain/pricing.py`, table in `seed/pricing.json`)

| Category | Estimate |
|---|---|
| chat | Counted from the **actual assembled request**: `stable_prefix_tokens × (p_cached if the prefix is warm else p_in) + other_in × p_in + expected_out × p_out`, × the peak multiplier at peak. `expected_out` = `min(max_tokens, p75 of this character's last 10 replies, default 220)` |
| decision | `(state + questions) tokens × $0.042/M` (output free). The 32K Jev budget is checked before sending |
| image | `pricing.generation.*` (Seedream 5.0 Flash ≈ $0.018/image) |
| embedding | `tokens × p_embed` (Qwen3 Embedding 8B $0.01/M) |
| music | `pricing.generation.song` |

**Peak pricing (R-23, ENG-06).** The DeepSeek first-party peak runs Mon–Fri 09:00–12:00 and 14:00–18:00 MYT, at ×2 (config). The `Clock` derives `AppSettings.pricing`. Actual costs always come from `usage.cost`.

## 4. Energy (D-42, NFR-34, OQ-SWE-13)

These are pure functions in `domain/energy.py`, the **same algorithm as `frontend/src/domain/energy.ts`** (including its `ceil(x − 1e-9)` epsilon). Both are tested against **one shared JSON fixture file**, and both are fixed together if they ever diverge.

```
EST_REPLY_POINTS = { off_peak: 4, peak: 8 }          # config; exposed as AppSettings.energy.estReplyPoints (rev 1.3)
regen(e, now):     if e.current >= e.max: current = e.current              # top-ups may exceed max; regen never lowers it
                   else current = min(e.max, e.current + (e.max/24) * hours(now - e.as_of))     # REAL, no flooring
day_roll(e, today): if e.energy_day != today: spent_today = 0; energy_day = today
drain(e, cost):    points = ceil(cost / usdPerPoint - 1e-9); current = max(0, regen(e).current - points)
                   spent_today += points; as_of = now                       # overdraft clamps at 0; the reply finishes
state:             exhausted if current < EST_REPLY_POINTS[period]          # ONE threshold for UI state AND the gate
                   tired     if current < 0.2 * max
                   active    otherwise
wire:              current, spentToday floored to integers; fullAt = now + (max - current)/(max/24) h (omitted when full)
```

- **One threshold.** A character the UI shows as awake is never refused. The *budget* preflight (§3) uses the real request estimate. The *energy* gate uses the fixed `EST_REPLY_POINTS[period]`.
- **Drain is the real cost**, so an expensive reply just makes the character tired sooner. That's visible in `TurnTrace.energy` and `context.used.knowledge`, never a surprise refusal.
- **Only a character's own reply drains its energy** (`purpose == 'reply'`), and that includes **discarded prefetched openings** (D-77). Everything else goes to the daily cap only: routing, Jev, reactions, host, verdict, memory, embeddings, images, songs.
- **Demo mode (ENG-07):** with no key, energy is returned **frozen as stored**: no regen and no drain.
- **Top-up (D-76).**
  - **Gate:** `spentToday + (todayTopUpPoints + points) × usdPerPoint ≤ dailyCapUsd`, where `todayTopUpPoints` is the sum of today's top-ups.
  - The ledger row is `category: energy_topup`, with `energy_points = points` and **`cost_usd = 0`**. A top-up authorises spend, and the replies it enables are recorded as `chat` when they happen, so nothing is counted twice; the gate still bounds repeated top-ups.
  - The MockClient and the ENG-05 wording are updated to match (M1a).
- **Exhaustion:** the speaker is skipped (`turn.next.skipped`, `TurnTrace.routing.skipped`), or in 1:1 a `system_note` "Hana is asleep (⚡ 0)" plus an `error` event with `energy_exhausted`. This is an async event, never a pre-202 rejection.
- **Day boundary:** local midnight in `HORIZON_TZ`. **Concurrency:** a per-character lock, and the drain is one `UPDATE` inside the ledger's writer transaction.
- **Stakeholder note.** Knowledge-heavy replies (uncached parent passages) can cost 13–26 ⚡, which breaks NFR-34's "125–250 replies/day" assumption for knowledge-heavy chats. The mitigations are `ai.knowledge.maxTokens` (default 1,500 tokens) and caching-friendly prompts (NFR-35) at the AI stage. Neither the gate nor the drain rule changes.

## 5. Secrets hygiene (NFR-12, OQ-SWE-12)

- The key comes from env/.env or `data/secrets.local.json`, is held as a `SecretStr`, and is only ever placed in the `Authorization` header by `gateway/client.py`.
- **Redaction:**
  - A logging filter, the exception formatter, the ledger writer and the `on_call` hook all redact `sk-or-[A-Za-z0-9_-]{10,}` → `sk-or-***`.
  - Tests assert that the key never appears in logs, errors, the ledger, exports or SSE.
- The backend binds to `127.0.0.1` only. `.env.example` is committed with blanks. A gitleaks pre-commit hook is recommended in the README.
