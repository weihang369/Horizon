# Spec Delta

## MODIFIED Requirements

### Requirement: Jev call 1 is one request with only the questions that apply
A turn's plan SHALL make at most one `turn_plan` request. In 1:1 it SHALL hold the emotion question for the speaker.
In group and watch it SHALL hold the who-speaks question when one is asked, the emotion question for each candidate,
and in watch "is the talk finished?". From M12 it SHALL also hold "needs documents?" for each candidate with a
searchable source, and, in 1:1 and when a group message is answered, "standalone?" and "English?" once when any
"needs documents?" is asked. Its state SHALL be the turn-plan state (see `conversation-context`) for that turn, with
the document titles of the candidates asked "needs documents?". The request SHALL be recorded as decision spend and
SHALL never drain energy.

#### Scenario: One request for the turn
- **WHEN** an `agent` 1:1 reply is planned for a character with no documents
- **THEN** exactly one `turn_plan` request is sent, with one question keyed `emotion_reply:{characterId}` and a state holding `mode`, `quoted_user`, `quoted_cast`, `quoted_latest` and `quoted_recent`

#### Scenario: No gate questions yet
- **WHEN** an `agent` 1:1 reply is planned for a character with no searchable source
- **THEN** the request holds no "needs documents?", "standalone?", "English?" or "needs something from earlier?" question

#### Scenario: The gates for a character with documents
- **WHEN** an `agent` 1:1 reply is planned for Amara, whose sources are keyword-only
- **THEN** the one request also holds `docs:chr_seedAmara`, `standalone` and `english`, and its state lists her document titles under `quoted_documents`

#### Scenario: A group's call 1
- **WHEN** an `agent` group of three with no mention is planned, and only one of them has documents
- **THEN** the one request holds `who_first`, three `emotion_reply:{characterId}` questions, one `docs:{characterId}` question, `standalone` and `english`

#### Scenario: Watch asks no rewrite questions
- **WHEN** a watch turn is planned for a cast where two characters have documents
- **THEN** the request holds two `docs` questions and no `standalone` or `english` question

## ADDED Requirements

### Requirement: The 1:1 plan takes the deep branch on its gate
In 1:1, when the speaker's "needs documents?" answer is at or above `t_gate`, the plan SHALL continue on its deep branch (see `deep-turn`) and return with the passages it kept, so the reply waits for the whole plan. Otherwise the plan SHALL end quick, as before.

#### Scenario: Deep 1:1 plan
- **WHEN** Amara's 1:1 gate answers p 0.8 with `t_gate` 0.35
- **THEN** the plan's graph path ends with the deep steps, and the reply request holds the kept passages

#### Scenario: Quick 1:1 plan
- **WHEN** her gate answers p 0.1
- **THEN** the plan's graph path ends at `route`, and no `deep_check` request is made

### Requirement: A planned reply in any mode carries its passages
A planned reply that went deep SHALL carry its kept passages, its outcome, its candidates and its query in its frozen plan, in every mode, and the reply engine SHALL read them from there. A planned reply that did not go deep SHALL carry none.

#### Scenario: Group second reply
- **WHEN** a group's second replier goes deep
- **THEN** its frozen plan holds its own kept passages, independent of the first reply's

### Requirement: Only the speaker's gate is used
In a plan that asked "needs documents?" about several candidates, only the speaker's own answer SHALL decide whether their reply goes deep. Every other candidate's gate answer SHALL be recorded as asked but not used.

#### Scenario: Group first slot
- **WHEN** a group plan asks `docs` about Amara and Mei and picks Mei
- **THEN** Mei's gate decides her reply's branch, and Amara's `docs` row is `not_used`
