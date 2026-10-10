## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Test mode labels requests with their purpose
In test mode only, every provider request SHALL carry an `X-Horizon-Purpose` header with the call's purpose. Outside test mode the header SHALL never be sent.

#### Scenario: Normal mode
- **WHEN** a chat request is built outside test mode
- **THEN** it has no `X-Horizon-Purpose` header

### Requirement: Canned responses per purpose in test mode
The fake provider SHALL answer chat requests for a purpose with that purpose's selected canned responses, in turn, in the requested streaming or complete form, with real-shaped usage. A purpose with no selection SHALL keep the default answer. The committed canned sets SHALL include group A's 20 real profile drafts.

#### Scenario: Canned drafts
- **WHEN** the `profile-drafts` set is selected for purpose `profile` and a naive draft job runs
- **THEN** the drafter receives the first recorded draft, and the draft validates

### Requirement: Decisions can be held in test mode
The fake provider SHALL hold the n-th decision request open until released, as it does for images and embeddings, so deadlines and late answers can be tested through the real gateway.

#### Scenario: Late answer through the gateway
- **WHEN** the next decision request is held past its 400 ms deadline and then released
- **THEN** the caller got the fallback at the deadline, and the ledger row is written after the release
