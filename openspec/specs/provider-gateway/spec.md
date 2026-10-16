# provider-gateway Specification

## Purpose

The gateway is the backend's only route to the network. Every call to OpenRouter (chat, Jev decisions, images, embeddings and the free metadata calls) goes through it, so routing, timeouts, retries, error mapping and the paid-call pipeline are enforced in one place.

## Requirements

### Requirement: Single network boundary
All outbound HTTP to OpenRouter SHALL go through the gateway. No other backend module SHALL open an outbound HTTP connection, except two the user starts explicitly:
- the document-conversion model download (`horizon models fetch`);
- the opt-in LangSmith client (see `opt-in-tracing`), which never receives the OpenRouter key.

The key SHALL be attached to a request only by the gateway's HTTP client. A lint check SHALL fail the build if the HTTP library is imported outside the gateway.

#### Scenario: Lint guard
- **WHEN** a module outside the gateway imports the outbound HTTP library
- **THEN** the lint step fails and names the file

#### Scenario: Tracing off by default
- **WHEN** a full test run executes with `HORIZON_LANGSMITH` unset
- **THEN** no connection is opened to any host

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
Chat requests to the main LLM SHALL send the pinned provider preferences: DeepSeek first, `require_parameters`, fallbacks allowed, full-precision quantizations only, `data_collection: "allow"` (so the DeepSeek first-party endpoint stays eligible, D-80), and usage included. They SHALL NOT send a fallback model list. Model IDs SHALL come from committed config, never a `~latest` alias. When the response names a serving provider other than DeepSeek, the call result SHALL carry a provider warning for the trace.

#### Scenario: Request body
- **WHEN** a chat completion is sent
- **THEN** the outgoing body has `provider.order: ["DeepSeek"]`, `provider.require_parameters: true`, `provider.data_collection: "allow"` and `usage.include: true`, and no `models` field

#### Scenario: Served elsewhere
- **WHEN** a recorded response reports provider `"Chutes"`
- **THEN** the result carries a provider warning naming `Chutes`, and the ledger row's `provider` is `Chutes`

### Requirement: Streamed chat
The chat client SHALL stream chunks that each carry the provider's `generation_id`, taken from the first chunk. It SHALL also offer a non-streaming completion. A stream that ends normally SHALL yield the final usage, including the provider-reported cost and any reasoning token count, and its finish reason. A stream whose finish reason is `error` or `insufficient_system_resource` SHALL fail as `provider_error`, may-be-charged, with its partial text kept.

#### Scenario: Generation id on every chunk
- **WHEN** a recorded stream of five chunks is consumed
- **THEN** every chunk carries the generation ID from the first chunk, and the last one carries `usage.cost`

#### Scenario: Finish reason kept
- **WHEN** a recorded stream ends with a content-less chunk whose `finish_reason` is `length`
- **THEN** that chunk is yielded, and the call's ledger row records `finish_reason: "length"`

#### Scenario: Error finish
- **WHEN** a recorded stream ends with `finish_reason: "insufficient_system_resource"` after the text `Well`
- **THEN** the call fails with `provider_error`, its partial text is `Well`, and a ledger row is written

### Requirement: Per-purpose timeouts
The gateway SHALL apply these default timeouts, all overridable by config:

| Call | Timeout |
|---|---|
| Chat, time to first token | 20 s |
| Images | 180 s |
| Embeddings | 30 s |
| Watch episode recap (whole call) | 30 s |
| Decision `route` | 400 ms |
| Decision `turn_plan` | 700 ms |
| Decision `follow_plan` | 400 ms |
| Decision `debate_plan` | 500 ms |
| Decision `guardrail` | 700 ms |
| Decision `guardrail_prompt` | 1,500 ms |
| Decision `reaction` | 1,500 ms |
| Decision `face_check` | 1,500 ms |
| Any other decision | 3 s |

An exceeded timeout SHALL surface as `timeout`.

#### Scenario: Route decision too slow
- **WHEN** a `route` decision's recorded response is delayed past 400 ms
- **THEN** the call fails with `timeout`

#### Scenario: Removed keys
- **WHEN** the shipped price table is loaded
- **THEN** it has no `gate`, `rerank` or `emotion` decision timeout and no `fallbackModel`

