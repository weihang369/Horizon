# Spec Delta

## ADDED Requirements

### Requirement: AI-owned per-message data is not event-sourced
Per-message data the AI derives (the stored query rewrites) SHALL be kept beside the messages, like turn traces, and SHALL NOT be projected from or written to the event log. Reducing a session's events SHALL NOT need it, and replaying them SHALL NOT recreate it. Forking SHALL copy the rows of the messages it copies, and deleting a message SHALL delete its row.

#### Scenario: Rebuilt from events
- **WHEN** a session with a stored rewrite is rebuilt from its event log
- **THEN** its messages are unchanged, and the stored rewrite is neither required nor recreated

#### Scenario: Message deleted
- **WHEN** a message with a stored rewrite is deleted
- **THEN** no row for it remains
