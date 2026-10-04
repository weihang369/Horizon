# Design: gateway-ledger-energy (M2)

## Context

See proposal.md (Why). This is the state M1b left behind that shapes the approach:

- **Key.** `config.py` deliberately never reads `OPENROUTER_API_KEY`. `services/settings.py` hard-codes `openRouterKeyStatus: "missing"` and `demoMode: true`. `services/reads.py` already takes a `demo_mode` flag for energy reads, but it is always true.
- **Storage.**
  - `usage_records` already has every M2 column: `purpose`, `cost_source`, `estimated_cost_usd`, `generation_id`, `price_period`, `provider`, `tokens_cached`, `latency_ms`, `counts_to_creation_cap`, `energy_points`.
  - `characters.energy_current` and `energy_spent_today` are `Float` (SQLite REAL).
  - **No migration is needed.**
- **Writes.** All writes go through `Database.write()`: one global `asyncio.Lock` plus `BEGIN IMMEDIATE`. The unit of work publishes events after commit.
- **Energy maths.** `domain/energy.py` already ports `energy.ts`: `settle`, `drain`, `top_up`, `can_top_up`, `read_energy`. It has no `with_max` yet. The shared fixtures already cover drain, top-up, day roll and gate cases.
- **Clock.** `domain/clock.py` already computes the pricing period and `next_change_at` from `HORIZON_TZ`. `FrozenClock.sleep()` **advances virtual time**.
- **Redaction.** `logs.py` redacts `sk-or-[A-Za-z0-9_-]+` → `sk-or-[REDACTED]`. Doc 04 §5 says `sk-or-***` with `{10,}`.
- **Contract.**
  - `openRouterKeyStatus` is `"missing" | "set" | "invalid"`. There is no `valid`/`none` value, and the contract wins over the M2 prompt's wording.
  - `ConnectionResult` and `ModelTestResult` are `ok: true` only, so failures are rejections.
  - The session `energy` event is a stored session event: M3, through the actor.
- **Frontend.**
  - The MockClient `setKey` returns `invalid` immediately for `sk-or-bad*`.
  - `settings.update` silently drops `estReplyPoints`.
  - `topUpEnergy` needs a key (`live()`), and `setEnergyMax` doesn't.
  - The UI already blocks non-`sk-or-` keys before calling `setKey`, and patches only editable fields and `modelOverrides`.
- **HTTP transport.** `transport.ts` has no `put`. The HTTP harness declares `supports: "M1b"`, and its `setKey` rejects.

## Goals / Non-Goals

**Goals:**
- **One choke point for all spend.** Whatever M3–M5 add, every call is labelled, capped, recorded, and drained only when it is a reply.
- **Deterministic tests with zero network.** respx-recorded responses for unit and integration tests, plus an in-process fake provider for the test-mode backend that the TS HTTP suite drives.
- **Settings and energy writes work on the HttpClient**, and the four M2 portable tests run over HTTP.

**Non-Goals:**
- No product feature calls chat, images or embeddings in M2. Turns are M3, jobs M4, knowledge M5. M2 exercises them only at the gateway/service level and through the `testModel` probes.
- No session-stream `energy` events. Those are session writes, which belong to M3's actor. M2 publishes `entity.changed { kind: "character" }`.
- No music client (M4) and no prompt design.

## Decisions

### D1. Module layout (doc 01 §7)

