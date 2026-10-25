## MODIFIED Requirements

### Requirement: Jev call 1 is one request with only the questions that apply
A turn's plan SHALL make at most one `turn_plan` request. In 1:1 it SHALL hold the emotion question for the speaker.
In group and watch it SHALL hold the who-speaks question when one is asked, the emotion question for each candidate,
and in watch "is the talk finished?". From M12 it SHALL also hold "needs documents?" for each candidate with a
searchable source, and, in 1:1 and when a group message is answered, "standalone?" and "English?" once when any
"needs documents?" is asked. From M14 it SHALL also hold "unsafe request?" once about a user-written line with no
stored safety answer, and in 1:1, group and Step in "at risk?" beside it. Its state SHALL be the turn-plan state (see
`conversation-context`) for that turn, with the document titles of the candidates asked "needs documents?". The
request SHALL be recorded as decision spend and SHALL never drain energy.

#### Scenario: One request for the turn
- **WHEN** an `agent` 1:1 reply is planned for a character with no documents, for a message already checked
- **THEN** exactly one `turn_plan` request is sent, with one question keyed `emotion_reply:{characterId}` and a state holding `mode`, `quoted_user`, `quoted_cast`, `quoted_latest` and `quoted_recent`

#### Scenario: No gate questions yet
- **WHEN** an `agent` 1:1 reply is planned for a character with no searchable source
- **THEN** the request holds no "needs documents?", "standalone?", "English?" or "needs something from earlier?" question

#### Scenario: The gates for a character with documents
- **WHEN** an `agent` 1:1 reply is planned for Amara, whose sources are keyword-only
- **THEN** the one request also holds `docs:chr_seedAmara`, `standalone` and `english`, and its state lists her document titles under `quoted_documents`

#### Scenario: A group's call 1
- **WHEN** an `agent` group of three with no mention is planned for a message already checked, and only one of them has documents
- **THEN** the one request holds `who_first`, three `emotion_reply:{characterId}` questions, one `docs:{characterId}` question, `standalone` and `english`

#### Scenario: Watch asks no rewrite questions
- **WHEN** a watch turn is planned for a cast where two characters have documents
- **THEN** the request holds two `docs` questions and no `standalone` or `english` question

#### Scenario: A new message is checked in the same request
- **WHEN** an `agent` 1:1 reply is planned for a message with no stored safety answer
- **THEN** the one request also holds `unsafe_request` and `at_risk`, and no second request is made

## ADDED Requirements

### Requirement: The plan carries the safety cue
The frozen plan SHALL carry the safety decision that applies to its reply (no cue, steer, care, or both, with the stored probabilities), so a replayed turn needs no Jev call and a regenerate uses the stored answer.

#### Scenario: Replay from the plan
- **WHEN** a steered turn's frozen plan is replayed with the Decider unavailable
- **THEN** the reply's request carries the steer sentence, and no decision request is made
