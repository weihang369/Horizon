## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Test-only control routes
Routes under `/api/v1/_test/` SHALL exist only when `HORIZON_TEST=1`; otherwise they SHALL return 404.
- **`POST /_test/clock`:** freezes the server clock at a given instant, or advances it by a given number of milliseconds. While frozen, any wait in the backend SHALL last until the clock is advanced past its deadline. An advance SHALL wake due waits in deadline order, and SHALL respond only after the work they started has settled.
- **`POST /_test/scenario`:** applies `character_exhausted`, `rush_hour`, `stream_cut`, `image_fail_partial`, `image_fail_all` or `song_fails` as the MockClient does, and rejects a scenario it does not support with `validation`.
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