#### Scenario: Recap limit
- **WHEN** the shipped price table is loaded
- **THEN** `timeoutsMs.episode` is 30000, and the MockClient's mirror holds the same value

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
After each paid call settles, the gateway SHALL invoke an observer hook with the call's context, its redacted request summary and its result. While capture is on, the hook SHALL also receive the redacted request body and the response (the reply text, or Jev's answers), and never embedding texts or vectors, image bytes or audio bytes. While capture is off, no body SHALL be built. The default hook SHALL do nothing. An exception raised inside the hook SHALL NOT fail the call.

#### Scenario: Failing hook
- **WHEN** an attached hook raises an exception
- **THEN** the call still returns its result, and the exception is logged with the key redacted

#### Scenario: Bodies only with capture
- **WHEN** a reply completes with capture off
- **THEN** the hook receives no request messages and no reply text

### Requirement: Test mode never reaches the network
When `HORIZON_TEST=1`, the gateway SHALL use an in-process fake provider instead of the network. A key starting `sk-or-bad` SHALL get 401 on every call. Any other key SHALL get deterministic successful responses for key info, credits, chat, decisions, embeddings, images and model metadata, with decision answers in the provider's real shape (each answer carries its `type`). The fake SHALL count the requests it receives per endpoint, so tests can assert how many provider calls were made. Automated tests SHALL NOT make live network calls.

#### Scenario: Bad key in test mode
- **WHEN** in test mode the key is `sk-or-bad-zzz` and the connection is tested
- **THEN** it rejects with `invalid_key`, and no network socket is opened

#### Scenario: Live tests are opt-in
- **WHEN** the default backend test run executes
- **THEN** tests marked `live` are skipped

#### Scenario: Fake image
- **WHEN** in test mode a naive image generation is requested
- **THEN** the fake returns a decodable image with a cost, and its images request count goes up by one

### Requirement: Scripted chat source
Paid calls made by scripted AI ports (replies, routing, verdicts, summaries) SHALL run through the same paid-call pipeline as real calls: preflight with caps and reservations, one ledger row, settle, drain only for `reply`, and emit. Their output SHALL come from an in-process source that never opens a network connection, paced on the backend clock, with usage priced from the committed price table. Their ledger rows SHALL carry `provider: "scripted"` and `cost_source: "provider"`.

#### Scenario: Scripted reply is billed and capped
- **WHEN** the scripted profile answers a 1:1 message with a key set
- **THEN** one ledger row with `category: "chat"`, `purpose: "reply"` and `provider: "scripted"` is written, the speaker's energy drops, and no network connection is opened

#### Scenario: Scripted reply refused at the cap
- **WHEN** today's spend has reached the daily cap and the scripted engine starts a reply
- **THEN** the reply is refused with `daily_budget_exceeded` before any token is produced, and `budget.reached` is published

### Requirement: Image request shape
An image request SHALL send `model`, `prompt`, `aspect_ratio`, `resolution` and `n: 1`, and SHALL pass reference images as `input_references: [{ type: "image_url", image_url: { url } }]`, where each URL is a data URL. The image SHALL be read from `data[].b64_json` (or a data URL), and the cost from `usage.cost`.

#### Scenario: Edit with a reference
- **WHEN** an emotion edit is requested with the base portrait as reference
- **THEN** the request body holds one `input_references` entry of type `image_url` whose URL starts with `data:image/`

### Requirement: Music request shape
A music request SHALL be a streamed chat completion to the music model with `modalities: ["text", "audio"]`, `stream: true` and usage included. It SHALL NOT carry the main LLM's pinned routing block or its fallback chat model. The audio SHALL be the concatenation of the base64 `choices[0].delta.audio.data` chunks, and the cost SHALL come from `usage.cost`.

#### Scenario: Streamed clip is assembled
- **WHEN** the provider streams a music response in three audio chunks followed by a usage chunk
- **THEN** the gateway returns the decoded bytes of all three chunks in order, and the ledger row carries the reported cost with `category: "music"` and `purpose: "song"`

#### Scenario: No main-LLM routing on a music call
- **WHEN** a music request is sent
- **THEN** its body has no `provider.order` pinned to the main LLM's provider and no `models` fallback list

#### Scenario: Stream without audio
- **WHEN** a music stream ends without any audio data
- **THEN** the call fails with `provider_error`, and it is recorded in the ledger at its estimate because it may have been charged

### Requirement: Paid calls can mark and commit with their caller
A paid call SHALL let its caller run a step after the cap preflight passes and before the request is sent, and a step inside the same transaction that writes the call's ledger row. If the caller's post-response step fails after the provider has charged, the ledger row SHALL still be written. A preflight refusal SHALL run neither step.

