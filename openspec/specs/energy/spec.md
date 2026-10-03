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
Energy maths SHALL be pinned by language-neutral JSON fixtures in `backend/tests/fixtures/energy/`. The fixtures cover regen, drain, rounding, state, the top-up gate and the day roll. The TypeScript implementation SHALL pass every fixture.

#### Scenario: Fixture run
- **WHEN** the unit tests run
- **THEN** every case in the energy fixtures passes against `energy.ts`, and a deliberately broken threshold makes at least one case fail
