## MODIFIED Requirements

### Requirement: AI-owned per-message data is not event-sourced
Per-message data the AI derives (the stored query rewrites, and the stored safety answers for a user line) SHALL be kept beside the messages, like turn traces, and SHALL NOT be projected from or written to the event log. Reducing a session's events SHALL NOT need it, and replaying them SHALL NOT recreate it. Forking SHALL copy the rows of the messages it copies, and deleting a message SHALL delete its row.

#### Scenario: Rebuilt from events
- **WHEN** a session with a stored rewrite is rebuilt from its event log
- **THEN** its messages are unchanged, and the stored rewrite is neither required nor recreated

#### Scenario: Message deleted
- **WHEN** a message with a stored rewrite is deleted
- **THEN** no row for it remains

#### Scenario: Safety answers are not events
- **WHEN** a steered message's session is rebuilt from its event log
- **THEN** no event carries the stored safety answer, and the answer is still read from its row

## ADDED Requirements

### Requirement: Both reducers empty a refused message
In both reducer languages, an `error` event with code `content_refused` and a `messageId` SHALL empty that message's content (or the streaming variant's) and set its (or the variant's) status to `error`, whether it comes before or after that message's `turn.end`. The session's cost SHALL NOT change. The backend's stored message SHALL match.

#### Scenario: Live block
- **WHEN** `token` events, then `error` (`content_refused`, `messageId`), then `turn.end` with status `error` are reduced
- **THEN** the message's content is empty and its status is `error`, in Python and in TypeScript alike

#### Scenario: After the fact
- **WHEN** a reply's `turn.end` with status `interrupted` is followed by `error` (`content_refused`, `messageId`)
- **THEN** the message's content is empty, its status is `error`, and the served message equals the reduced one

#### Scenario: A blocked variant
- **WHEN** a regenerate's variant is blocked
- **THEN** only that variant's content is emptied, and the earlier variant is unchanged
