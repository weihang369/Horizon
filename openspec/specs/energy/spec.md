# energy Specification

## Purpose

Defines the character energy rules the UI and backend must compute identically: the single exhaustion threshold and the top-up gate. Both languages are pinned to shared fixtures.

## Requirements

### Requirement: One exhaustion threshold
A character SHALL be `exhausted` exactly when its current energy is below `estReplyPoints[period]` (4 off-peak, 8 at peak). The same threshold SHALL decide both the displayed state and whether the character may speak (D-78).

#### Scenario: Peak threshold
- **WHEN** a character has 6 ⚡ during peak pricing
- **THEN** its state is `exhausted`, and the next turn skips it with reason `exhausted`

#### Scenario: Off-peak threshold
- **WHEN** the same character has 6 ⚡ off-peak with max 1000
- **THEN** its state is `tired`, not `exhausted`

### Requirement: Top-up gate
A top-up of `points` SHALL be allowed only while `spentTodayUsd + (todayTopUpPoints + points) × usdPerPoint ≤ dailyCapUsd`, where `todayTopUpPoints` is the sum of today's top-ups. A refused top-up SHALL reject with `daily_budget_exceeded` (D-76).

#### Scenario: Repeated top-ups hit the gate
- **WHEN** with a $1.00 cap, $0.10 spent and usdPerPoint $0.0001, the user tops up +5000 and then +5000 again
- **THEN** the first succeeds, the second rejects with `daily_budget_exceeded`, and energy is unchanged by the second

### Requirement: Top-up is not spend
A successful top-up SHALL write one ledger row with `category: "energy_topup"`, `energyPoints: points` and `costUsd: 0`. It SHALL NOT increase `spentTodayUsd`.

#### Scenario: Ledger after top-up
- **WHEN** a +500 top-up succeeds
- **THEN** the newest ledger row is `energy_topup` with `energyPoints: 500` and `costUsd: 0`, and `settings.spentTodayUsd` is unchanged

### Requirement: Top-up dialog explains the gate
The top-up dialog SHALL say that top-ups are bounded by today's budget. On refusal, it SHALL show the `daily_budget_exceeded` message without closing silently.

#### Scenario: Refused top-up in the UI
- **WHEN** the user confirms a top-up that the gate refuses
- **THEN** the dialog shows the budget message, and the energy bar is unchanged

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

### Requirement: Energy is derived when read
A character read SHALL derive `energy.state` and `energy.fullAt` from the stored values and the current pricing period. `current` and `spentToday` SHALL be floored to integers on the wire. In demo mode (no key), energy SHALL be returned frozen as stored: no regeneration.

#### Scenario: Demo mode read
- **WHEN** a seed character is read in demo mode, a day after its energy was stored
- **THEN** `current` equals the stored value floored, and `state` follows the one-threshold rule for the current period

#### Scenario: Peak changes the state on read
- **WHEN** a character with 6 ⚡ stored is read at peak and then off-peak
- **THEN** it is `exhausted` at peak and not `exhausted` off-peak, with no write in between

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
