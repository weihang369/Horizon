# http-api Specification

## Purpose

Defines the REST conventions every backend route follows: base path, wire shapes validated against the shared contract schema, the error envelope and status mapping, pagination, idempotent POSTs, asset serving, the read routes that map to `HorizonClient` queries, and the test-only control routes.

## Requirements

### Requirement: Contract-shaped JSON
Every route SHALL live under `/api/v1` and use camelCase JSON in the shapes of the data contract. Optional fields SHALL be omitted, never `null`, unless the contract allows `null`. Every JSON response body and every SSE payload SHALL validate against `backend/horizon/contract/schema.json`.

#### Scenario: Responses validate
- **WHEN** the backend test suite calls every route in scope
- **THEN** each response body validates against its contract definition, and none contains a `null` the contract does not allow

### Requirement: Error envelope
Every non-2xx response SHALL have the body `{ "error": { code, message, retryable, retryAfterSec?, details? } }`, where `code` is a contract `ErrorCode`. The HTTP status SHALL follow the documented mapping:
- 404 → `not_found`;
- 409 → `conflict`;
- 400/413/422 → `validation`.

The framework's own validation errors SHALL be re-mapped to `validation` in this envelope.

#### Scenario: Unknown record
- **WHEN** `GET /api/v1/sessions/ses_nope` is requested
- **THEN** the status is 404, and the body is `{ "error": { "code": "not_found", "retryable": false, … } }`

#### Scenario: Schema-invalid body
- **WHEN** `POST /api/v1/worlds` is sent without `name`
- **THEN** the status is 422, the code is `validation`, and `details` names the invalid field

#### Scenario: Unknown route
- **WHEN** a path under `/api/v1` that no route matches is requested
- **THEN** the status is 404 with `code: "not_found"` in the envelope

### Requirement: Cursor pagination
`GET /sessions/{id}/messages`, `GET /sessions/{id}/events` and `GET /usage` SHALL return `{ items, nextCursor }`. `nextCursor` SHALL be an opaque string, or `null` on the last page. `limit` SHALL default to 200, and a value above 1,000 SHALL be rejected with `validation`. Following the cursors SHALL yield every record exactly once, in order.

#### Scenario: Paging a seed session
- **WHEN** a seed session's events are fetched with `limit=10`, following `nextCursor` until it is `null`
- **THEN** the concatenated items equal a single unpaged fetch, ordered by `seq`, with no gaps or duplicates

### Requirement: Idempotent POSTs
Every `POST` SHALL accept an `Idempotency-Key` header. Keys SHALL be kept for 24 hours and SHALL survive a restart:
- **same key, same body:** the stored status and body are returned without repeating the effect;
- **same key, different body:** the request is rejected with `conflict`;
- **same key while the first request is in flight:** the second request waits and returns the first one's result.

#### Scenario: Retried create
- **WHEN** `POST /api/v1/worlds` is sent twice with the same key and body
- **THEN** both responses are 201 with the same world, and only one world exists

#### Scenario: Reused key, different body
- **WHEN** the same key is sent with a different world name
- **THEN** the second request is rejected with 409 `conflict`

### Requirement: Asset serving
`GET /assets/{path}` SHALL serve the file from `data/assets/` if it exists there, and otherwise from `seed/assets/`, with a correct content type. Paths that escape those folders SHALL return 404. Files under `gen/` SHALL be served with `Cache-Control: public, max-age=31536000, immutable`.

#### Scenario: Seed portrait
- **WHEN** a seed character's `basePortraitUrl` is requested
- **THEN** the SVG is returned with `Content-Type: image/svg+xml`

#### Scenario: Traversal blocked
- **WHEN** `/assets/../data/horizon.db` (or an encoded equivalent) is requested
- **THEN** the response is 404

### Requirement: Read routes
The backend SHALL serve these `HorizonClient` queries with the documented routes:
- settings get;
- worlds list/get;
- characters list (excluding tombstones, archived only with `includeArchived=true`), get (tombstones included), assets, song, memory, knowledge, knowledge source;
- sessions list, get, messages, events, trace;
- usage list and summary;
- job get and active-job list.

