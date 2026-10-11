## MODIFIED Requirements

### Requirement: Trace ownership
The backend SHALL own:
- the trace sections `model`, `energy`, `routing` and `system1`;
- the message's `usage`;
- `TurnTrace.calls`, with usage and calls derived from the ledger rows for that message.

A trace patch from an AI port that sets an owned section SHALL be rejected, and the rest of the patch SHALL still be applied. A later `insight` for the same message SHALL carry the full merged trace, and SHALL keep the stored engine name, versions and creation time when it carries no engine metadata of its own.

#### Scenario: Reply cost matches usage
- **WHEN** a live reply completes
- **THEN** its trace's `calls` include a `reply` entry whose `costUsd` equals the message's `usage.costUsd`, and both equal the ledger row's cost

#### Scenario: Engine tries to set energy
- **WHEN** a turn engine emits a trace patch containing an `energy` section and a `context` section
- **THEN** the emitted trace keeps the backend's `energy` section and includes the engine's `context` section

#### Scenario: Engine tries to set System 1
- **WHEN** a turn engine emits a trace patch containing `system1`
- **THEN** the patch's `system1` is dropped

## ADDED Requirements

### Requirement: The reply cap is chosen after the plan
The runtime SHALL choose a reply's `max_tokens` after retrieval and after the turn's plan is known, from the mode and whether the plan made the turn deep. With no plan, the turn SHALL use the quick cap. Prefetched turns SHALL follow the same rule.

#### Scenario: Prefetched debate opening
- **WHEN** a debate opening is prefetched in a `short` debate
- **THEN** its request's `max_tokens` is 200
