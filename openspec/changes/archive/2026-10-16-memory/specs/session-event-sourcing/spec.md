# Spec Delta

## ADDED Requirements

### Requirement: Memory run bookkeeping is not event-sourced
A session's memory checkpoint, its list of messages to read again and its failed-try count SHALL be runtime bookkeeping set by memory pause runs, not projected from or written to the event log. Rebuilding a session from its events SHALL NOT need them, and SHALL leave them unchanged.

#### Scenario: Rebuilt from events
- **WHEN** a session whose checkpoint is 40 is rebuilt from its event log
- **THEN** its messages are unchanged and its checkpoint is still 40

### Requirement: The indexed lines are derived data
The indexed copies of a session's dropped lines, and their vectors, SHALL be AI-owned derived data, like turn traces: not projected from events, copied by a fork with their messages, and deleted with their messages.

#### Scenario: Message deleted
- **WHEN** a session with indexed lines is deleted
- **THEN** no indexed line or vector of its messages remains
