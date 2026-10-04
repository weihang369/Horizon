# Tasks

> Before starting: confirm or override design.md OQ-A…OQ-L. The tasks below implement the defaults recorded there.
> Constraints for every task: no network in automated tests; only obviously fake `sk-or-test-…` keys in code, fixtures and tests; contract additive; commits without Claude attribution.

## 1. Tooling and config

- [x] 1.1 Set up the backend tooling. Verify that `uv sync`, `uv run ruff check`, `uv run mypy` and `uv run pytest` are all green with no behaviour change. The changes:
  - add `respx` to the dev group in `backend/pyproject.toml`;
  - select ruff `TID` with a `flake8-tidy-imports.banned-api` entry for `httpx`, with per-file ignores for `horizon/gateway/**` and `tests/**`;
  - make mypy strict on `horizon.gateway.*` and `horizon.ai.decider`;
  - add the pytest `live` marker with `addopts = "-m 'not live'"`.
- [x] 1.2 Prove the httpx ban works: a scratch import of `httpx` in `horizon/services/` makes `uv run ruff check` fail with the ban message. Remove the scratch import afterwards.
- [x] 1.3 Add `.env.example` at the repo root: `OPENROUTER_API_KEY=` (blank) plus the `HORIZON_*` variables with their defaults and one-line comments. Verify `git check-ignore .env` matches and `git check-ignore .env.example` does not.
- [x] 1.4 Add the `peak` and `gateway` blocks (design D9) to `frontend/scripts/seed-build/pricing.config.ts`, with optional fields on the TS `PricingTable` type, then run `npm run seed:build`. Verify that `seed/pricing.json` contains them, `npm run seed:check` passes, and the frontend unit tests and typecheck are green.

## 2. Redaction and the key store

- [x] 2.1 Create `gateway/redact.py` (`KEY_RE = sk-or-[A-Za-z0-9_-]+`, `REDACTED = "sk-or-***"`, `redact()`). Switch `logs.py` to import it, and make `api/errors.py` redact every envelope's `message` and `details`. Verify with these tests, plus the existing M1b logging test updated to the new token:
  - a log line with `sk-or-v1-abc123`;
  - a log line with the short key `sk-or-good`;
  - an exception traceback;
  - an error envelope whose details echo a key.
- [x] 2.2 Extend `config.py` with `openrouter_key: SecretStr | None`, read from env and then `.env`, always `None` when `HORIZON_TEST=1`. Verify with unit tests for each of these:
  - env wins over `.env`;
  - test mode ignores both;
  - `repr(cfg)` contains no key.

  Replace the M1b test asserting the key is never read.
- [x] 2.3 Implement `services/keys.py` `KeyStore`:
  - the effective key and its source (config first, then `data/secrets.local.json`);
  - format validation;
  - an atomic write (temp + `os.replace`) and delete;
  - the `rejected_fingerprint` and `mark_rejected()`;
  - `status()` / `demo_mode()`;
  - a `conflict` when an env key is effective.

  Verify with unit tests covering every `openrouter-key` spec scenario that doesn't need HTTP.

## 3. Pure domain: pricing, budget, energy

- [x] 3.1 Implement `domain/pricing.py`: the price table loaded from `seed/pricing.json`, `expected_out`, the chat, decision, image and embedding estimates, the peak multiplier, and the byte-based token count. Verify with `tests/unit/test_pricing.py`:
  - a decision with 10,000 tokens is $0.00042;
  - the peak estimate is twice the off-peak one;
  - `expected_out` uses `min(max_tokens, p75, 220)`;
  - the warm prefix uses the cached rate.

  `mypy --strict` must also be clean.
- [x] 3.2 Make `PricingCalendar` take the peak time zone and windows from the `pricing.json` `peak` block (OQ-G), and keep day boundaries in `HORIZON_TZ`. Verify that the existing clock tests pass, and add one where `HORIZON_TZ=UTC` still gives `peak` at Tuesday 10:30 MYT.
- [x] 3.3 Implement `domain/budget.py`: `exceeds_daily`, `exceeds_creation`, and `crossed(before, after, warn_at)` with `before < warn_at ≤ after`. Verify with unit tests for the 0.79 → 0.81 crossing, the 0.81 → 0.83 non-crossing, a crossing that lands exactly on the line, and the creation scope.
- [x] 3.4 Add `with_max` to `domain/energy.py`, plus `withMax` cases to `backend/tests/fixtures/energy/cases.json`: lowering below current, raising, demo-frozen and regen-settled-first. Teach both fixture runners the new `fn`. Verify that `tests/unit/test_energy_fixtures.py` and the TS `energy.test.ts` both pass every case, including the new ones.

