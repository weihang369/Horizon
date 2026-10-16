# Spec Delta

## ADDED Requirements

### Requirement: The memory guard purpose
`memory_guard` SHALL be a decision purpose, recorded in the `decision` category. Like `importance`, it SHALL retry once after a rate limit, and its deadline SHALL come from the decision timeouts.

#### Scenario: Ledger category
- **WHEN** a guard request is recorded
- **THEN** its ledger row's category is `decision` and its purpose is `memory_guard`

### Requirement: A call can be marked as never pausing sessions
A call's context SHALL say whether reaching the daily cap through it may pause live sessions. Calls made by memory pause runs and by window-drop indexing SHALL say it may not; every other call keeps today's behaviour.

#### Scenario: Refused run call
- **WHEN** a pause run's `memory` call is refused by the daily cap
- **THEN** `budget.reached` is published with sessions left running, and no session pauses
