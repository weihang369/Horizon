# Spec Delta

## MODIFIED Requirements

### Requirement: The summary check follows each turn
After a turn that did not end in error, the runtime SHALL ask the session's summary task to check the window (see `conversation-context`). The check SHALL NOT delay the next queued turn or hold an LLM slot.

#### Scenario: Next speaker not delayed
- **WHEN** a group turn ends with the window over its size and another speaker is queued
- **THEN** the next speaker's `turn.next` follows the turn gap (or, for a follow plan's second reply, the follow plan's answer), whether or not the summary call has returned

### Requirement: After-turn tasks are named and cancellable
Work started after a turn (reactions, the face check, the watch plan made ahead, the rolling summary, the memory writer) SHALL run as named tasks owned by the session's actor. `clear()` (Stop, leave, a cap pause, Summarise, the session's end) SHALL cancel the session's pending reactions, face checks and plans made ahead, and SHALL leave the rolling summary and the memory writer running.

#### Scenario: Stop cancels reactions and the check
- **WHEN** Stop is sent while a reaction and a face check are pending and a rolling summary is running
- **THEN** no `reaction` event and no face-check row is emitted afterwards, and the rolling summary's row is still written

#### Scenario: Stop cancels the plan made ahead
- **WHEN** Stop is sent in an `agent` watch while the next turn's plan is being made ahead
- **THEN** that plan's ledger row has outcome `cancelled`, and no later turn uses it

## ADDED Requirements

### Requirement: A turn announces itself only for the current reply epoch
Each user message in a group or a Step in SHALL start a new reply epoch, under the writer lock, before the message is appended. A turn queued for an earlier epoch SHALL append its `turn.next` only if no newer epoch exists at that moment, checked under the same lock. A turn that fails the check SHALL emit nothing, and its plan and prefetch SHALL be discarded (their spend and drain stand).

#### Scenario: No turn.next after a newer message
- **WHEN** a group reply job for message A reaches its second speaker after the user's message B was appended
- **THEN** that speaker's `turn.next` is never appended, and the job ends without writing

#### Scenario: Never between the check and the write
- **WHEN** a `turn.next` and a new user message are appended at the same moment, a thousand times on the virtual clock
- **THEN** every run either has the `turn.next` before the user's message and its reply complete, or has no such `turn.next`

### Requirement: Superseded work ends at its boundaries
A job superseded by a newer reply epoch SHALL end at its next boundary (before a speaker, while waiting for a follow plan, during a turn gap), never by cancelling the worker task mid-turn. A watch turn's bookkeeping (`turnsTaken`) SHALL never be lost to a supersede.

#### Scenario: Step in during a watch turn's gap
- **WHEN** the user steps into a watch while a scene turn is in its turn gap
- **THEN** that turn's `turnsTaken` increment is still emitted, and Step in's reply follows

### Requirement: New cancel paths leave the writer free
A storm of cancels landing on any of the new cancel paths (a superseded reply, a follow plan cut by a new message, Step in's second reply, a watch plan made ahead) during a write or during a plan SHALL leave no connection checked out, let a new write succeed within 5 seconds, and leave an event log that reduces.

#### Scenario: Storm on a supersede
- **WHEN** a group send that supersedes an earlier reply is cancelled on every loop turn until it ends
- **THEN** the writer has no checked-out connection, a fresh write succeeds within 5 seconds, and the stored events reduce to the live state

### Requirement: A mode can hand the turn its plan
When a mode passes a frozen per-turn plan with a turn, the runtime SHALL use it as the turn's plan, start no plan of its own, and follow the plan's branch for retrieval (in M10 always quick: no retrieval).

#### Scenario: A planned group reply
- **WHEN** an `agent` group reply runs with the cast plan's per-turn plan
- **THEN** its turn context holds that plan, no second `turn_plan` request is made for it, and no retrieval runs