## 4. Gateway core

- [x] 4.1 Implement `gateway/errors.py` (`ProviderError` and the mapping table) and `gateway/context.py` (frozen `CallContext` with an optional `world_id`, `call_ctx(purpose, …)`, and `drains` derived from `purpose == "reply"`). Verify with unit tests for each mapping row, for `retryAfterSec` taken from `Retry-After`, and that `drains` is true only for `reply`.
- [x] 4.2 Implement `gateway/client.py` `HttpCore`: one `httpx.AsyncClient`, an injectable transport, the bearer header built per request from the `KeyStore`, per-request timeouts, and the "nothing charged" retry (D6). Verify with respx tests:
  - a connect error followed by success is retried once;
  - a 503 with an empty body is retried once;
  - a 503 with a body is not retried;
  - a read error after send is not retried;
  - a 401 calls `mark_rejected`.
- [x] 4.3 Implement `gateway/fake.py` `FakeOpenRouter` (D14), an `httpx.MockTransport` handler. Verify with unit tests that each endpoint returns its deterministic payload, that `sk-or-bad*` gets 401 everywhere, and, through a socket guard fixture, that no socket is opened.
- [x] 4.4 Create `backend/tests/fixtures/openrouter/`: recorded JSON for the success response of every client, plus one file per ErrorCode case. Each file carries `"verified": false` and a `source` note saying which doc or reference it was taken from. Add a small loader helper for respx. Verify that a test loads every file and that no file contains `sk-or-` followed by anything other than `test-`.

## 5. Gateway clients

- [x] 5.1 Implement `gateway/chat.py`:
  - `stream()`: SSE parsing, `generation_id` taken from the first chunk, the time-to-first-token and idle timeouts, a mid-stream error that keeps the partial text, refusal → `content_refused`;
  - `complete()`;
  - the pinned routing body and the provider warning.

  Verify with respx tests for every `provider-gateway` chat scenario: request body contents, generation ID on every chunk, usage on the last chunk, a "Chutes" provider warning, a mid-stream error with partial text, and a first-token timeout giving `timeout`.
- [x] 5.2 Implement `gateway/decisions.py`: the Jev request `{model, state, questions}` with the pinned model, and parsing of the choice, noul and score answers plus usage. Verify with respx tests for each answer type and for the 401, 429, 5xx and malformed cases.
- [x] 5.3 Implement `gateway/images.py` (`generate` → `ImageResult` with the image bytes or a data URL, and the cost) and `gateway/embeddings.py` (batches of 32 with the pinned provider, vectors in input order). Verify with respx tests: 70 texts produce three requests and 70 ordered vectors; each client maps 402 to `insufficient_credits` and 403 moderation to `content_refused`.
- [x] 5.4 Implement `gateway/meta.py`: `key_info`, `credits`, `generation(id)` (a 404 means "not yet") and `model_exists(model)`. Verify with respx tests that each parses its fixture, and with an assertion that meta calls never touch the ledger or the reservation book.

## 6. Pipeline, reservations and ledger

- [x] 6.1 Implement `gateway/reservations.py` `ReservationBook`: an atomic check-and-reserve under a lock, `release`, per-character totals, and the job-wide `reserve_job` / `release_step` API. Verify with unit tests for the spec's "two in flight" and "job-wide reservation" scenarios.
- [x] 6.2 Implement `services/ledger.py` `LedgerWriter.record(row, drain)`:
  - one writer transaction;
  - the reply drain inside it, under the per-character lock taken before the writer lock;
  - text columns redacted;
  - it returns the spend before and after.

  Also add the read helpers `spent_today`, `creation_spent`, `calls_for_message` and `reply_usage`. Verify with integration tests on a temporary DB:
  - the drain and the row commit together, or roll back together;
  - a non-reply purpose leaves energy unchanged;
  - an overdraft clamps at 0.
- [x] 6.3 Implement `gateway/pipeline.py` `Gateway.paid()` (D5): the key guard, preflight with `budget.reached` + 402, reserve, send, record, release after the commit, the shielded estimate row on cancel or break, `budget.warning` on crossing, `entity.changed` for drained characters, and the `on_call` hook (no-op default, exceptions logged and swallowed). Verify with integration tests:
  - refused before spend (no request, no row);
  - the reservation is released on `provider_error`;
  - a crossing publishes exactly one warning;
  - a hook that raises still returns the result;
  - a `budget.reached` payload validates as a `GlobalEvent`.