#### Scenario: Archived and tombstoned characters
- **WHEN** a world's characters are listed with and without `includeArchived=true`
- **THEN** archived characters appear only with the flag, and tombstoned characters never appear, while `GET /characters/{id}` still returns a tombstone with `deletedAt` set

#### Scenario: Session snapshot
- **WHEN** `GET /api/v1/sessions/{id}` is requested for a seed session
- **THEN** it returns `{ session, messages, lastSeq }`, where `messages` omit `trace`, `lastSeq` is the highest event `seq`, and `GET /messages/{id}/trace` returns each trace

### Requirement: Settings are computed on read
`GET /settings` SHALL return a full `AppSettings`:
- **`spentTodayUsd`:** the sum of today's ledger costs in the configured time zone;
- **`pricing`:** derived from the clock (peak Mon–Fri 09:00–12:00 and 14:00–18:00 Malaysia time);
- **`energy.estReplyPoints`** and **`models.embedding`:** from config;
- **`openRouterKeyStatus`** and **`demoMode`:** from the key status (see `openrouter-key`).

The key itself SHALL never appear in the response.

#### Scenario: Peak period
- **WHEN** the test clock is set to a Tuesday at 10:00 Malaysia time
- **THEN** `pricing.period` is `"peak"`, and `nextChangeAt` is 12:00 Malaysia time that day

#### Scenario: Key ignored for now
- **WHEN** in test mode `OPENROUTER_API_KEY` is set in `.env` and no key has been saved
- **THEN** settings report `openRouterKeyStatus: "missing"` and `demoMode: true`, and the key is never read into a response

#### Scenario: Key status reported, key never returned
- **WHEN** a key is set and `GET /settings` is called
- **THEN** the response has `openRouterKeyStatus: "set"` and `demoMode: false`, and its body contains no `sk-or-` string

### Requirement: Demo-data reset route
`POST /api/v1/admin/reset-demo` with body `{ "confirm": true }` SHALL reset the demo data (see `demo-data`) and return 204. Any other body SHALL be rejected with `validation`.

#### Scenario: Unconfirmed reset
- **WHEN** `POST /admin/reset-demo` is sent with an empty body
- **THEN** it rejects with `validation`, and nothing changes

### Requirement: Test-only control routes
Routes under `/api/v1/_test/` SHALL exist only when `HORIZON_TEST=1`; otherwise they SHALL return 404.
- **`POST /_test/clock`:** freezes the server clock at a given instant, or advances it by a given number of milliseconds. While frozen, any wait in the backend SHALL last until the clock is advanced past its deadline. An advance SHALL wake due waits in deadline order, and SHALL respond only after the work they started has settled.
- **`POST /_test/scenario`:** applies `character_exhausted`, `rush_hour`, `stream_cut`, `image_fail_partial`, `image_fail_all`, `song_fails`, `no_worlds` or `daily_cap` as the MockClient does, and rejects a scenario it does not support with `validation`. Applying a scenario SHALL first clear every fault and override a previous scenario set, so scenarios replace each other as they do on the MockClient. `network_down` SHALL be rejected with `validation` and `details.clientSide: true`, because a client simulates it. In test mode, `POST /admin/reset-demo` SHALL also clear the active scenario's faults and overrides.
- **`POST /_test/ai-profile`:** sets the AI profile (`scripted` or `naive`) for subsequent turns and jobs, optionally with per-port overrides.
- **`POST /_test/decider-fixtures`:** sets or clears scripted Decider answers keyed by purpose and question.

In test mode, the provider SHALL be the in-process fake (see `provider-gateway`), so no test-mode request reaches the network.

#### Scenario: Not in normal runs
- **WHEN** the backend runs without `HORIZON_TEST=1` and `POST /_test/clock` is called
- **THEN** the response is 404

