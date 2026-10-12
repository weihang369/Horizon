## MODIFIED Requirements

### Requirement: Turn event sequence
A live character turn SHALL emit, in order, `turn.next`, `turn.thinking`, `turn.start`, then the reply's `token` and `emotion` events, then `turn.end`. When the engine's first event is an emotion, `turn.start` and that `emotion` event SHALL be appended in one write. After those come an `energy` event when energy was spent, and `insight` unless the turn ended in error. Listener `reaction` events and a later `insight` carrying after-turn System 1 rows MAY follow `turn.end`.

#### Scenario: 1:1 reply events
- **WHEN** a key is set, a 1:1 session is created, its greeting completes, and a message is sent and answered
- **THEN** the session stream carried `turn.next`, `turn.thinking`, `turn.start`, `token`, `emotion`, `turn.end`, `energy`, `insight` and `message` events, with consecutive `seq` values

#### Scenario: Nothing between the start and the face
- **WHEN** a reaction to an earlier message is due at the moment an `agent` reply's first chunk arrives
- **THEN** no `reaction` event has a `seq` between that reply's `turn.start` and its first `emotion`

### Requirement: Stop and pause are prompt
`chat.stop`, `debate.pause`, `watch.pause`, `leave` and `end` SHALL cancel a running turn within 500 ms of acceptance, including a turn whose plan is still waiting for Jev. A partially streamed reply SHALL be closed with `turn.end { status: "interrupted", interruptedBy: "user" }`, keeping the text already streamed. Its spend SHALL stay in the ledger at the estimate when the provider has not reported the cost.

#### Scenario: Stop mid-stream
- **WHEN** Stop is sent while a reply is streaming
- **THEN** within 500 ms the message's status is `interrupted` with `interruptedBy: "user"`, and its content is exactly the text streamed before the stop

#### Scenario: Stop during the plan
- **WHEN** Stop is sent while an `agent` 1:1 turn's plan is waiting for Jev
- **THEN** within 500 ms no turn is running and no message was created

### Requirement: The reply cap is chosen after the plan
The runtime SHALL choose a reply's `max_tokens` after retrieval and after the turn's plan is known, from the mode and whether the plan made the turn deep. With no plan, or a plan that made the turn quick (every plan in M9), the turn SHALL use the quick cap. Prefetched turns SHALL follow the same rule.

#### Scenario: Prefetched debate opening
- **WHEN** a debate opening is prefetched in a `short` debate
- **THEN** its request's `max_tokens` is 200

#### Scenario: Planned 1:1 turn
- **WHEN** an `agent` 1:1 turn is planned
- **THEN** its request's `max_tokens` is the quick cap for 1:1

## ADDED Requirements

### Requirement: After-turn tasks are named and cancellable
Work started after a turn (reactions, the face check, the rolling summary, the memory writer) SHALL run as named tasks owned by the session's actor. `clear()` (Stop, leave, a cap pause, the session's end) SHALL cancel the session's pending reactions and face checks, and SHALL leave the rolling summary and the memory writer running.

#### Scenario: Stop cancels reactions and the check
- **WHEN** Stop is sent while a reaction and a face check are pending and a rolling summary is running
- **THEN** no `reaction` event and no face-check row is emitted afterwards, and the rolling summary's row is still written