- [x] 6.4 **Overrun bound test.** Run 20 concurrent paid calls whose respx actual costs exceed their estimates, under a $0.05 cap. Verify that the recorded spend is ≤ the cap + Σ(actual − estimate) of the admitted calls, and that every refused call made no request.
- [x] 6.5 **Cancelled stream test.** Cancel a chat stream after 3 chunks. Verify that one `cost_source='estimate'` row with the generation ID exists, written even though the task was cancelled, and that the reservation is released.

## 7. Cost corrector

- [x] 7.1 Implement `services/corrector.py` `CostCorrector`: a queue and a worker, an injectable sleeper, backoff 2 s → 5 s → 15 s → 60 s → 5 min, giving up at 24 h of row age, and the guarded `UPDATE … WHERE cost_source='estimate'`. For reply rows it applies the energy delta (drain or refund) and publishes `entity.changed`. Verify with integration tests:
  - the cancelled stream from 6.5 is corrected to the respx `/generation` cost;
  - a second lookup changes nothing;
  - a 404, 404, 200 sequence corrects the row on the third try;
  - the reply delta adjusts energy.
- [x] 7.2 Add the startup scan: estimate rows with a `generation_id` that are ≤ 24 h old are re-enqueued, and older ones are left alone. Verify with an integration test that stops the runtime with a pending row, restarts it, sees the row corrected once, and sees a 25-hour-old row untouched.

## 8. Decider

- [x] 8.1 Implement `ai/decider.py`: the `Choice`/`Noul`/`Score` questions, the answers with `source`, `DecisionResult`, `DecisionUnavailable` and `DeciderFixtures`. `ask()` takes fixtures first, then the 32K check, then one call through `Gateway.paid` (category `decision`), then a timeout with the late task kept running and recorded, then per-answer validation with a partial fallback. Verify with tests covering every `decider` spec scenario:
  - batched questions;
  - over budget;
  - one bad answer;
  - a late answer at 650 ms against 400 ms that still writes a ledger row;
  - no fallback → `DecisionUnavailable`;
  - a gate decision that doesn't drain energy;
  - a fixture answer with no request and no row.
- [x] 8.2 Make the per-purpose timeouts come from the `pricing.json` `gateway.timeoutsMs.decision` block, with an override per call. Verify with a unit test that changing the config value changes the effective timeout.

## 9. Settings and key routes

- [x] 9.1 Make `GET /settings` report the real `openRouterKeyStatus` / `demoMode` from the `KeyStore`, and pass `demo_mode` into the energy reads in `services/reads.py`. Verify with an updated `test_settings` (the "Key ignored for now" scenario in test mode, and status `set` after a key is saved) and with the existing energy-read tests in both modes.
- [x] 9.2 Add `PUT /settings/key`: format check, save or delete, env conflict, `entity.changed settings`, no network. Verify with integration tests for every `openrouter-key` "Setting the key" and "Environment key" scenario, plus a socket guard proving no network.
- [x] 9.3 Add `PATCH /settings` (D12): strip the ignored fields, deep-merge, validate against the schema plus the range rules, write atomically, publish `entity.changed settings`. Verify with integration tests for every `http-api` "Settings update" scenario, including persistence across a runtime restart. In the same task, correct doc 03's "read-only fields rejected" to "ignored" (OQ-E).
- [x] 9.4 Add `POST /settings/test-connection` (key info + credits, `latencyMs`, `missing_key` / `invalid_key`, no ledger row). Verify with integration tests against the fake provider: good key, `sk-or-bad` → `invalid_key` and then status `invalid`, no key → `missing_key`.
- [x] 9.5 Add `POST /settings/test-model` (D13): paid probes recorded with `purpose: "probe"`, image and music checked through metadata only, `model` = override ?? configured. Verify with integration tests for each of the five roles: embedding writes one `embedding` probe row, image writes no row, no key → `missing_key`, and an override is echoed.

## 10. Energy routes

