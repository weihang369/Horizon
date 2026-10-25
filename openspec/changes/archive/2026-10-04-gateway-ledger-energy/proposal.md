# Proposal: gateway-ledger-energy (M2)

## Why

M1b gave Horizon a local backend that can browse, replay and edit worlds, but it can't make a single paid call. Settings still hard-code `openRouterKeyStatus: "missing"` and demo mode, and the HttpClient rejects every settings and energy write with `later("M2")`. Each AI milestone after this one (M3 sessions, M4 generation jobs, M5 knowledge) spends money through OpenRouter. They all need one place that holds the key safely, checks the caps before spending, records every cent in the ledger and drains energy correctly. M2 builds that foundation (doc 04 in full, doc 05 §3), so M3 can start on turns and not on plumbing.

## What Changes

- **Key handling.**
  - The OpenRouter key is read from env/`.env`, then `data/secrets.local.json`, and held as a `SecretStr`.
  - `PUT /settings/key` checks the format only and makes no network call. `null` deletes the secrets file.
  - `openRouterKeyStatus` (`missing | set | invalid`, the existing contract enum) and `demoMode` become real. Any 401 from OpenRouter flips the status to `invalid`.
  - **Test mode never reads a real key and never reaches the network.**
- **Settings writes.**
  - `PATCH /settings` deep-merges into `data/settings.local.json`. Computed and config-owned fields can't be changed.
  - `POST /settings/test-connection` returns `{ ok, latencyMs, creditsUsd? }`.
  - `POST /settings/test-model` is the cheapest probe for each role. For image and music it only checks metadata and never pays for a generation.
- **The gateway (`horizon/gateway/`), the only network code.**
  - Clients: `chat` (stream + complete), `decisions` (Jev, pinned `typesafe/jev-1.13`), `images`, `embeddings` (batches of 32), and `meta` (key, credits, generation lookup; free, no ledger row). `music` stays in M4.
  - Every paid call runs **preflight → request → record → settle → emit**.
  - Pinned DeepSeek routing, with a warning in the trace when another provider serves the call.
  - Per-purpose timeouts. A call is retried only when nothing can have been charged.
  - The full ErrorCode mapping, with the partial text kept when a stream breaks mid-way.
  - `CallContext` can be built only through `call_ctx(purpose)`, and the `on_call` hook is a no-op.
- **Reservation book and caps.**
  - The in-memory reservation book feeds the daily cap and the per-character creation cap.
  - `budget.warning` is emitted when a cap is crossed; `budget.reached` comes with 402 `daily_budget_exceeded` / `creation_budget_exceeded` before any spend.
  - A whole-job reservation API is ready for M4.
- **Ledger.**
  - One row per paid call, with `category` + `purpose`, and `cost_source` set to `provider` or `estimate`.
  - A cancelled or broken call is recorded at its estimate, together with its `generation_id`. A background corrector replaces the estimate with the actual cost exactly once. It survives a restart.
- **Pricing.** Estimates per category from `seed/pricing.json` (`domain/pricing.py`), plus the ×2 multiplier during DeepSeek peak. The peak window comes from the existing Clock.
- **Energy writes.**
  - Draining happens only for `purpose == 'reply'`: one UPDATE inside the ledger's writer transaction, under a per-character lock.
  - Demo mode freezes energy.
  - `POST /characters/{id}/energy/top-up` applies the D-76 gate and writes an `energy_topup` row at $0. `PUT /characters/{id}/energy/max` sets the maximum.
  - `entity.changed` for the character goes on the global stream.
- **Decider (`horizon/ai/decider.py`).**
  - All questions about one state go in one Jev call, after a 32K budget check.
  - Each answer is validated, and the fallback runs only for the invalid ones. Without a fallback the result is `DecisionUnavailable`.
  - Late answers are discarded but still recorded.
  - Scripted fixtures (`source: "fixture"`).
- **Redaction.** One `redact()` helper and one token, used by the log filter, the exception formatter, the ledger writer, error envelopes and the `on_call` hook.
- **HttpClient.** Settings `update`, `setKey`, `testConnection` and `testModel`, plus energy `topUpEnergy` and `setEnergyMax`. The HTTP portable suite moves to `supports: "M2"`.
- **Tests.**
  - Recorded HTTP (respx) for every client and every ErrorCode.
  - Leak tests showing the key never appears in logs, errors, the ledger, exports or SSE.
  - The concurrent-preflight overshoot bound.
  - A cancelled stream gets its estimate corrected.
  - Shared energy fixtures, including set-max.
  - An opt-in `pytest -m live` run (≤ $0.05, never in CI).
