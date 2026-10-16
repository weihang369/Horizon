# Spec Delta

## MODIFIED Requirements

### Requirement: After-turn tasks are named and cancellable
Work started after a turn (reactions, the face check, the watch plan made ahead, the rolling summary and the indexing of the lines it drops) SHALL run as named tasks owned by the session's actor. `clear()` (Stop, leave, a cap pause, Summarise, the session's end) SHALL cancel the session's pending reactions, face checks and plans made ahead, and SHALL leave the rolling summary and its indexing running. Memory pause runs SHALL NOT be actor tasks (see `long-term-memory`).

#### Scenario: Stop cancels reactions and the check
- **WHEN** Stop is sent while a reaction and a face check are pending and a rolling summary is running
- **THEN** no `reaction` event and no face-check row is emitted afterwards, and the rolling summary's row is still written

#### Scenario: Stop cancels the plan made ahead
- **WHEN** Stop is sent in an `agent` watch while the next turn's plan is being made ahead
- **THEN** that plan's ledger row has outcome `cancelled`, and no later turn uses it

#### Scenario: A pause run doesn't hold the actor
- **WHEN** a session's pause run is in flight and the session has no subscriber and no other work for 10 minutes of clock time
- **THEN** the session's actor is released, and the run still commits

### Requirement: A blocked reply is scrubbed
When the output guardrail blocks a reply after it has streamed, the backend SHALL end the turn with `status: "error"` and `content_refused`. It SHALL remove the reply's text from the stored message and from its stored `token` events, and SHALL exclude the reply from memory: no pause run SHALL read the reply, and any still-current memory derived from that message SHALL be undone as a changed read message is (see `long-term-memory`), so memories it only superseded become current again.

#### Scenario: Blocked after streaming
- **WHEN** the output guardrail blocks a completed reply
- **THEN** `turn.end` has `status: "error"`, the `error` event has `content_refused`, and neither the message content nor any stored `token` event contains the reply's text

#### Scenario: Blocked reply leaves no memory
- **WHEN** a reply is blocked and the session then pauses
- **THEN** the run's input does not hold the reply, and no memory has that message as its source

#### Scenario: Blocked regenerate keeps older memories
- **WHEN** memory B, sourced from a read reply, superseded memory A, and a regenerate of that reply is blocked
- **THEN** B is gone and A is current again

### Requirement: Daily cap pauses live sessions
When recorded spend reaches the daily cap, or a session's paid call is refused by it, every active live session SHALL pause with `pausedReason: "daily_budget"`, after letting a reply already streaming finish. A refused turn SHALL leave no message. Any further command that would spend in that session SHALL be rejected with `daily_budget_exceeded` until spend is below the cap again, for example after the day rolls over or the cap is raised. Spend or a refusal from memory pause runs and window-drop indexing SHALL NOT pause any session.

#### Scenario: Cap reached by the greeting
- **WHEN** the daily cap is $0.00005 and a character's second new 1:1 session generates its greeting
- **THEN** the global stream carries `budget.reached`, the session reports `pausedReason: "daily_budget"`, and `chat.send` rejects with `daily_budget_exceeded`

#### Scenario: The first chat's greeting costs nothing
- **WHEN** the daily cap is $0.00005 with nothing spent today, and a character's first new 1:1 session opens
- **THEN** the approved greeting completes, no `budget.reached` is sent, and the session stays `active`

#### Scenario: A pause run crosses the cap
- **WHEN** a pause run's `memory` call takes spend over the daily cap while another session is active
- **THEN** that session stays active until its own next paid call meets the cap

## ADDED Requirements

### Requirement: The runtime keeps each sitting's memory list
The runtime SHALL read each `agent` speaker's memory list once per sitting, when it first builds that speaker's view, and reuse it for every later turn of the sitting. It SHALL drop it when one of its memories is forgotten or when a pause run commits memories for that character, so the next turn reads it again.

#### Scenario: Run commits in another tab
- **WHEN** a run in session A commits a memory for Amara while session B with Amara is live
- **THEN** B's next Amara turn shows the new memory in its list, and the turn after it sends the same system message
