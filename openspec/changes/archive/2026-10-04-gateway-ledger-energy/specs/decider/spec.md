# Spec Delta

## Purpose

The Decider is the only way the backend asks a bounded question (route, gate, rerank, guardrail, emotion, scoring) (D-66). It batches the questions about one state into a single Jev call, validates every answer and falls back deterministically, so callers always get an answer or an explicit "unavailable".

## ADDED Requirements

### Requirement: One call per state
All independent questions about the same state SHALL be sent in a single decision call to the pinned decision model (`typesafe/jev-1.13`, never an alias). Before sending, the Decider SHALL check that the state plus the longest question fits the 32K-token budget. When it doesn't fit, the request SHALL be treated as a failure and SHALL NOT be sent.

#### Scenario: Batched questions
- **WHEN** a caller asks a `choice`, a `noul` and a `score` question about one state
- **THEN** exactly one decision request is sent, and it contains all three questions

#### Scenario: Over budget
- **WHEN** the state is 40,000 tokens
- **THEN** no request is sent, and the caller's fallback runs, or `DecisionUnavailable` is raised when there is none

### Requirement: Answers are validated individually
Each answer SHALL be checked against its question's declared type and option set:
- a `choice` must be one of the options;
- a `noul` must be a probability between 0 and 1;
- a `score` must be within the declared levels.

When only some answers are invalid, the fallback SHALL run only for those questions. Each answer SHALL be marked with its source: `jev`, `fallback` or `fixture`.

#### Scenario: One bad answer
- **WHEN** Jev answers `route` with an option that was not offered, and answers `gate` validly
- **THEN** `route` comes from the fallback with source `fallback`, and `gate` keeps its Jev answer with source `jev`

### Requirement: Failure and timeout fall back
When the call fails or exceeds its purpose's timeout, the Decider SHALL return the caller's fallback answers. With no fallback it SHALL raise `DecisionUnavailable`. A response that arrives after the timeout SHALL be discarded, but its cost SHALL still be recorded in the ledger.

#### Scenario: Late answer
- **WHEN** a `route` decision's response arrives at 650 ms against a 400 ms timeout
- **THEN** the caller has already received the fallback answer, the late answer is not used, and one `decision` ledger row records the call's cost

#### Scenario: No fallback
- **WHEN** a decision with no fallback fails with `provider_error`
- **THEN** the caller receives `DecisionUnavailable`

### Requirement: Decisions are recorded as decision spend
Every decision call SHALL be recorded in the ledger with `category: "decision"` and the caller's purpose. It SHALL NOT drain any character's energy.

#### Scenario: Gate decision
- **WHEN** a `gate` decision completes for a character
- **THEN** a `decision` row with `purpose: "gate"` exists, and the character's energy is unchanged

### Requirement: Scripted fixtures
The Decider SHALL accept scripted answers keyed by purpose and question. When a scripted answer exists for a question, it SHALL return that answer with source `fixture`, without a network call, and it SHALL NOT write a ledger row for it.

#### Scenario: Fixture answer
- **WHEN** a fixture scripts `route` → `chr_seedAmara` and the Decider is asked `route`
- **THEN** the answer is `chr_seedAmara` with source `fixture`, no request is sent, and no ledger row is written
