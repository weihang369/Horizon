# Spec Delta

## ADDED Requirements

### Requirement: Earlier-gate and recall rows
A reply whose plan asked "needs something from earlier?" SHALL carry one `earlier` row per candidate asked, `used` for the speaker and `not_used` for the others, comparing p against its `t_gate`. A reply that ran recall SHALL carry one `recall` row per checked candidate, about that line's message id or that memory's id and never its text, `used`, `below_threshold` or `fallback`.

#### Scenario: Recall rows
- **WHEN** a reply checked 6 recall candidates and kept 2
- **THEN** its trace has 6 `recall` rows, 2 `used`, each `about` a `msg_` or `mem_` id

#### Scenario: Forgotten memory row
- **WHEN** a memory named by a `recall` row is forgotten
- **THEN** that row is gone from the stored trace and from any later append

### Requirement: Pause runs are not in System 1
The Jev and DeepSeek calls of a memory pause run SHALL NOT add rows to any message's System 1 section. They SHALL appear only in the ledger and the AI-call log.

#### Scenario: After a run
- **WHEN** a pause run made importance and guard requests for a session
- **THEN** no message trace of that session gains a row from them