| Module | Contents |
|---|---|
| `gateway/client.py` | `HttpCore`: the single `httpx.AsyncClient`. Builds the `Authorization` header per request from the `KeyStore` (the only place the key leaves its `SecretStr`), applies timeouts, and does the "nothing charged" retry |
| `gateway/context.py` | `CallContext` (frozen), plus `call_ctx(purpose, …)` factories for system calls; turn/job factories come with M3/M4. `drains` is a property: `purpose == "reply"` |
| `gateway/chat.py` · `decisions.py` · `images.py` · `embeddings.py` · `meta.py` | The thin per-endpoint clients: request building, response parsing → `ChatChunk`/`ChatResult`, `DecisionsResponse`, `ImageResult`, vectors, key/credits/generation |
| `gateway/pipeline.py` | `Gateway.paid(ctx, estimate, send)`: preflight → request → record → settle → emit, shared by every paid client |
| `gateway/reservations.py` | `ReservationBook` (in-memory) |
| `gateway/errors.py` | `ProviderError(code, message, retry_after, partial_text)` and the mapping table |
| `gateway/redact.py` | `KEY_RE`, `REDACTED`, `redact()`: the one helper |
| `gateway/fake.py` | `FakeOpenRouter`, an `httpx.MockTransport` handler for test mode |
| `domain/pricing.py` | Pure estimates (mypy strict) |
| `domain/budget.py` | Pure cap and warning predicates: `exceeds_daily`, `exceeds_creation`, `crossed(before, after, warn_at)` |
| `services/keys.py` | `KeyStore`: sources, secrets file and status |
| `services/ledger.py` | `LedgerWriter`: the row insert + reply drain in one writer transaction; read helpers `calls_for_message`, `reply_usage` for M3 |
| `services/energy_writes.py` | Top-up, set-max, per-character locks |
| `services/corrector.py` | `CostCorrector` |
| `ai/decider.py` | `Decider`, question/answer types, `DeciderFixtures`, `DecisionUnavailable` |
| API | Routes added to `api/routes.py` |

**Alternative:** fold the pipeline into each client. That was rejected, because the five steps must be identical for every paid call, and one place is easier to audit for NFR-30.

### D2. One HTTP client, transport chosen once
`HttpCore` owns one `httpx.AsyncClient(base_url="https://openrouter.ai/api", transport=…)`:
- **Normal runs** use the default transport.
- **`cfg.test_mode`** uses `httpx.MockTransport(FakeOpenRouter(...))`.
- **Unit tests** construct `HttpCore` with the default transport and mount `respx` on it.

There is one code path for request building, so the fake and respx both exercise the real client code.

**Alternatives rejected:** a `Protocol` with a fake gateway, because it would bypass the real request building and error mapping; and respx inside the running server, because respx is a test dependency and patches globally.

### D3. KeyStore and status

**Where the key comes from.**
- `config.py` gains `openrouter_key: SecretStr | None`. It reads `OPENROUTER_API_KEY` from env, then `.env`, and is **always `None` in test mode** (`openrouter-key` spec).
- `KeyStore.effective()` returns `(SecretStr, source)` from the config first, then `data/secrets.local.json` (`{"openRouterKey": "…"}`).
- The secrets file is written atomically: temp file in the same directory, then `os.replace`.

**Status.**
- Status is computed from the effective key plus an in-memory `rejected_fingerprint`: `sha256(key)[:16]`, set on any 401.
- `setKey`, factory reset and restart clear it.
- **A status change publishes `entity.changed { kind: "settings" }`.**

**`demoMode = status != "set"`** feeds:
- settings;
- `ReadContext.demo_mode` (energy frozen);
- the key guard (`missing_key` / `invalid_key`) for paid calls and for top-ups.

### D4. Redaction (resolves tension 2; see OQ-B)
One helper in `gateway/redact.py`:
- `KEY_RE = r"sk-or-[A-Za-z0-9_-]+"`, `REDACTED = "sk-or-***"`.
- It's used by:
  - `logs.py`, which imports it, replacing its own copy;
  - the exception formatter;
  - `api/errors.py`, which redacts `message` and the stringified `details` of every envelope;
  - `LedgerWriter`, which redacts the text columns `model`, `provider` and `generation_id` defensively;
  - the `on_call` hook payload;
  - `ProviderError` messages.

**Why `+` and not `{10,}`:** the key validator accepts any `sk-or-…` with one or more characters, and the test keys are short (`sk-or-good`). A minimum-length redactor would leave a gap where an accepted key is not redacted.

