# session-event-sourcing Specification

## Purpose

Makes a session's event log the single source of truth: messages and session state are always derived from the events by one reducer, and the TypeScript and Python versions of that reducer must agree on shared fixtures and on every shipped seed session.

## Requirements

### Requirement: One reducer in two languages
The backend SHALL derive messages, participant state and session state from session events using the same rules as the frontend reducer. For every case in `backend/tests/fixtures/reducer/`, both the TypeScript and the Python reducer SHALL produce exactly the case's expected session and messages. The cases SHALL include a reaction for the character who is streaming, before and after its first token, and the seed case `ses_seedDinner` seq 25.

#### Scenario: Shared fixture run
- **WHEN** the Python tests run the reducer fixtures
- **THEN** every case passes, and so does the TypeScript fixture test on the same files

#### Scenario: Divergence is caught
- **WHEN** one reducer's handling of a later `insight` is changed to keep the first trace
- **THEN** the `insight-replacement` case fails in that language

#### Scenario: Speaker's face kept against a reaction
- **WHEN** both reducers run the case where a reaction for Rin arrives 10 ms after Rin's own `turn.start`
- **THEN** both keep Rin's face unchanged, and both record the reaction on the message it reacts to

#### Scenario: Seed sessions still reduce
- **WHEN** every seed session is re-reduced after the speaker-face rule
- **THEN** each reduces to its shipped messages

### Requirement: Seed sessions reduce to their shipped messages
Reducing each seed session's `events.json` SHALL yield exactly its `messages.json`, in both languages. The backend SHALL refuse to import a seed whose reduction differs, and SHALL name the session in the error.

#### Scenario: Every seed session
- **WHEN** the seed is imported
- **THEN** every seed session's reduced messages equal its shipped messages, and the import succeeds

#### Scenario: Tampered seed
- **WHEN** one seed message's content is edited so that it no longer matches its events, and the import runs
- **THEN** the import fails with an error naming that session, and no seed rows are written

### Requirement: Served messages match the event log
For any session, the messages returned by the API SHALL equal the reduction of the events returned by the API for that session, apart from `trace`, which the snapshot leaves out.

#### Scenario: Replay equals snapshot
- **WHEN** a client reduces `GET /sessions/{id}/events` for a seed session
- **THEN** the result equals `GET /sessions/{id}/messages`

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

### Requirement: AI-owned per-message data is not event-sourced
Per-message data the AI derives (the stored query rewrites) SHALL be kept beside the messages, like turn traces, and SHALL NOT be projected from or written to the event log. Reducing a session's events SHALL NOT need it, and replaying them SHALL NOT recreate it. Forking SHALL copy the rows of the messages it copies, and deleting a message SHALL delete its row.

#### Scenario: Rebuilt from events
- **WHEN** a session with a stored rewrite is rebuilt from its event log
- **THEN** its messages are unchanged, and the stored rewrite is neither required nor recreated

#### Scenario: Message deleted
- **WHEN** a message with a stored rewrite is deleted
- **THEN** no row for it remains