- **Repo hygiene.** A committed `.env.example` with blank values; `respx` as a dev dependency; a ruff rule banning `httpx` outside `gateway/`.

There are no **BREAKING** changes. The contract stays additive (`schemaVersion` 1), and every response still validates against `schema.json`.

## Capabilities

### New Capabilities
- `provider-gateway`: the only code that calls OpenRouter.
  - Clients, `CallContext`, pinned routing and the served-provider warning.
  - Per-purpose timeouts, the no-double-charge retry rule and the ErrorCode mapping.
  - The paid-call pipeline (preflight → request → record → settle → emit), the `on_call` hook, and the in-process fake provider used in test mode.
- `openrouter-key`: where the key comes from, `openRouterKeyStatus` / `demoMode`, `setKey`, `testConnection` and `testModel`.
- `spend-ledger`: one ledger row per paid call (`category`, `purpose`, `cost_source`, estimate vs actual), the estimate → actual correction, and `Message.usage` / `TurnTrace.calls[]` sourcing.
- `budget-caps`: the reservation book, the daily and creation caps, warning on crossing, `budget.reached`, the overrun bound, per-category cost estimates and the peak multiplier.
- `decider`: Jev bounded decisions. One call per state, the 32K check, per-answer validation with partial fallback, `DecisionUnavailable`, per-purpose timeouts and scripted fixtures.

### Modified Capabilities
- `energy`: adds the writes on top of the existing read and gate rules:
  - the reply drain inside the ledger transaction, under a per-character lock;
  - the demo-mode freeze on writes;
  - the top-up route (key required, D-76 gate, $0 row) and set-max;
  - set-max (`withMax`) fixtures.
- `http-api`: settings stop hard-coding the key status, and new routes arrive (`PATCH /settings`, `PUT /settings/key`, `POST /settings/test-connection`, `POST /settings/test-model`, `POST /characters/{id}/energy/top-up`, `PUT /characters/{id}/energy/max`). Test mode's provider stand-in is part of the test-only routes requirement.
- `local-backend`: key precedence, and test mode ignoring env keys. "The API key never leaks" widens from logs to the ledger, error envelopes, exports and SSE, with a single redaction token.
- `http-client`: settings and energy methods move off `later("M2")`, and the transport gains `PUT`.
- `client-contract`: the HTTP portable run supports M2, and the key-status test asserts only behaviour both clients share.
- `event-streams`: `entity.changed` for `character` (energy writes) and `settings` (settings/key writes); `budget.warning` / `budget.reached` on the global stream.

## Impact

- **Backend, new:**
  - `horizon/gateway/{client,chat,decisions,images,embeddings,meta,reservations,errors,redact,context,fake}.py`;
  - `horizon/ai/decider.py`;
  - `horizon/domain/pricing.py`;
  - `horizon/services/{keys,ledger,energy_writes}.py` (names settled in design);
  - new routes in `api/routes.py`.
- **Backend, changed:**
  - `config.py`: key source, test mode;
  - `logs.py`: redaction moves to `gateway/redact.py`;
  - `services/settings.py`: real key status, PATCH;
  - `services/reads.py`: demo flag from key status;
  - `runtime.py`: gateway, reservation book and corrector on the Runtime, and the corrector as a lifespan task;
  - `domain/energy.py`: `with_max`;
  - `pyproject.toml`: respx, the ruff banned-api rule, a `live` marker, mypy strict on `gateway/`.
- **Database:** no migration. `usage_records` already has every M2 column, and the energy columns are already REAL (`Float`).
- **Seed:** `seed/pricing.json` gains peak/routing/timeout config, generated through `frontend/scripts/seed-build/pricing.config.ts` (verified by `seed:check`).
- **Frontend:**
  - `client/http/{HttpClient,transport}.ts` (PUT, the settings and energy methods);
  - `clientContract.http.test.ts` (`supports: "M2"`, a real `setKey`);
  - one portable test rewritten, with its mock-only half moved to `clientContract.mock.test.ts`;
  - energy fixtures + `energy.test.ts` for `withMax`.
  - No UI changes.
- **Repo:** `.env.example` (blank values).
- **Out of scope:**
  - SessionActor, turns and session-stream `energy` events (M3);
  - job scheduler/workers, the music client and image post-processing (M4);
  - knowledge, memory, embedder pipelines and "Index seed knowledge" (M5);
  - real AI prompts beyond the `testModel` probes and the Decider plumbing.