**Why `sk-or-***`:** doc 04 is the source of truth, and the M1b spec only promises "a redaction marker".

### D5. Paid-call pipeline and atomic preflight
```
Gateway.paid(ctx, est, send):
  require_key()                                   # missing_key / invalid_key, before anything
  async with book.lock:                           # check-and-reserve is atomic (the SUM read is awaited inside)
      spent = await ledger.spent_today(); creation = await ledger.creation_spent(ch) if ctx.creation
      refuse → publish budget.reached; raise 402  # no reservation made, nothing sent
      hold = book.reserve(ctx, est)
  try:
      outcome = await send()                      # client-specific; may raise ProviderError
      before/after = await ledger.record(row(outcome), drain=ctx.drains)   # writer tx; drain inside
  except Cancelled/broken-after-send:
      await shield(ledger.record(estimate_row(ctx, est, generation_id)))  # cost_source='estimate'
      corrector.enqueue(row_id) if generation_id
      raise
  finally:
      book.release(hold)                          # AFTER the row commits: spend is never counted 0 times
  emit: crossed(before, after) → budget.warning; entity.changed(character) if drained; on_call(ctx, summary, outcome)
```
- **Release after record**, so the window where a call is neither reserved nor spent is zero. During that instant it may be counted twice, which errs safe.
- **`asyncio.shield`** keeps a stop or cancel from aborting the ledger write. NFR-30: spend is never lost.
- **`budget.reached` scope:** `daily` or `creation`, with `sessionId`/`jobId` from ctx.
- **Overrun bound:** with the atomic check-and-reserve, only the calls already holding reservations can exceed. That's Σ(actual − estimate), which the concurrent-preflight test asserts.

### D6. Routing, timeouts and retries
- **Routing.**
  - The chat request body always merges the pinned `provider`/`usage` block from config (D9).
  - The model is `modelOverrides.chat ?? models.chat`.
  - `ChatResult.provider_warning` is set when the response's `provider` isn't `DeepSeek`.
- **Timeouts.**
  - The chat time-to-first-token timeout wraps the wait for the first chunk only. After that, an idle timeout of 30 s between chunks applies.
  - Decision timeouts come from config per purpose (D9). Images, embeddings and meta use per-request `httpx.Timeout`.
- **Retry** happens only on:
  - `httpx.ConnectError` / `ConnectTimeout`, which come before the request is sent;
  - a 429/5xx whose body is empty.

  It is never retried after the request bytes were written and the read failed (`ReadError`, `RemoteProtocolError` mid-response). Those become an estimate row.

### D7. Ledger and correction
- `LedgerWriter.record(row, drain)` runs inside `db.write()`. When `drain` is set, it takes the per-character lock **before** entering the writer (lock order: character → writer; never the reverse). It then:
  - inserts the row;
  - reads the character's stored energy;
  - computes `domain.energy.drain` with `points_for_cost(cost)`;
  - writes `energy_current` / `energy_spent_today` / `energy_as_of`.

  It returns `(spent_before, spent_after)` for warning detection.
- **Day roll uses `HORIZON_TZ`.** The services pass the offset from `clock.calendar` into `settle`/`day_roll`. The fixtures keep their fixed +08:00 file-level offset.
- **`CostCorrector`:**
  - One worker task with an `asyncio.Queue`, started in `Runtime.start()` after the DB is ready and cancelled in `stop()`.
  - On start it scans for `cost_source='estimate' AND generation_id IS NOT NULL AND at ≥ now − 24h`.
  - It calls `meta.generation(id)` with backoff 2 s → 5 s → 15 s → 60 s → 5 min (repeated), giving up at 24 h of row age.
  - The update is `UPDATE … SET cost_usd=?, cost_source='provider', tokens…, provider=? WHERE id=? AND cost_source='estimate'`. A rowcount of 1 guarantees "exactly once".
  - For `purpose='reply'`, the energy delta is `points(actual) − points(estimate)`, applied in the same transaction under the character lock and followed by `entity.changed`. A positive delta drains with the normal `drain` rule (clamped at 0). A negative delta refunds: `current += |delta|` and `spentToday −= |delta|`, floored at 0.
  - Backoff uses an **injected sleeper** (default `asyncio.sleep`), **not `clock.sleep`**. `FrozenClock.sleep` advances shared virtual time, and a background task must never move the test clock (OQ-J).