#### Scenario: Advance time
- **WHEN** in test mode the clock is frozen at `2026-10-03T03:00:00.000Z` and advanced by 3,600,000 ms
- **THEN** a world created next has `createdAt` `2026-10-03T04:00:00.000Z`

#### Scenario: Provider stand-in
- **WHEN** in test mode a key is set and `POST /settings/test-connection` is called
- **THEN** it succeeds from the fake provider, without any network access

#### Scenario: Advance drives a live session
- **WHEN** the clock is frozen, a 1:1 session is created, and `POST /_test/clock { advanceMs: 6000 }` returns
- **THEN** the greeting is already complete in `GET /sessions/{id}/messages`

#### Scenario: Advance drives a job
- **WHEN** the clock is frozen, a Lean `portrait_candidates` job is started, and `POST /_test/clock { advanceMs: 21000 }` returns
- **THEN** `GET /jobs/{id}` reports `succeeded`, and the candidate is `ready`

#### Scenario: Scenarios mirror the mock
- **WHEN** `rush_hour` is applied
- **THEN** `GET /settings` reports `pricing.period: "peak"` whatever the clock says, and `character_exhausted` sets Takeshi's energy to 0 without touching user-created sessions

#### Scenario: Stream cut
- **WHEN** `stream_cut` is applied and the next reply streams
- **THEN** the reply stops after about 24 tokens with an `error` event (`network`) and `turn.end { status: "interrupted", interruptedBy: "error" }`

#### Scenario: Decider fixture over HTTP
- **WHEN** the router is set to `naive`, a fixture answers the `route` question with a given participant, and a group message is sent
- **THEN** that participant answers first, the routing trace shows the fixture's choice, and no ledger row is written for the route

#### Scenario: No worlds
- **WHEN** a user world exists and `no_worlds` is applied
- **THEN** `GET /worlds` returns an empty list, settings and the key are unchanged, the ledger rows are still listed by `GET /usage`, and the global stream carries `mock.reset`

#### Scenario: Seed worlds come back after no worlds
- **WHEN** `no_worlds` is applied and then `POST /admin/reset-demo` is called
- **THEN** `GET /worlds` lists the two seed worlds with their shipped names, and the user world does not come back

#### Scenario: Daily cap reached
- **WHEN** a key is set, `daily_cap` is applied, and a top-up of 500 is requested for Hana
- **THEN** `GET /settings` reports `spentTodayUsd` equal to the daily cap, the top-up is refused with `daily_budget_exceeded`, and `GET /usage` lists no new ledger row

#### Scenario: Scenarios replace each other
- **WHEN** `rush_hour` is applied and then `stream_cut` is applied
- **THEN** `GET /settings` reports the clock's own pricing period again, and the next reply is cut

#### Scenario: Reset clears the scenario
- **WHEN** `daily_cap` is applied and then `POST /admin/reset-demo` is called in test mode
- **THEN** `GET /settings` reports `spentTodayUsd` equal to the ledger's own total for today

#### Scenario: Network down is client-side
- **WHEN** `POST /_test/scenario { "id": "network_down" }` is called
- **THEN** it rejects with `validation`, `details.clientSide` is `true`, and nothing changes on the backend

### Requirement: Settings update
`PATCH /api/v1/settings` with a partial `AppSettings` SHALL deep-merge the editable fields into `data/settings.local.json` and return the full `AppSettings`. The following fields are computed or config-owned and SHALL be ignored when present in the patch: `openRouterKeyStatus`, `demoMode`, `spentTodayUsd`, `pricing`, `models` (except `modelOverrides`), `energy.estReplyPoints`. An editable field with a value of the wrong type or out of range SHALL reject with `validation`, and nothing SHALL be written. A successful update SHALL publish `entity.changed { kind: "settings" }`.

#### Scenario: Read-only threshold ignored
- **WHEN** `PATCH /settings` sends `{ "energy": { "estReplyPoints": { "off_peak": 1, "peak": 1 } } }`
- **THEN** the response's `energy.estReplyPoints` is still `{ off_peak: 4, peak: 8 }`, and the file holds no `estReplyPoints`

