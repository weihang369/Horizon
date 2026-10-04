# Spec Delta

## MODIFIED Requirements

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

### Requirement: Test-only control routes
Routes under `/api/v1/_test/` SHALL exist only when `HORIZON_TEST=1`; otherwise they SHALL return 404.
- **`POST /_test/clock`:** freezes the server clock at a given instant, or advances it by a given number of milliseconds.
- **`POST /_test/scenario`:** rejects a scenario it does not support with `validation`.

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

## ADDED Requirements

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