- **No migration.** The startup scan has no index on `cost_source`. The table is small and the scan runs once, so we accept it. If it grows, a partial index can come in a later migration.

### D8. Energy writes
- **Locks.** `EnergyLocks` is a `dict[str, asyncio.Lock]` created lazily. It isn't pruned, because the number of characters is small.
- **Top-up.** Key guard → character lock → writer transaction:
  1. `spentToday` = the ledger sum for `local_day`;
  2. `todayTopUpPoints` = the sum of `energy_points` where `category = 'energy_topup' AND local_day = today`;
  3. `can_top_up` (D-76) with `dailyCapUsd` and `usdPerPoint` from the merged settings;
  4. settle + top-up;
  5. UPDATE the character;
  6. INSERT the `energy_topup` row (`cost_usd 0`, `cost_source 'provider'`).

  It then publishes `entity.changed { kind: "character", id, worldId }`. A refusal raises 402 `daily_budget_exceeded` with `details: { todayTopUpPoints, points }` (mock parity).
- **Set-max.** No key required. It adds `domain.energy.with_max`, ported from `withMax`, and new fixture cases (`fn: "withMax"`) that the TS fixture runner also executes. In demo mode `settle` is called `frozen`, so no regeneration happens.
- **Bodies.** Both routes take `{ points: int > 0 }`. Anything else is `validation`.

### D9. Config for routing, timeouts and peak (`seed/pricing.json`)
`frontend/scripts/seed-build/pricing.config.ts` gains two blocks, written to `seed/pricing.json` by `seed:build` and checked by `seed:check`:
- `peak: { multiplier: 2, tz: "Asia/Kuala_Lumpur", windows: [[540,720],[840,1080]] }`;
- `gateway: { routing: {order, require_parameters, allow_fallbacks, quantizations, data_collection}, fallbackModel: "deepseek/deepseek-v4-flash", embeddingProvider, embedBatch: 32, timeoutsMs: {chatFirstToken, chatIdle, image, embedding, meta, decision: {route, gate, rerank, emotion, default}} }`.

The TS `PricingTable` type gains these as optional fields, so the mock is unaffected.

`seed/settings.json` is **not** used, because its `data` is a wire `AppSettings` validated by `schema.json`. `PricingCalendar` takes the peak tz and windows from this block (OQ-G).

### D10. Pricing (`domain/pricing.py`, pure)
- **Functions:** `expected_out(max_tokens, recent_outs)`, `estimate_chat(prefix_tokens, warm, other_in, expected_out, period)`, `estimate_decision(tokens)`, `estimate_image(kind)` and `estimate_embedding(tokens)`.
- **Token counts** use a conservative heuristic, `ceil(utf8_bytes / 3)`, with no tokenizer dependency. Estimates are meant to be upper-bound-ish, and the Jev 32K check uses the same count, so a borderline state falls back rather than being sent.

  **Alternative:** `tokenizers`/`tiktoken`. Rejected for install weight and model mismatch; actual costs always come from the provider.
- **Warm prefix.** "Warm" is passed in by the caller. M3's TurnEngine knows the prefix hash; M2 callers pass `False`.

### D11. Decider
- **Questions and answers.** `Question = Choice(options: dict[str,str], instructions) | Noul(true: str, false: str, instructions) | Score(levels: list[str], instructions)`. Answers mirror Jev's shapes, plus `source`.
- **`ask(...)`:**
  1. Fixtures first, per question.
  2. Budget-check the rest.
  3. One `decisions.decide` through `Gateway.paid` (category `decision`, ctx purpose).
  4. Wait with `asyncio.wait({task}, timeout=…)`. On timeout, return the fallback at once while the task **keeps running** to completion, so the late answer is recorded but discarded.

  Background tasks are held in a set, cancelled on `stop()`, and recorded as estimate rows via D5.
