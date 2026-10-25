# decider Specification

## Purpose

The Decider is the only way the backend asks a bounded question (route, gate, rerank, guardrail, emotion, scoring) (D-66). It batches the questions about one state into a single Jev call, validates every answer and falls back deterministically, so callers always get an answer or an explicit "unavailable".

## Requirements

### Requirement: One call per state
All independent questions about the same state SHALL be sent in a single decision call to the pinned decision model (`typesafe/jev-1.13`, never an alias). The questions SHALL be built from the question bank. Before sending, the Decider SHALL check that the state plus the longest question is at most 30,000 tokens, counted as UTF-8 bytes ÷ 3, and that the request holds at most 64 questions. When either check fails, the request SHALL be treated as a failure with reason `too_large`, SHALL be logged with its purpose and size, and SHALL NOT be sent, reserved or recorded.

#### Scenario: Batched questions
- **WHEN** a caller asks a `choice`, a `noul` and a `score` question about one state
- **THEN** exactly one decision request is sent, and it contains all three questions

#### Scenario: Over budget
- **WHEN** the state is 31,000 tokens by the byte count
- **THEN** no request is sent, no ledger row is written, and the caller's fallback runs, or `DecisionUnavailable` is raised when there is none

#### Scenario: Too many questions
- **WHEN** a caller asks 65 questions about one small state
- **THEN** no request is sent, and the fallback runs with reason `too_large`

### Requirement: Answers are validated individually
Each answer SHALL be checked against its question's declared type and option set:
- a `choice` must be one of the options;
- a `noul` must be a probability between 0 and 1;
- a `score` must be within the declared levels (0 … n−1).

When only some answers are invalid, the fallback SHALL run only for those questions. Each answer SHALL be marked with its source: `jev`, `fallback` or `fixture`.

#### Scenario: One bad answer
- **WHEN** Jev answers `route` with an option that was not offered, and answers another question in the same request validly
- **THEN** `route` comes from the fallback with source `fallback`, and the other question keeps its Jev answer with source `jev`

### Requirement: Failure and timeout fall back
A decision SHALL be started once and read by deadline:
- reading it by an absolute virtual-clock deadline SHALL return the answers if they are back by then, else the caller's fallback, run once;
- reading it in full SHALL return the real answers whenever they land.

With no fallback, a failure or a missed deadline SHALL raise `DecisionUnavailable`. A response that lands after a deadline SHALL still be recorded in the ledger, and SHALL stay readable in full.

#### Scenario: Late answer
- **WHEN** a `route` decision's response arrives at 650 ms against a 400 ms deadline
- **THEN** the caller has already received the fallback answer, the late answer is not used for that deadline, and one `decision` ledger row records the call's cost

#### Scenario: Deadline then full answer
- **WHEN** a decision is read by a 500 ms deadline, which passes, and the response lands at 620 ms
- **THEN** the deadline read returned the fallback, the full read returns Jev's answers, and exactly one request and one ledger row exist

#### Scenario: No fallback
- **WHEN** a decision with no fallback fails with `provider_error`
- **THEN** the caller receives `DecisionUnavailable`

### Requirement: Scripted fixtures
The Decider SHALL accept scripted answers keyed by purpose and question. When a scripted answer exists for a question, it SHALL return that answer with source `fixture`, without a network call, and it SHALL NOT write a ledger row for it.

#### Scenario: Fixture answer
- **WHEN** a fixture scripts `route` → `chr_seedAmara` and the Decider is asked `route`
- **THEN** the answer is `chr_seedAmara` with source `fixture`, no request is sent, and no ledger row is written

### Requirement: Decision calls are decision spend
Every decision call SHALL be recorded in the ledger with `category: "decision"` and the caller's purpose. It SHALL NOT drain any character's energy. The decision purposes SHALL include `turn_plan`, `reaction` and `face_check`.

#### Scenario: Route decision
- **WHEN** a `route` decision completes for a session
- **THEN** a `decision` row with `purpose: "route"` exists, and no character's energy changes

#### Scenario: Turn plan and face check
- **WHEN** an `agent` 1:1 reply with a non-neutral face completes and its face check answers
- **THEN** one `decision` row with `purpose: "turn_plan"` and one with `purpose: "face_check"` exist, and the character's energy changed only by the reply's drain

### Requirement: Cancelling a decision detaches its readers
Cancelling a started decision (Stop, leaving, a cap pause or the end of a session) SHALL make its pending readers fail with a cancellation, without running the fallback. The request already sent SHALL complete and be recorded at the provider's cost. Only shutdown and factory reset SHALL abort requests in flight, which are then recorded at their estimate.

#### Scenario: Stop during a decision
- **WHEN** a session is stopped while a decision is in flight, and the response lands 200 ms later
- **THEN** no fallback runs, nothing in the session uses the answer, and the ledger row carries the provider's cost

### Requirement: Rate limits fall back on the hot path and retry in the background
A `rate_limited` failure SHALL fall back at once for every purpose except `importance`, `memory_guard` and `rubric`. Those SHALL wait the larger of 1 s and the provider's Retry-After, up to 5 s, and send once more if their deadline allows it.

#### Scenario: Hot path
- **WHEN** a `route` decision gets HTTP 429
- **THEN** the fallback answers at once, and no second request is sent

#### Scenario: Background purpose
- **WHEN** an `importance` decision gets HTTP 429 and its retry succeeds
- **THEN** the answer is Jev's, two requests were sent, and one ledger row exists

### Requirement: Deadlines are looked up per question
Each question's deadline SHALL come from its bank entry's deadline key, looked up in the decision timeouts, defaulting to its purpose. Two questions of one purpose MAY have different deadlines (the output check and the prompt checks under `guardrail`).

#### Scenario: Prompt check deadline
- **WHEN** a `guardrail` question whose deadline key is `guardrail_prompt` is asked
- **THEN** its deadline is 1,500 ms, not the output check's 700 ms

### Requirement: Decision requests are runtime tasks
Each decision request SHALL run as a task started by the runtime's task factory, so a virtual-clock advance waits for it to settle.

#### Scenario: Advance waits for a late answer
- **WHEN** in test mode a parked decision is released and the clock is advanced
- **THEN** the advance returns only after the decision's ledger row is written
