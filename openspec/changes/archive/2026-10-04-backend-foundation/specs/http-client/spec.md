# Spec Delta

## Purpose

Defines the frontend `HttpClient`, the `HorizonClient` implementation that talks to the local backend: how it is selected, how it maps HTTP failures to `HorizonError`, how it pages and subscribes, and how it behaves for methods whose backend milestone has not shipped yet.

## ADDED Requirements

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
- **WHEN** `chat.send` is called on the `HttpClient`
- **THEN** it rejects with `code: "validation"`, `retryable: false` and `details.availableIn: "M3"`, and no request is made