#### Scenario: Refused job task is not marked as sent
- **WHEN** an image task's preflight is refused at the creation cap
- **THEN** the task is not marked as sent, and no ledger row is written

#### Scenario: Result and ledger row together
- **WHEN** an image call succeeds for a job task
- **THEN** the task's result and its ledger row become visible in the same commit

### Requirement: Scripted generation source
Paid generation calls made by scripted ports (profile drafts and images) SHALL run through the same paid-call pipeline as real calls, priced from the committed price table, with ledger rows carrying `provider: "scripted"`. They SHALL never open a network connection, and their duration SHALL follow the shared timing table on the backend clock.

#### Scenario: Scripted portrait is billed
- **WHEN** the scripted profile runs a one-candidate portrait job with a key set
- **THEN** one ledger row with `category: "image"`, `provider: "scripted"` and the job's `job_id` is written, and no network connection is opened

### Requirement: Scripted embedding source
Embedding requests made by the scripted embedder SHALL run through the same paid-call pipeline as real ones: key check, preflight with caps and reservations, and one ledger row per batch of at most 32 texts. The rows SHALL have category `embedding`, `provider: "scripted"`, the active space's model, input tokens counted from the texts, and a cost priced from the committed price table. The scripted embedder SHALL never open a network connection, and SHALL return deterministic unit vectors of the space's dimensions.

#### Scenario: Scripted source indexed with a key
- **WHEN** with the scripted profile and a key set a three-paragraph Markdown source is added
- **THEN** exactly one `embedding` ledger row with `provider: "scripted"`, `tokensIn > 0` and the embedding model is written, and no network connection is opened

#### Scenario: Same text, same vector
- **WHEN** the scripted embedder embeds the same passage text twice in different runs
- **THEN** both vectors are identical and have unit length

### Requirement: Test mode labels requests with their purpose
In test mode only, every provider request SHALL carry an `X-Horizon-Purpose` header with the call's purpose. Outside test mode the header SHALL never be sent.

#### Scenario: Normal mode
- **WHEN** a chat request is built outside test mode
- **THEN** it has no `X-Horizon-Purpose` header

### Requirement: Canned responses per purpose in test mode
The fake provider SHALL answer chat requests for a purpose with that purpose's selected canned responses, in turn, in the requested streaming or complete form, with real-shaped usage. A purpose with no selection SHALL keep the default answer. The committed canned sets SHALL include group A's 20 real profile drafts and real rolling summaries recorded by M8's summary suite.

#### Scenario: Canned drafts
- **WHEN** the `profile-drafts` set is selected for purpose `profile` and a naive draft job runs
- **THEN** the drafter receives the first recorded draft, and the draft validates

#### Scenario: Canned rolling summaries
- **WHEN** the rolling-summary set is selected for purpose `rolling_summary` and a test session's window drops
- **THEN** the summary task receives the first recorded summary, and a `rolling` row with that text is written

### Requirement: Decisions can be held in test mode
The fake provider SHALL hold the n-th decision request open until released, as it does for images and embeddings, so deadlines and late answers can be tested through the real gateway.

#### Scenario: Late answer through the gateway
- **WHEN** the next decision request is held past its 400 ms deadline and then released
- **THEN** the caller got the fallback at the deadline, and the ledger row is written after the release

### Requirement: Rolling summaries are labelled as summary spend
A rolling summary call SHALL carry purpose `rolling_summary` in ledger category `summary`, separate from watch's episode summary. It SHALL be labelled by the same purpose factory as every other call, so it never drains energy.

#### Scenario: Ledger row
- **WHEN** a naive session's summary call completes
- **THEN** its ledger row has `category: "summary"`, `purpose: "rolling_summary"`, the session's ID and no message ID

### Requirement: Follow plans and recaps are labelled at the source
A follow plan SHALL carry purpose `follow_plan` in ledger category `decision`, and a watch recap SHALL carry purpose `episode_summary` in category `summary`. Both SHALL be labelled by the shared purpose factory, so neither drains energy, and both count toward the daily cap.

#### Scenario: Follow-plan row
- **WHEN** an `agent` group's follow plan is answered
- **THEN** its ledger row has `category: "decision"`, `purpose: "follow_plan"` and the session's ID, and the call is listed on the trace of the reply it explains