#### Scenario: Lower the daily cap
- **WHEN** `PATCH /settings` sends `{ "budget": { "dailyCapUsd": 0.6 } }`
- **THEN** the response has `budget.dailyCapUsd: 0.6`, every other budget field is unchanged, and the change survives a restart

#### Scenario: Invalid value
- **WHEN** `PATCH /settings` sends `{ "budget": { "dailyCapUsd": -1 } }`
- **THEN** it rejects with `validation`, and settings are unchanged

### Requirement: Settings and energy write routes
The backend SHALL serve these routes, with their behaviour specified in `openrouter-key` and `energy`:

| Route | Response |
|---|---|
| `PUT /api/v1/settings/key` | `AppSettings` |
| `POST /api/v1/settings/test-connection` | `{ ok, latencyMs, creditsUsd? }` |
| `POST /api/v1/settings/test-model` | `{ ok, latencyMs, model }` |
| `POST /api/v1/characters/{id}/energy/top-up` | `Energy` |
| `PUT /api/v1/characters/{id}/energy/max` | `Energy` |

Every response SHALL validate against `schema.json`.

#### Scenario: Schema-valid energy response
- **WHEN** in test mode a top-up succeeds
- **THEN** the response validates as `Energy`, with integer `current` and `spentToday`

### Requirement: Session write routes
The backend SHALL serve the session lifecycle routes (see `session-lifecycle`):

| Route | Response |
|---|---|
| `POST /sessions` | 201 `SessionSnapshot` |
| `PATCH /sessions/{id}` `{ title }` | `Session` |
| `DELETE /sessions/{id}` | 204 |
| `POST /sessions/{id}/fork` `{ atSeq? }` | 201 `SessionSnapshot` |
| `POST /sessions/{id}/leave` | 204 |
| `POST /sessions/{id}/end` | 204 |
| `GET /sessions/{id}/export` | `text/markdown` |

Every JSON response SHALL validate against `schema.json`.

#### Scenario: Create returns a valid snapshot
- **WHEN** `POST /sessions` creates a group session
- **THEN** the response is 201 with a `SessionSnapshot` that validates against `schema.json`, and its `lastSeq` equals the highest stored event `seq`

### Requirement: Session command routes
Every chat, debate and watch command in doc 03 SHALL be served as `POST /sessions/{id}/…` and SHALL answer 202 with an empty JSON body when accepted. A command SHALL be rejected before acceptance for:
- an unknown session (404 `not_found`);
- a seed session (409 `conflict`);
- an ended session (409);
- a debate command in a non-debate session, or a watch command in a non-watch session (409);
- another live session (409, `details.activeSessionId`);
- no usable key (400 `missing_key`, or 401 `invalid_key`) for commands that generate;
- the daily cap still reached (402 `daily_budget_exceeded`) for commands that generate;
- empty text (422 `validation`).

#### Scenario: Send to a seed recording
- **WHEN** `POST /sessions/ses_seedAmaraHeadache/send { text: "hi" }` is sent with a key set
- **THEN** the response is 409 `conflict`, and no event is stored

#### Scenario: Accepted send
- **WHEN** a valid send reaches a live 1:1 session
- **THEN** the response is 202, the user's `message` event is already stored, and the reply follows on the session stream

#### Scenario: Retried command
- **WHEN** the same send is retried with the same `Idempotency-Key`
- **THEN** the stored 202 is returned, and only one user message exists

### Requirement: Character write routes
The backend SHALL serve the character write routes (see `character-lifecycle` and `generated-assets`):

| Route | Response |
|---|---|
| `POST /worlds/{worldId}/characters` `DraftInput` | 201 `{ character, job }` |
| `PATCH /characters/{id}` `CharacterPatch` | `Character` |
| `POST /characters/{id}/lock-portrait` `{ candidateId }` | `Character` |
| `POST /characters/{id}/approve`, `/archive`, `/restore` | `Character` |
| `DELETE /characters/{id}` | 204 |
| `POST /assets/{assetId}/accept` | `Character` |

