# Spec Delta

## ADDED Requirements

### Requirement: Retrieval calls are labelled at the source
Jev call 2 SHALL be recorded with purpose `deep_check` as decision spend, and the query rewrite with purpose `query_rewrite` as chat spend, each linked to the message it serves. Neither SHALL drain energy. A call labelled with any other unknown purpose SHALL still be refused.

#### Scenario: A deep turn's ledger
- **WHEN** a deep 1:1 reply with a rewrite completes
- **THEN** the ledger holds one `query_rewrite` row (category `chat`), its `deep_check` rows (category `decision`) and its `query_embed` row, and the character's energy fell only by the reply's own drain

### Requirement: Retrieval deadlines and refusals
A `deep_check` request SHALL be read by `retrieval.agent.deepCheckMs` from when it was sent, and a `query_rewrite` call abandoned after `retrieval.agent.rewriteMs`. A `deep_check` request refused with HTTP 429 SHALL fall back at once with no retry. A late answer SHALL still be recorded and then discarded.

#### Scenario: One piece rate limited
- **WHEN** one of a turn's 8 `deep_check` requests returns HTTP 429
- **THEN** no retry is sent for it, and its System 1 row has `result: "fallback"`

#### Scenario: Slow rewrite
- **WHEN** the rewrite's response is held past `rewriteMs`
- **THEN** the turn searches the message and its two earlier lines, and the late call's ledger row exists