### Requirement: A refused follow plan pauses nothing
A daily-cap refusal of a `follow_plan` request SHALL publish the cap event without pausing live sessions, as for the after-turn purposes; the next reply's own preflight takes the pause.

#### Scenario: Cap reached at the follow plan
- **WHEN** the daily cap is reached exactly when a follow plan is requested
- **THEN** no second reply is made, no `session.paused` event comes from the follow plan, and the next reply's preflight pauses the session

### Requirement: Debate calls are labelled at the source
A debate plan SHALL carry purpose `debate_plan` in ledger category `decision`; a rubric request purpose `rubric` (`decision`); a host line purpose `host` (`chat`); and the verdict prose purpose `verdict` (`chat`). Each SHALL be labelled by the shared purpose factory, never drain energy, and count toward the daily cap.

#### Scenario: A debate's rows
- **WHEN** an `agent` Standard debate with Auto host and Arbiter runs to its verdict
- **THEN** its ledger has `debate_plan` rows in category `decision`, one `rubric` row in `decision`, `host` rows and one `verdict` row in `chat`, and no character's energy moved for any of them

### Requirement: Debate deadlines and limits
`timeoutsMs.decision.debate_plan` (500 by default) SHALL be a deadline counted from `turn.end`. `timeoutsMs.decision.rubric` SHALL be 10,000, and a 429 on a rubric request SHALL be retried once after 1 s inside it. `timeoutsMs.verdict` SHALL be 30,000, the whole verdict prose call's limit. The mock's price table SHALL carry the same values.

#### Scenario: A rubric 429
- **WHEN** the first rubric request gets a 429
- **THEN** it is sent once more after 1 s, and a second 429 counts as a failed score

#### Scenario: Seed check
- **WHEN** the seed check runs
- **THEN** `seed/pricing.json` and the mock's price table agree on `debate_plan`, `rubric` and `verdict`

### Requirement: A refused debate plan pauses nothing
A daily-cap refusal of a `debate_plan` request SHALL publish the cap event without pausing; the member SHALL fall back to fixed order, and the next argument's own preflight SHALL take the pause.

#### Scenario: Cap reached at the debate plan
- **WHEN** the daily cap is reached exactly when a debate plan is requested
- **THEN** the next member is announced in fixed order, no `session.paused` comes from the plan, and the next argument's preflight pauses the session

### Requirement: Retrieval calls are labelled at the source
Jev call 2 SHALL be recorded with purpose `deep_check` as decision spend, and the query rewrite with purpose `query_rewrite` as chat spend, each linked to the message it serves. Neither SHALL drain energy. A call labelled with any other unknown purpose SHALL still be refused.

#### Scenario: A deep turn's ledger
- **WHEN** a deep 1:1 reply with a rewrite completes
- **THEN** the ledger holds one `query_rewrite` row (category `chat`), its `deep_check` rows (category `decision`) and its `query_embed` row, and the character's energy fell only by the reply's own drain

### Requirement: Retrieval deadlines and refusals
A `deep_check` request SHALL be read by `retrieval.agent.deepCheckMs` from when it was sent, and a `query_rewrite` call abandoned after `retrieval.agent.rewriteMs`. A `deep_check` request refused with HTTP 429 SHALL fall back at once with no retry. A late answer SHALL still be recorded and then discarded.

#### Scenario: One piece rate limited
- **WHEN** one of a turn's 8 `deep_check` requests returns HTTP 429
- **THEN** no retry is sent for it, and its System 1 row has `result: "fallback"`

#### Scenario: Slow rewrite
- **WHEN** the rewrite's response is held past `rewriteMs`
- **THEN** the turn searches the message and its two earlier lines, and the late call's ledger row exists

### Requirement: The memory guard purpose
`memory_guard` SHALL be a decision purpose, recorded in the `decision` category. Like `importance`, it SHALL retry once after a rate limit, and its deadline SHALL come from the decision timeouts.

#### Scenario: Ledger category
- **WHEN** a guard request is recorded
- **THEN** its ledger row's category is `decision` and its purpose is `memory_guard`

### Requirement: A call can be marked as never pausing sessions
A call's context SHALL say whether reaching the daily cap through it may pause live sessions. Calls made by memory pause runs and by window-drop indexing SHALL say it may not; every other call keeps today's behaviour.

#### Scenario: Refused run call
- **WHEN** a pause run's `memory` call is refused by the daily cap
- **THEN** `budget.reached` is published with sessions left running, and no session pauses
