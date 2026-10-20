# Spec Delta

<!-- CONDITIONAL (design D2, D16): applies only if the user switches at the gate task. If they keep jev-1.13, this
     file is deleted before archive. The id below is the expected candidate; task 0.3 replaces it with the verified id
     if it differs. -->

## MODIFIED Requirements

### Requirement: One call per state
All independent questions about the same state SHALL be sent in a single decision call to the pinned decision model (`typesafe/jev-1.14`, never an alias). The questions SHALL be built from the question bank. Before sending, the Decider SHALL check that the state plus the longest question is at most 30,000 tokens, counted as UTF-8 bytes ÷ 3, and that the request holds at most 64 questions. When either check fails, the request SHALL be treated as a failure with reason `too_large`, SHALL be logged with its purpose and size, and SHALL NOT be sent, reserved or recorded.

#### Scenario: Batched questions
- **WHEN** a caller asks a `choice`, a `noul` and a `score` question about one state
- **THEN** exactly one decision request is sent, and it contains all three questions

#### Scenario: Over budget
- **WHEN** the state is 31,000 tokens by the byte count
- **THEN** no request is sent, no ledger row is written, and the caller's fallback runs, or `DecisionUnavailable` is raised when there is none

#### Scenario: Too many questions
- **WHEN** a caller asks 65 questions about one small state
- **THEN** no request is sent, and the fallback runs with reason `too_large`

#### Scenario: The pinned id
- **WHEN** the backend starts from the shipped seed
- **THEN** every decision request names `typesafe/jev-1.14`