- **Validation per answer.** A partial fallback is run once and only its invalid keys are taken.
- **Fixtures.** `DeciderFixtures` is a `(purpose, key) → answer` mapping on the Runtime. It is set by Python tests in M2; the HTTP route `/_test/decider-fixtures` comes in M3 (OQ-H).

### D12. Settings PATCH
`settings.update_local(patch)` runs under a settings `asyncio.Lock`:
1. Strip the ignored fields (`openRouterKeyStatus`, `demoMode`, `spentTodayUsd`, `pricing`, `models`, `energy.estReplyPoints`).
2. Deep-merge into the local file's dict.
3. Build the full `AppSettings` and validate it against `schema.json` (`AppSettings` def) plus range rules: caps > 0, `warnAtPct` 1–100, energy numbers > 0, overrides are non-empty strings.
4. Write atomically and publish `entity.changed settings`.

### D13. testModel probes
Paid probes go through `Gateway.paid` with `purpose: "probe"` and `world_id: None` (`CallContext.world_id` becomes optional for system calls):

| Role | Probe |
|---|---|
| chat | `max_tokens: 1` |
| decision | One `noul` question |
| embedding | `["ping"]` |
| image / music | `meta.model_exists(model)` against `GET /api/v1/models` (free) |

The returned `model` is `modelOverrides[role] ?? models[role]`.

### D14. Test-mode fake provider (resolves tension 1; see OQ-A)
`FakeOpenRouter` answers in-process:
- `/v1/key` and `/v1/credits`;
- `/v1/chat/completions`: SSE and JSON, text `"ok"`, `usage.cost` 0.000002, provider `DeepSeek`;
- `/alpha/decisions`: the first option, `noul` 0.5, the middle score level;
- `/v1/embeddings`: deterministic unit vectors;
- `/v1/models`: lists the configured IDs;
- `/v1/generation`: returns the cost.

Any bearer starting `sk-or-bad` gets 401 everywhere. The same handler backs the Python integration tests that need a live-ish server, and the `npm run test:http` backend.

The respx fixture files (`backend/tests/fixtures/openrouter/*.json`) cover each client's success, plus one per ErrorCode. Each file carries `"verified": false` until the live checklist confirms it (OQ-C).

### D15. Runtime wiring and factory reset
- **Construction.** `Runtime.start()` builds `KeyStore`, `HttpCore`, `Gateway`, `ReservationBook`, `LedgerWriter`, `EnergyLocks`, `Decider` and `CostCorrector`, after the DB, and starts the corrector.
- **Teardown.** `stop()` cancels the corrector and Decider stragglers and closes the httpx client.
- **Factory reset** already closes the `Gate`, waits for in-flight requests, then stop → wipe → start. It therefore drops reservations, the rejected fingerprint and the secrets file together, and the startup scan finds nothing (the ledger is gone).

### D16. HttpClient and the portable suite
- **`transport.ts`** gains `put<T>(path, body)`, which is not idempotent-keyed (PUTs are naturally idempotent).
- **HttpClient methods:** settings `update`/`setKey`/`testConnection`/`testModel` and characters `topUpEnergy`/`setEnergyMax`.
- **HTTP harness:** `supports: "M2"`, `setKey: () => client.settings.setKey("sk-or-test-0001")`.
- **Portable test 117** is rewritten to the shared semantics (`client-contract` spec). Its "setKey returns invalid immediately" half moves to `clientContract.mock.test.ts`.

