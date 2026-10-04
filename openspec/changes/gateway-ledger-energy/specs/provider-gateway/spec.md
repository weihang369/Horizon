# Spec Delta

## Purpose

The gateway is the backend's only route to the network. Every call to OpenRouter (chat, Jev decisions, images, embeddings and the free metadata calls) goes through it, so routing, timeouts, retries, error mapping and the paid-call pipeline are enforced in one place.

## ADDED Requirements

### Requirement: Single network boundary
All outbound HTTP to OpenRouter SHALL go through the gateway. No other backend module SHALL open an outbound HTTP connection, and the key SHALL be attached to a request only by the gateway's HTTP client. A lint check SHALL fail the build if the HTTP library is imported outside the gateway.

#### Scenario: Lint guard
- **WHEN** a module outside the gateway imports the outbound HTTP library
- **THEN** the lint step fails and names the file

### Requirement: Paid-call pipeline
Every paid call SHALL run these steps in order: preflight (caps, including in-flight reservations, then reserve the estimate), request, record (one ledger row), settle (release the reservation; drain energy only when the purpose is `reply`), and emit (energy and budget events, then the `on_call` hook). A preflight refusal SHALL happen before any request is sent.

#### Scenario: Refused before spend
- **WHEN** a paid call's preflight finds the daily cap would be exceeded
- **THEN** the call rejects with `daily_budget_exceeded`, no request reaches the provider, and no ledger row is written

#### Scenario: Reservation released on failure
- **WHEN** a paid call fails with `provider_error` after its preflight reserved $0.002
- **THEN** the reservation book no longer holds that $0.002

### Requirement: Call context is labelled at the source
Each paid call SHALL carry a call context with its ledger `category`, its internal `purpose`, its `world_id`, optional `character_id`, `session_id`, `job_id` and `message_id`, and whether it counts toward a creation cap. Callers SHALL obtain a context only from a factory that takes the purpose. There SHALL be no separate flag to request an energy drain: draining is derived from `purpose == "reply"`.

#### Scenario: Non-reply call does not drain
- **WHEN** a `route` decision is made for a character
- **THEN** its ledger row has `purpose: "route"`, and the character's energy is unchanged

### Requirement: Pinned routing for the main LLM
Chat requests to the main LLM SHALL send the pinned provider preferences: DeepSeek first, `require_parameters`, fallbacks allowed, full-precision quantizations only, `data_collection: "allow"` (so the DeepSeek first-party endpoint stays eligible, D-80), and usage included. Model IDs SHALL come from committed config, never a `~latest` alias. When the response names a serving provider other than DeepSeek, the call result SHALL carry a provider warning for the trace.

#### Scenario: Request body
- **WHEN** a chat completion is sent
- **THEN** the outgoing body has `provider.order: ["DeepSeek"]`, `provider.require_parameters: true`, `provider.data_collection: "allow"` and `usage.include: true`

#### Scenario: Served elsewhere
- **WHEN** a recorded response reports provider `"Chutes"`
- **THEN** the result carries a provider warning naming `Chutes`, and the ledger row's `provider` is `Chutes`

### Requirement: Streamed chat
The chat client SHALL stream chunks that each carry the provider's `generation_id`, taken from the first chunk. It SHALL also offer a non-streaming completion. A stream that ends normally SHALL yield the final usage, including the provider-reported cost.

#### Scenario: Generation id on every chunk
- **WHEN** a recorded stream of five chunks is consumed
- **THEN** every chunk carries the generation ID from the first chunk, and the last one carries `usage.cost`

### Requirement: Per-purpose timeouts
The gateway SHALL apply these default timeouts, all overridable by config:

| Call | Timeout |
|---|---|
| Chat, time to first token | 20 s |
| Images | 180 s |
| Embeddings | 30 s |
| Decision `route` | 400 ms |
| Decision `gate` (with input guardrail) | 500 ms |
| Decision `rerank` | 600 ms |
| Decision `emotion` | 300 ms |
| Any other decision | 3 s |

An exceeded timeout SHALL surface as `timeout`.

#### Scenario: Route decision too slow
- **WHEN** a `route` decision's recorded response is delayed past 400 ms
- **THEN** the call fails with `timeout`

### Requirement: Retry only when nothing was charged
The gateway SHALL retry a call at most once, and only when nothing can have been charged: a connection failure before any response, or a 429/5xx with no body. A call that may have been charged SHALL NOT be retried automatically. That includes a response lost after it was sent.

#### Scenario: Connection refused
- **WHEN** the first attempt fails to connect and the second succeeds
- **THEN** the call succeeds and exactly one ledger row is written

#### Scenario: Body lost after send
- **WHEN** the connection drops after the request was sent and before a response is read
- **THEN** the call is not retried, and it is recorded at its estimate with a generation ID if one is known

### Requirement: Provider errors map to ErrorCodes
Provider and transport failures SHALL map to these ErrorCodes:

| Failure | ErrorCode |
|---|---|
| 401 | `invalid_key` |
| 402 | `insufficient_credits` |
| 403 moderation, or a refusal finish reason | `content_refused` |
| 429 | `rate_limited`, with `retryAfterSec` |
| 408, or our own timeout | `timeout` |
| 5xx, or a malformed response | `provider_error` |
| An error chunk mid-stream | `provider_error`, with the partial text returned |

Messages SHALL never contain the key.

#### Scenario: Rate limited
- **WHEN** a recorded 429 has `Retry-After: 12`
- **THEN** the error is `rate_limited` with `retryAfterSec: 12`

#### Scenario: Mid-stream error keeps partial text
- **WHEN** a stream delivers "Hello the" and then an error chunk
- **THEN** the caller gets `provider_error` together with the partial text "Hello the"

### Requirement: Free metadata calls
Key info, credits and generation lookups SHALL go through the gateway as free calls. They SHALL NOT be reserved, recorded in the ledger or counted toward any cap.

#### Scenario: Credits lookup
- **WHEN** credits are fetched
- **THEN** no ledger row is written and `spentTodayUsd` is unchanged

### Requirement: Embedding batches
The embeddings client SHALL send at most 32 texts per request to the pinned provider. It SHALL return vectors in input order, and write one ledger row per request.

#### Scenario: Seventy texts
- **WHEN** 70 texts are embedded
- **THEN** three requests are sent (32, 32 and 6 texts), 70 vectors come back in input order, and three ledger rows are written

### Requirement: Call observer hook
After each paid call settles, the gateway SHALL invoke an observer hook with the call's context, its redacted request summary and its result. The default hook SHALL do nothing. An exception raised inside the hook SHALL NOT fail the call.

#### Scenario: Failing hook
- **WHEN** an attached hook raises an exception
- **THEN** the call still returns its result, and the exception is logged with the key redacted

### Requirement: Test mode never reaches the network
When `HORIZON_TEST=1`, the gateway SHALL use an in-process fake provider instead of the network. A key starting `sk-or-bad` SHALL get 401 on every call. Any other key SHALL get deterministic successful responses for key info, credits, chat, decisions, embeddings and model metadata. Automated tests SHALL NOT make live network calls.

#### Scenario: Bad key in test mode
- **WHEN** in test mode the key is `sk-or-bad-zzz` and the connection is tested
- **THEN** it rejects with `invalid_key`, and no network socket is opened

#### Scenario: Live tests are opt-in
- **WHEN** the default backend test run executes
- **THEN** tests marked `live` are skipped