- [x] 10.1 Add `POST /characters/{id}/energy/top-up` (`services/energy_writes.py`, D8): key guard, character lock, the D-76 gate in the writer transaction, the `energy_topup` row at $0, the wire `Energy`, and `entity.changed character`. Verify with integration tests for the `energy` spec scenarios (two +5000 top-ups under a $0.60 cap, no key → `missing_key`), the spend-ledger "Top-up row" scenario, and a refused top-up publishing nothing.
- [x] 10.2 Add `PUT /characters/{id}/energy/max` (no key needed; frozen settle in demo mode). Verify with integration tests for "Lower the max" (800 of 500, no `fullAt`) and "Set-max in demo mode", and that the response validates as `Energy`.
- [x] 10.3 **Race test.** Run a +500 top-up and a 5-point reply drain concurrently on one character starting from 100 ⚡. Verify the final value is 595 ⚡ (frozen clock) across 50 repetitions.

## 11. Runtime wiring

- [x] 11.1 Wire `KeyStore`, `HttpCore` (fake transport in test mode), `ReservationBook`, `LedgerWriter`, `EnergyLocks`, `Gateway`, `Decider` and `CostCorrector` into `Runtime.start()` / `stop()` (D15). Verify with an integration test that a factory reset during a pending correction leaves no running tasks and no reservations, deletes `secrets.local.json`, and returns the status to `missing`. Also verify `uv run horizon serve` in test mode answers `test-connection` from the fake provider.

## 12. HttpClient and the portable suite

- [x] 12.1 Add `put<T>()` to `frontend/src/client/http/transport.ts`, and implement settings `update` / `setKey` / `testConnection` / `testModel` and characters `topUpEnergy` / `setEnergyMax` in `HttpClient.ts`, removing their `later("M2")` stubs. Verify with typecheck and the http-client unit tests: a top-up sends an `Idempotency-Key`, a 402 maps to `daily_budget_exceeded`, and `setKey` sends a PUT.
- [x] 12.2 Rewrite portable test "mock keys: sk-or-* valid, sk-or-bad* invalid" to the shared semantics in the `client-contract` spec. Add the mock-only test "setKey(sk-or-bad…) is invalid immediately" to `clientContract.mock.test.ts`. Verify that `npm test` passes on the MockClient with nothing pending, and that the "≥ 50 milestone-tagged tests" check still holds.
- [x] 12.3 Switch the HTTP harness to `supports: "M2"` with `setKey: () => client.settings.setKey("sk-or-test-0001")`. Verify that `npm run test:http` runs every M1b and M2 test green against the test-mode backend, and lists M3+ as pending.

## 13. Live verification (manual, run by the user)

- [x] 13.1 Add `backend/tests/live/` (marked `live`, skipped unless `HORIZON_LIVE=1` and the key is in the environment). It confirms:
  - the `/key`, `/credits`, `/generation` and `/models` shapes;
  - a 1-token DeepSeek completion, including whether `logprobs` + `require_parameters` changes the serving provider;
  - one Jev call of each question type;
  - one embedding.

  It asserts a total spend ≤ $0.05 from the ledger. Add `backend/tests/live/README.md` with the run steps: the user puts the key in `.env` themselves and runs `HORIZON_LIVE=1 uv run pytest -m live`. Verify that the default `uv run pytest` reports these tests as deselected.
- [x] 13.2 After the user's live run: flip the confirmed fixtures to `"verified": true`, and fix any parser or fixture mismatch. Record the observed provider routing and the Jev billing note in design.md OQ-C. Verify that the respx suite is still green. If the user doesn't run it before archive, leave this task unchecked and say so in the archive summary.

## 14. Integration checks

- [x] 14.1 **Leak sweep** (`local-backend` spec), one integration test: with the fake key `sk-or-test-leakcheck-0001`, run a set key, a connection test, every model probe, a 401, a 500 whose body echoes the key, a top-up, and a cancelled stream with its correction. Then grep the log file, every error response body, every ledger row, `GET /usage`, the captured global SSE frames and every file under `data/` except `secrets.local.json` for the key. Verify there are zero hits.
- [x] 14.2 Run every gate and record the results in the apply summary:
  - `uv run pytest`;
  - `uv run ruff check`;
  - `uv run mypy`;
  - `npm test`;
  - `npm run typecheck`;
  - `npm run test:http`;
  - `npm run seed:check`;
  - `npm run export-schema -- --check`;
  - the Playwright E2E suite on the mock.

  Verify that all are green, that `schema.json` is unchanged (contract additive, `schemaVersion` 1), and that `git grep -n "sk-or-" -- ':!*.md'` shows only obviously fake keys (`sk-or-test-…`, `sk-or-bad…`, `sk-or-good`, the MockClient's `sk-or-mock-…`) and the redaction pattern.
