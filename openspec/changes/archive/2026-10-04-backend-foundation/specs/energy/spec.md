# Spec Delta

## MODIFIED Requirements

### Requirement: Shared energy fixtures
Energy maths SHALL be pinned by language-neutral JSON fixtures in `backend/tests/fixtures/energy/`. The fixtures cover regen, drain, rounding, state, the top-up gate and the day roll. The TypeScript implementation and the Python implementation SHALL each pass every fixture.

#### Scenario: Fixture run
- **WHEN** the unit tests run
- **THEN** every case in the energy fixtures passes against `energy.ts`, and a deliberately broken threshold makes at least one case fail

#### Scenario: Python fixture run
- **WHEN** the backend unit tests run
- **THEN** every case in the same fixture file passes against the Python energy module within the file's tolerance

## ADDED Requirements

### Requirement: Energy is derived when read
A character read SHALL derive `energy.state` and `energy.fullAt` from the stored values and the current pricing period. `current` and `spentToday` SHALL be floored to integers on the wire. In demo mode (no key), energy SHALL be returned frozen as stored: no regeneration.

#### Scenario: Demo mode read
- **WHEN** a seed character is read in demo mode, a day after its energy was stored
- **THEN** `current` equals the stored value floored, and `state` follows the one-threshold rule for the current period

#### Scenario: Peak changes the state on read
- **WHEN** a character with 6 ⚡ stored is read at peak and then off-peak
- **THEN** it is `exhausted` at peak and not `exhausted` off-peak, with no write in between
