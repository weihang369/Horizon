## MODIFIED Requirements

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
