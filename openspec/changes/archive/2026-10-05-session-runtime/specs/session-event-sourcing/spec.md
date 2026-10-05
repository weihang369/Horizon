# Spec Delta

## ADDED Requirements

### Requirement: Live sessions stay event-sourced
Every live change to a session SHALL be written as session events. The stored session and messages SHALL be updated from those events by the shared reducer, in the same transaction. A crash SHALL never leave events without their projection, or the reverse. After any live exchange, the served messages SHALL equal the reduction of the served events (apart from `trace`).

#### Scenario: Live exchange reduces to the snapshot
- **WHEN** a live 1:1 exchange with a greeting, a send, a reply and a regenerate has finished
- **THEN** reducing `GET /sessions/{id}/events` yields exactly `GET /sessions/{id}/messages`, variants included

#### Scenario: Interrupted streams at startup
- **WHEN** the backend stops while a reply is streaming and starts again
- **THEN** the message is closed as `interrupted` by stored events, and the reduction still equals the snapshot

### Requirement: Fork is identical in both languages
Forking a session's events at a playhead SHALL produce the same events, renamed IDs, renumbered `seq` and reduced messages in the backend as in the MockClient. For every case in `backend/tests/fixtures/fork/`, both implementations SHALL produce exactly the case's expected output, with the new session ID taken from the case.

#### Scenario: Fork fixture in both languages
- **WHEN** the Python and TypeScript tests run the fork fixtures, including a cut that lands mid-stream
- **THEN** every case passes in both languages, and the mid-stream case's cut extends to that turn's `turn.end`