### D17. Tooling
- **Dependencies:** `respx` added to the dev group.
- **ruff:** `TID` selected, with a `flake8-tidy-imports.banned-api` entry for `httpx`, ignored in `horizon/gateway/**` and `tests/**`.
- **mypy:** strict on `horizon.gateway.*` and `horizon.ai.decider`.
- **pytest:** `markers = ["live: …"]` and `addopts = "-m 'not live'"`. `tests/live/` is skipped unless `HORIZON_LIVE=1` and a key is in the environment.
- **`.env.example`** at the repo root, next to where `config.py` reads `.env`.

## Risks / Trade-offs

- **Jev is alpha, and the OpenRouter `/generation`, `/credits` and `/models` shapes are "verify in M2".** Parsers could be wrong against the live API. → The parsers are tolerant (unknown fields ignored, missing cost → estimate row + correction). The fixtures are flagged unverified, and the manual live checklist (task 12) confirms or corrects them before archive.
- **`require_parameters` + `logprobs` may route away from DeepSeek.** That would lose caching and break the price assumptions. → A provider warning on the result and the ledger `provider` column make it visible; the live checklist measures it.
- **The reservation book is in memory.** A crash loses reservations, but the in-flight calls die with the process, so nothing is double-booked. The corrector rescans estimate rows on restart.
- **The global preflight lock serialises the preflight of every paid call.** It's one indexed SUM per call, about 1 ms. Acceptable at single-user scale. → If M3 shows contention, cache `spentToday` in memory and update it on record.
- **Estimate rows without a generation ID** (cancelled before the first chunk) can never be corrected. → They are recorded at the upper-bound-ish estimate, which errs toward over-reporting. That's honest under NFR-09.
- **The secrets file on Windows can't be `chmod 600`.** → It relies on the user-profile ACL of the repo's `data/` (gitignored), noted in the README. The key never leaves loopback.
- **Background tasks and the frozen test clock.** → The corrector and Decider stragglers never call `clock.sleep` (D7). Tests inject an instant sleeper.
- **Byte-based token estimates over-count for English** (about 4 chars per token). So a borderline Jev state may fall back unnecessarily. → That's acceptable: the fallback is deterministic, and the threshold can be tuned at the AI stage.

## Migration Plan

- **No database migration.** All columns exist. Alembic stays at `0001`.
- **New data file:** `data/secrets.local.json`, created only by `PUT /settings/key`. The `settings.local.json` format is unchanged; PATCH writes the same shape.
- **`seed/pricing.json` gains additive keys** through `seed:build`. The mock ignores them.
- **Rollback:** revert the branch. A leftover `secrets.local.json` is ignored by M1b code, which never reads the key.

## Open Questions

These are the known tensions. Each has a **default the specs and tasks already use**; flip any of them before `/opsx:apply` and the affected spec or task changes with it.

- **OQ-A: Key-test semantics over HTTP.**
  - **Default:** the in-process fake provider in test mode (D14). Portable test 117 asserts only the shared behaviour: rejected key → `testConnection` gives `invalid_key` → status `invalid`. The mock's immediate `invalid` moves to a mock-only test.
  - **Alternative:** make `setKey` call `/key`. That breaks doc 03's "no network on setKey".
- **OQ-B: Redaction token.** **Default** `sk-or-***` with `+` (D4). The alternative keeps `sk-or-[REDACTED]`; it's a one-line change, and the spec scenario would change with it.
- **OQ-C: Unverified provider shapes.**
  - **Default:** fixtures are recorded from the docs and the Jev reference and flagged `"verified": false`.
  - The user runs `pytest -m live` (≤ $0.05) with their own key in `.env`, never pasted in chat. That run confirms `/key`, `/credits`, `/generation`, `/models` (image/music metadata), the Jev request and response, and whether `logprobs` + `require_parameters` leaves DeepSeek.
  - Any mismatch is fixed in the parsers and fixtures, without a spec change.
