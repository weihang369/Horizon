# Spec Delta

## MODIFIED Requirements

### Requirement: Shared energy fixtures
Energy maths SHALL be pinned by language-neutral JSON fixtures in `backend/tests/fixtures/energy/`. The fixtures cover regen, drain, rounding, state, the top-up gate, the day roll and changing the maximum. The TypeScript implementation and the Python implementation SHALL each pass every fixture.

#### Scenario: Fixture run
- **WHEN** the unit tests run
- **THEN** every case in the energy fixtures passes against `energy.ts`, and a deliberately broken threshold makes at least one case fail

#### Scenario: Python fixture run
- **WHEN** the backend unit tests run
- **THEN** every case in the same fixture file passes against the Python energy module within the file's tolerance

#### Scenario: Set-max cases
- **WHEN** the fixtures are run in either language
- **THEN** they include changing the maximum, which settles regeneration first and sets `regenPerHour` to `max / 24`, and both implementations pass them

## ADDED Requirements

### Requirement: Only a character's own reply drains its energy
A paid call with purpose `reply` SHALL drain the speaking character's energy by `ceil(cost / usdPerPoint − 1e-9)` points, settling regeneration and the day roll first. Current energy SHALL be clamped at 0, and the drained points SHALL be added to `spentToday`. The drain SHALL be applied in the same database transaction as the call's ledger row. No other purpose SHALL change energy.

#### Scenario: Reply drain
- **WHEN** a reply for a character with 500 ⚡ is recorded at $0.00042 with usdPerPoint $0.0001
- **THEN** the ledger row and the energy write commit together, and the character has 495 ⚡ with `spentToday` raised by 5

#### Scenario: Overdraft clamps
- **WHEN** a reply costing 12 points is recorded for a character with 3 ⚡
- **THEN** the character has 0 ⚡, and the reply is not cut short

### Requirement: Energy writes are serialised per character
Writes to one character's energy (drain, top-up, set-max, correction) SHALL be serialised so that none of them is lost when they race.

#### Scenario: Top-up races a drain
- **WHEN** a +500 top-up and a 5-point reply drain for the same character are applied concurrently, starting from 100 ⚡
- **THEN** the character ends with 595 ⚡ (allowing for regeneration in between)

### Requirement: Demo mode freezes energy writes
While `demoMode` is true, no energy write SHALL apply regeneration or a drain: stored energy stays as it is.

#### Scenario: Set-max in demo mode
- **WHEN** in demo mode the max of a character with 300 ⚡ stored a day ago is set to 1200
- **THEN** it still has 300 ⚡: no regeneration was applied by the write

### Requirement: Top-up route
`POST /api/v1/characters/{id}/energy/top-up` with `{ points }`, where `points` is a positive integer, SHALL:
- require a usable key (`missing_key` with none, `invalid_key` with a rejected one);
- apply the top-up gate;
- add the points (they may exceed max);
- write the `energy_topup` ledger row in the same transaction;
- return the character's wire `Energy`.

A refused top-up SHALL leave energy and the ledger unchanged. An unknown character SHALL get `not_found`.

#### Scenario: Two large top-ups under a small cap
- **WHEN** the daily cap is $0.60 with nothing spent, and the user tops up a character +5000 twice
- **THEN** the first returns the raised energy, and the second rejects with `daily_budget_exceeded`, leaving energy at the first result

#### Scenario: No key
- **WHEN** no key is set and a top-up is requested
- **THEN** it rejects with `missing_key`

### Requirement: Set-max route
`PUT /api/v1/characters/{id}/energy/max` with `{ points }`, where `points` is a positive integer, SHALL settle regeneration and then set the maximum. Regeneration becomes `points / 24` per hour. Current energy SHALL be unchanged, even when it is above the new maximum. The route SHALL return the wire `Energy`, and it SHALL NOT require a key.

#### Scenario: Lower the max
- **WHEN** a character with 800 ⚡ of 1000 has its max set to 500
- **THEN** it has 800 ⚡ of 500, `regenPerHour` 20.833…, and no `fullAt`
