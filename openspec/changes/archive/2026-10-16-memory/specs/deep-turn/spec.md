# Spec Delta

## ADDED Requirements

### Requirement: Documents and recall share one deep run
A reply that goes deep for documents and recall SHALL build one query (with its one embedding and any rewrite) and run both searches and both sets of Jev checks in parallel. Cancelling the turn SHALL cancel both. Each part's fallback SHALL apply on its own: a documents fallback SHALL NOT drop recalled lines, nor the reverse.

#### Scenario: Both in parallel
- **WHEN** a 1:1 reply goes deep for both and its documents checks are late
- **THEN** the reply carries the documents fallback and the recalled lines its recall checks kept

#### Scenario: Stop during both
- **WHEN** Stop is sent while 8 passage checks and 6 recall checks are in flight
- **THEN** all 14 are recorded `cancelled` and no reply is written

### Requirement: The early embedding also serves recall
The user message's early embedding SHALL also start beside the plan when the session has indexed lines or a candidate has memories beyond its list with vectors. The search SHALL wait for it at most the agent wait, and never for a vector of a text made after the gate.

#### Scenario: Recall-only speaker
- **WHEN** a 1:1 speaker has no documents but the session has indexed lines
- **THEN** the message's embedding starts with Jev call 1, and there is one embedding call for the message