- **OQ-C findings (live run, 2026-10-04; total live spend ≈ $0.00003).**
  - **Confirmed as recorded:**
    - `/key` and `/credits` are wrapped in `data`.
    - Chat (complete and stream) reports `usage.cost` and cached tokens. One generation ID covers every chunk, and usage comes on the last one.
    - `/generation?id=` answers 404 for about 13 s, then returns `data.total_cost`, `provider_name` and `tokens_*`. The corrector's 2/5/15/60 s backoff covers that wait.
  - **Fixed:**
    - Jev's top level is `{id, model, provider, answers, usage}`. Each answer carries its `type`, and a score's `legend` is an object, not a list; the fixture now matches.
    - Billing is exactly `input_tokens × $0.042/M`. Jev reports some output tokens, but they aren't billed.
    - `/models` lists text models only unless you pass `output_modalities=all`, so `model_exists` now passes that filter.
  - **Routing (decided as D-80):** DeepSeek's own endpoint was removed by OpenRouter's guardrail (`paid-model-training-violation-by-account`), and chat went to the cheapest third party (Relace; Wafer when `logprobs` was set).
    - Chat now sends `data_collection: "allow"`.
    - The user's OpenRouter privacy settings must also allow paid endpoints that may train on inputs (https://openrouter.ai/settings/privacy).
    - The provider warning makes any fallback visible.
    - **Verified:** after the account setting was enabled, the committed routing is served by DeepSeek with no provider warning.
  - **For later milestones:**
    - **M4:** `google/lyria-3-clip` is not on OpenRouter (its endpoints return 404), so music needs another source, and `testModel("music")` reports it as unavailable until then. The image fixture is still unverified, because the live run made no paid image call.
    - **M5:** Qwen3 Embedding 8B returns 4096 dimensions by default. `dimensions: 1024` is honoured by Nebius, so the embedder must pass the space's dimensions.
- **OQ-D: An env key vs saving a key from the UI.**
  - **Default:** doc 01's precedence stays (env > file). `setKey` rejects with `conflict` and `details.source: "env"` while an env key is effective, so the UI never appears to save a key that isn't used.
  - **Alternative:** let the file win over the env key.
- **OQ-E: `PATCH /settings` read-only fields.**
  - Doc 03 says they are "rejected", but the portable test (the executable spec on both clients) expects `estReplyPoints` to be **ignored**.
  - **Default: ignore** (D12). Doc 03 gets a one-line correction in this change.
- **OQ-F: Key status vocabulary.** The M2 prompt said `none/set/valid/invalid`, but the contract is `missing | set | invalid`. **The contract is kept** (additive-only rule). "Valid" is not tracked; a passing `testConnection` leaves the status at `set`.
- **OQ-G: Peak-window time zone.**
  - Doc 04 says MYT (DeepSeek's schedule), while M1b computes peak in `HORIZON_TZ`.
  - **Default:** the peak windows use the fixed `Asia/Kuala_Lumpur` from `pricing.json`, and day boundaries (`spentToday`, energy day) stay in `HORIZON_TZ`. The two are identical at the default tz.
- **OQ-H: `/_test/decider-fixtures` over HTTP.** Doc 03 lists it for "M2/M3". **Default:** defer the route to M3, when the first HTTP-visible Decider caller (the Router) lands. M2 uses Python-level fixtures.
- **OQ-I: What M2 exercises end to end.**
  - **Default, over HTTP:** the key flow, settings PATCH, `testConnection`, `testModel` (all roles), top-up and set-max, through the TS HTTP suite.
  - **Service-level only, with respx:** chat stream/complete, images, embeddings, the Decider, the corrector and the cap races.
  - Nothing else spends until M3.
- **OQ-J: Corrector backoff clock.** **Default:** real `asyncio.sleep` (injectable), never `clock.sleep`. Row age is measured with the Clock.
- **OQ-K: Persisting `invalid`.** **Default:** in memory only (D3). After a restart the status reads `set` until the next 401. This avoids writing provider state into the secrets file.
- **OQ-L: A key is required for top-up.** Doc 03 is silent, and the MockClient requires one. **Default:** mock parity (`missing_key` / `invalid_key`). Set-max needs no key.
