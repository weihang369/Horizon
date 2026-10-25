# Spec Delta

## MODIFIED Requirements

### Requirement: Test-only control routes
Routes under `/api/v1/_test/` SHALL exist only when `HORIZON_TEST=1`; otherwise they SHALL return 404.
- **`POST /_test/clock`:** freezes the server clock at a given instant, or advances it by a given number of milliseconds. While frozen, any wait in the backend SHALL last until the clock is advanced past its deadline. An advance SHALL wake due waits in deadline order, and SHALL respond only after the work they started has settled.
- **`POST /_test/scenario`:** applies `character_exhausted`, `rush_hour` or `stream_cut` as the MockClient does, and rejects a scenario it does not support with `validation`.
- **`POST /_test/ai-profile`:** sets the AI profile (`scripted` or `naive`) for subsequent turns, optionally with per-port overrides.
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

#### Scenario: Scenarios mirror the mock
- **WHEN** `rush_hour` is applied
- **THEN** `GET /settings` reports `pricing.period: "peak"` whatever the clock says, and `character_exhausted` sets Takeshi's energy to 0 without touching user-created sessions

#### Scenario: Stream cut
- **WHEN** `stream_cut` is applied and the next reply streams
- **THEN** the reply stops after about 24 tokens with an `error` event (`network`) and `turn.end { status: "interrupted", interruptedBy: "error" }`

#### Scenario: Decider fixture over HTTP
- **WHEN** the router is set to `naive`, a fixture answers the `route` question with a given participant, and a group message is sent
- **THEN** that participant answers first, the routing trace shows the fixture's choice, and no ledger row is written for the route

## ADDED Requirements

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