Every JSON response SHALL validate against `schema.json`.

#### Scenario: Draft over HTTP
- **WHEN** `POST /worlds/wld_seedMeridian/characters` is sent with a key set
- **THEN** the response is 201 with a `draft` character and a `queued` or `running` `profile_draft` job, both valid against `schema.json`

#### Scenario: Command on a tombstone
- **WHEN** `PATCH /characters/chr_seedVictor` is sent after Victor was deleted
- **THEN** the response is 404 `not_found`

### Requirement: Job write routes
The backend SHALL serve `POST /jobs/estimate` (`StartJobInput` → `{ estimatedCostUsd }`), `POST /jobs` (201 `GenerationJob`), `POST /jobs/{id}/cancel` (`GenerationJob`) and `POST /jobs/{id}/tasks/{taskId}/retry` (`GenerationJob`). Unknown jobs or tasks SHALL be 404 `not_found`. `POST /jobs` SHALL reject before storing anything as described in `generation-jobs`.

#### Scenario: Start and read back
- **WHEN** `POST /jobs` starts a portrait job and `GET /jobs/{id}` is requested
- **THEN** both return the same job ID, and the job is listed by `GET /jobs?active=true` until it finishes

### Requirement: Cover upload route
`POST /worlds/{id}/cover` SHALL take `multipart/form-data` with one `file` part. A request whose declared length is over 5 MB SHALL be refused before its body is read, and the body SHALL also be counted while it is read, so an upload without a length can't exceed the limit. Both cases SHALL be 413 with the `validation` error.

#### Scenario: Chunked oversize upload
- **WHEN** a 6 MB file is sent without a `Content-Length` header
- **THEN** the response is 413 `validation`, and nothing is stored

### Requirement: Knowledge and memory write routes
The backend SHALL serve the knowledge and memory write routes (see `knowledge-sources` and `long-term-memory`):

| Route | Response |
|---|---|
| `POST /characters/{id}/knowledge`, multipart `file` or JSON `{ type: "text", title, text }` | 201 `KnowledgeSource` (`status: "indexing"`) |
| `DELETE /knowledge/{sourceId}` | 204 |
| `POST /knowledge/{sourceId}/reindex` | `KnowledgeSource` |
| `DELETE /memory/{memoryItemId}` | 204 |

Any other `Content-Type` on the knowledge route SHALL be `validation`. Unknown or tombstoned characters, sources and memories SHALL be 404 `not_found`. Every JSON response SHALL validate against `schema.json`.

#### Scenario: Pasted text over HTTP
- **WHEN** `POST /characters/chr_seedHana/knowledge` is sent with JSON `{ "type": "text", "title": "Notes", "text": "Rice first." }`
- **THEN** the response is 201 with a `KnowledgeSource` of `type: "text"` and `status: "indexing"`, valid against `schema.json`

#### Scenario: Unsupported body
- **WHEN** the knowledge route is called with `Content-Type: text/plain`
- **THEN** the response is 422 `validation`, and no source is created

#### Scenario: Forget over HTTP
- **WHEN** `DELETE /memory/{id}` is sent for an existing memory
- **THEN** the response is 204, and `GET /characters/{id}/memory` no longer lists it

### Requirement: Knowledge upload limit is enforced while reading
A knowledge upload whose declared length is over 10 MB SHALL be refused before its body is read. The body SHALL also be counted while it is read, so an upload without a length can't exceed the limit. Both cases SHALL be 413 with the `validation` error and `details.limit` of 10,485,760. The limit SHALL also hold for a request carrying an `Idempotency-Key`.

#### Scenario: Chunked oversize upload
- **WHEN** an 11 MB file is sent to the knowledge route without a `Content-Length` header
- **THEN** the response is 413 `validation` with `details.limit: 10485760`, and nothing is stored

#### Scenario: Keyed oversize upload
- **WHEN** an 11 MB file is sent with an `Idempotency-Key`
- **THEN** the response is 413 `validation`, and nothing is stored
