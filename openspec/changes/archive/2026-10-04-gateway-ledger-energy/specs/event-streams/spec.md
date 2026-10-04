# Spec Delta

## MODIFIED Requirements

### Requirement: Changes are announced
After a write commits, the backend SHALL publish:
- `entity.changed { kind: "world", id, worldId }` when a world is created, renamed or deleted;
- `entity.changed { kind: "settings" }` when settings or the key are changed, or when the key status changes;
- `entity.changed { kind: "character", id, worldId }` when a character's energy is written (top-up, set-max, a reply drain or an energy correction);
- `mock.reset` after a demo-data reset.

An event SHALL NOT be published for a write that failed.

#### Scenario: World created
- **WHEN** a global subscriber is connected and a world is created
- **THEN** the subscriber receives `entity.changed` with `kind: "world"` and the new world's ID

#### Scenario: Reset announced
- **WHEN** demo data is reset
- **THEN** every connected global subscriber receives `{ "type": "mock.reset" }`

#### Scenario: Top-up announced
- **WHEN** a global subscriber is connected and a top-up succeeds for `chr_seedHana`
- **THEN** the subscriber receives `entity.changed` with `kind: "character"` and `id: "chr_seedHana"`

#### Scenario: Refused top-up is silent
- **WHEN** a top-up is refused by the gate
- **THEN** no `entity.changed` is published for it

## ADDED Requirements

### Requirement: Budget events on the global stream
The global stream SHALL carry `budget.warning { scope, spentUsd, capUsd }` when spend crosses a warning line, and `budget.reached { scope, spentUsd, capUsd, sessionId?, jobId? }` when a paid call is refused by a cap (see `budget-caps`). Each SHALL validate as a `GlobalEvent`.

#### Scenario: Warning delivered
- **WHEN** a recorded call moves daily spend across 80 % of the cap while a global subscriber is connected
- **THEN** the subscriber receives one `budget.warning` with `scope: "daily"`
