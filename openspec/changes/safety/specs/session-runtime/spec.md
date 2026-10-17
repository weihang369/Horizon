## MODIFIED Requirements

### Requirement: Turn event sequence
A live character turn SHALL emit, in order, `turn.next`, `turn.thinking`, `turn.start`, then the reply's `token` and `emotion` events, then `turn.end`. When the engine's first event is an emotion, `turn.start` and that `emotion` event SHALL be appended in one write. After those come an `energy` event when energy was spent, and `insight` unless the turn ended in an error other than a block by the output check (a blocked reply emits its `insight`). Listener `reaction` events and a later `insight` carrying after-turn System 1 rows MAY follow `turn.end`.

#### Scenario: 1:1 reply events
- **WHEN** a key is set, a 1:1 session is created, its greeting completes, and a message is sent and answered
- **THEN** the session stream carried `turn.next`, `turn.thinking`, `turn.start`, `token`, `emotion`, `turn.end`, `energy`, `insight` and `message` events, with consecutive `seq` values

#### Scenario: Nothing between the start and the face
- **WHEN** a reaction to an earlier message is due at the moment an `agent` reply's first chunk arrives
- **THEN** no `reaction` event has a `seq` between that reply's `turn.start` and its first `emotion`

#### Scenario: A blocked reply still explains itself
- **WHEN** an `agent` reply is blocked by the output check
- **THEN** the stream carries `error`, then `turn.end` with status `error`, then an `insight` for that message whose `guardrail.checks` include `output` with verdict `block`

## ADDED Requirements

### Requirement: An interrupted reply is checked after the fact
Under `agent`, a reply ended by Stop (including Stop during its check) SHALL be checked by a named after-turn task that reuses any check already in flight, so nothing is paid twice. The task SHALL survive Stop, End, a cap pause and leave, and SHALL be cancelled by a session, character or world delete, by Reset demo and by shutdown. A block SHALL scrub the reply as a live block does.

#### Scenario: Stop during the check
- **WHEN** the user presses Stop while a finished reply's output check is in flight, and the check then answers p 0.95
- **THEN** exactly one `guardrail` ledger row exists for that message, and the message ends with empty content and status `error`

#### Scenario: Deleted meanwhile
- **WHEN** a session is deleted while an after-the-fact check is in flight
- **THEN** the task is cancelled, and nothing is written for the deleted message

### Requirement: The output check doesn't stretch the turn cadence
The waits after a character turn (the turn gap, a debate's `pauseMs`, a watch's `paceMs`) SHALL count from the moment the reply's stream ended, and the next turn SHALL start no earlier than the turn's `turn.end`. Deadlines that count from `turn.end` (the follow plan, the debate member) SHALL keep counting from it.

#### Scenario: A short check is hidden in the pace
- **WHEN** a watch with `paceMs` 2,000 has a reply whose output check takes 500 ms
- **THEN** the next turn's `turn.next` comes 2,000 ms after that reply's stream ended, not 2,500 ms
