# Spec Delta

## ADDED Requirements

### Requirement: A session stream left empty is noticed
When the last subscriber of a session's stream disconnects, the backend SHALL start that session's 30-second grace (`memory.leaveGraceMs`) on the runtime clock, and SHALL cancel it when anyone subscribes to that session's stream again. When the grace ends, the session's memory pause run SHALL be requested, whatever the session's status.

#### Scenario: Two tabs
- **WHEN** a session is open in two tabs and one closes
- **THEN** no grace starts, and when the second closes the grace starts

#### Scenario: Reconnect
- **WHEN** a session's only stream drops and reconnects 5 seconds later
- **THEN** no pause run is requested
