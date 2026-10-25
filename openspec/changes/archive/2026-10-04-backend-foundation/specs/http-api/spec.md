# Spec Delta

## Purpose

Defines the REST conventions every backend route follows: base path, wire shapes validated against the shared contract schema, the error envelope and status mapping, pagination, idempotent POSTs, asset serving, the read routes that map to `HorizonClient` queries, and the test-only control routes.

## ADDED Requirements

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
- **`pricing`:** derived from the clock (peak Mon–Fri 09:00–12:00 and 14:00–18:00 local);
- **`energy.estReplyPoints`:** from config.

Until key handling exists, it SHALL report `openRouterKeyStatus: "missing"` and `demoMode: true`, whatever key is configured.

#### Scenario: Peak period
- **WHEN** the test clock is set to a Tuesday at 10:00 local time
- **THEN** `pricing.period` is `"peak"`, and `nextChangeAt` is 12:00 local that day

#### Scenario: Key ignored for now
- **WHEN** `OPENROUTER_API_KEY` is set in `.env`
- **THEN** settings still report `openRouterKeyStatus: "missing"` and `demoMode: true`, and the key is never read into a response

### Requirement: Demo-data reset route
`POST /api/v1/admin/reset-demo` with body `{ "confirm": true }` SHALL reset the demo data (see `demo-data`) and return 204. Any other body SHALL be rejected with `validation`.

#### Scenario: Unconfirmed reset
- **WHEN** `POST /admin/reset-demo` is sent with an empty body
- **THEN** it rejects with `validation`, and nothing changes

### Requirement: Test-only control routes
Routes under `/api/v1/_test/` SHALL exist only when `HORIZON_TEST=1`; otherwise they SHALL return 404.
- **`POST /_test/clock`:** freezes the server clock at a given instant, or advances it by a given number of milliseconds.
- **`POST /_test/scenario`:** rejects a scenario it does not support with `validation`.

#### Scenario: Not in normal runs
- **WHEN** the backend runs without `HORIZON_TEST=1` and `POST /_test/clock` is called
- **THEN** the response is 404

#### Scenario: Advance time
- **WHEN** in test mode the clock is frozen at `2026-10-03T03:00:00.000Z` and advanced by 3,600,000 ms
- **THEN** a world created next has `createdAt` `2026-10-03T04:00:00.000Z`
