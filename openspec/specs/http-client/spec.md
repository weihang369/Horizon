# http-client Specification

## Purpose

Defines the frontend `HttpClient`, the `HorizonClient` implementation that talks to the local backend: how it is selected, how it maps HTTP failures to `HorizonError`, how it pages and subscribes, and how it behaves for methods whose backend milestone has not shipped yet.

## Requirements

### Requirement: Client selection
The app SHALL use the `HttpClient` against `/api/v1` when it is built or served with `VITE_HORIZON_CLIENT=http`, and the MockClient otherwise. A build without that variable (the Vercel build) SHALL make no backend requests. Mock-only dev controls SHALL be absent under the `HttpClient`.

#### Scenario: Default stays mock
- **WHEN** the frontend is built with no `VITE_HORIZON_CLIENT`
- **THEN** `client.kind` is `"mock"`, and no request to `/api/` is made while the seed worlds are browsed

#### Scenario: HTTP selected
- **WHEN** the dev server runs with `VITE_HORIZON_CLIENT=http`
- **THEN** `client.kind` is `"http"`, and the world list comes from `GET /api/v1/worlds`

### Requirement: Errors become HorizonErrors
Every non-2xx response SHALL reject with a `HorizonError` built from the error envelope, keeping `code`, `message`, `retryable`, `retryAfterSec` and `details`. A request that cannot reach the server SHALL reject with `code: "network"` and `retryable: true`.

#### Scenario: Conflict details survive
- **WHEN** creating a world with a duplicate name returns 409 with `details`
- **THEN** the promise rejects with a `HorizonError` whose `code` is `"conflict"` and whose `details` equal the response's

#### Scenario: Backend down
- **WHEN** the backend is not running and `worlds.list()` is called
- **THEN** it rejects with `code: "network"`

### Requirement: Lists are complete
Methods that return arrays from paginated routes SHALL follow `nextCursor` until it is `null`, and SHALL resolve with every item in order.

#### Scenario: Long seed session
- **WHEN** `sessions.events(id)` is called for a session with more events than one page
- **THEN** it resolves with all of them, ordered by `seq`

### Requirement: One idempotency key per user action
Every `POST` the `HttpClient` sends SHALL carry a fresh `Idempotency-Key`. A retry of the same call SHALL reuse that key.

#### Scenario: Create retried after a dropped response
- **WHEN** `worlds.create` is retried because the first response was lost
- **THEN** both requests carry the same key, and one world exists

### Requirement: Subscriptions use at most two streams
`onGlobal` SHALL share a single global event stream. `sessions.subscribe` SHALL open at most one session stream at a time. After a reconnect, a subscriber SHALL NOT receive an event whose `seq` it has already received.

#### Scenario: Reconnect without duplicates
- **WHEN** the session stream drops after `seq 20` and reconnects
- **THEN** the subscriber's next event has `seq 21`

#### Scenario: Shared global stream
- **WHEN** three components call `onGlobal`
- **THEN** one global stream is open, and each callback receives every event

### Requirement: Methods without a backend yet
A `HorizonClient` method whose backend milestone has not shipped SHALL reject immediately, without sending a request, with a non-retryable `HorizonError` (`code: "validation"`). Its message SHALL say the feature is not available on the local backend yet, and `details.availableIn` SHALL name the milestone.

#### Scenario: Sending a chat message in M1b
- **WHEN** a method from a milestone the backend has not shipped is called on the `HttpClient` (`chat.send` before M3; `characters.addKnowledge` from M4 until M5)
- **THEN** it rejects with `code: "validation"`, `retryable: false` and `details.availableIn` naming that milestone (`"M3"` for `chat.send` before M3, `"M5"` for `characters.addKnowledge`), and no request is made

### Requirement: Settings and energy over HTTP
The `HttpClient` SHALL implement the following methods against the backend:
- `settings.update` → `PATCH /settings`;
- `settings.setKey` → `PUT /settings/key`;
- `settings.testConnection` → `POST /settings/test-connection`;
- `settings.testModel` → `POST /settings/test-model`;
- `characters.topUpEnergy` → `POST /characters/{id}/energy/top-up`;
- `characters.setEnergyMax` → `PUT /characters/{id}/energy/max`.

None of these methods SHALL reject as "not available yet". Every `POST` among them SHALL carry an `Idempotency-Key`.

#### Scenario: Top-up over HTTP
- **WHEN** `characters.topUpEnergy("chr_seedHana", 500)` is called with a key set
- **THEN** one `POST /characters/chr_seedHana/energy/top-up` is sent with an `Idempotency-Key`, and the returned `Energy` is shown

#### Scenario: Top-up refused
- **WHEN** a top-up is refused by the backend with 402 `daily_budget_exceeded`
- **THEN** the method rejects with a `HorizonError` whose `code` is `daily_budget_exceeded`

#### Scenario: Not pending any more
- **WHEN** `settings.setKey` is called on the `HttpClient`
- **THEN** a `PUT /settings/key` request is sent, and the method does not reject with `details.availableIn: "M2"`

### Requirement: Sessions and commands over HTTP
The `HttpClient` SHALL implement, against the session routes:
- `sessions` `create`, `rename`, `delete`, `forkSeedSession`, `export`, `leave` and `end`;
- every `chat`, `debate` and `watch` command.

None of these SHALL reject as "not available yet". Every `POST` among them SHALL carry an `Idempotency-Key`. A command SHALL resolve when the backend accepts it (202). Its effects SHALL arrive through `sessions.subscribe`.

#### Scenario: Send over HTTP
- **WHEN** `chat.send(sid, "hello")` is called on a live 1:1 session
- **THEN** one `POST /sessions/{sid}/send` is sent with an `Idempotency-Key`, the promise resolves, and the user message and reply arrive through `sessions.subscribe`

#### Scenario: Conflict surfaces with details
- **WHEN** `sessions.create` is refused because another session is streaming
- **THEN** it rejects with a `HorizonError` whose `code` is `conflict` and whose `details.activeSessionId` names the live session

#### Scenario: Export as text
- **WHEN** `sessions.export("ses_seedDebate4Day")` is called
- **THEN** it resolves with the Markdown body as a string

### Requirement: Characters, jobs and covers over HTTP
The `HttpClient` SHALL implement, against the backend routes:
- `characters` `createDraft`, `update`, `lockPortrait`, `approve`, `archive`, `restore`, `delete` and `acceptAssetVersion`;
- `jobs` `estimate`, `start`, `cancel` and `retryTask`;
- `worlds.uploadCover`, as a `multipart/form-data` request with one `file` part.

None of these SHALL reject as "not available yet". Every `POST` among them SHALL carry an `Idempotency-Key`.

#### Scenario: Upload a cover over HTTP
- **WHEN** `worlds.uploadCover("wld_seedMeridian", pngFile)` is called
- **THEN** one multipart `POST /worlds/wld_seedMeridian/cover` is sent with an `Idempotency-Key`, and the returned `World` has `cover.kind: "upload"`

#### Scenario: Start a job over HTTP
- **WHEN** `jobs.start({ characterId, kind: "portrait_candidates" })` is called with a key set
- **THEN** one `POST /jobs` is sent, it resolves with the `GenerationJob`, and `jobs.subscribe` on its ID delivers its `task.update` and `job.done` events from the global stream
