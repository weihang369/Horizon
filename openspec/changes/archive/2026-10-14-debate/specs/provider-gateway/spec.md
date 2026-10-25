# Spec Delta

## ADDED Requirements

### Requirement: Debate calls are labelled at the source
A debate plan SHALL carry purpose `debate_plan` in ledger category `decision`; a rubric request purpose `rubric` (`decision`); a host line purpose `host` (`chat`); and the verdict prose purpose `verdict` (`chat`). Each SHALL be labelled by the shared purpose factory, never drain energy, and count toward the daily cap.

#### Scenario: A debate's rows
- **WHEN** an `agent` Standard debate with Auto host and Arbiter runs to its verdict
- **THEN** its ledger has `debate_plan` rows in category `decision`, one `rubric` row in `decision`, `host` rows and one `verdict` row in `chat`, and no character's energy moved for any of them

### Requirement: Debate deadlines and limits
`timeoutsMs.decision.debate_plan` (500 by default) SHALL be a deadline counted from `turn.end`. `timeoutsMs.decision.rubric` SHALL be 10,000, and a 429 on a rubric request SHALL be retried once after 1 s inside it. `timeoutsMs.verdict` SHALL be 30,000, the whole verdict prose call's limit. The mock's price table SHALL carry the same values.

#### Scenario: A rubric 429
- **WHEN** the first rubric request gets a 429
- **THEN** it is sent once more after 1 s, and a second 429 counts as a failed score

#### Scenario: Seed check
- **WHEN** the seed check runs
- **THEN** `seed/pricing.json` and the mock's price table agree on `debate_plan`, `rubric` and `verdict`

### Requirement: A refused debate plan pauses nothing
A daily-cap refusal of a `debate_plan` request SHALL publish the cap event without pausing; the member SHALL fall back to fixed order, and the next argument's own preflight SHALL take the pause.

#### Scenario: Cap reached at the debate plan
- **WHEN** the daily cap is reached exactly when a debate plan is requested
- **THEN** the next member is announced in fixed order, no `session.paused` comes from the plan, and the next argument's preflight pauses the session
