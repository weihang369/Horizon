# session-runtime Specification

## Purpose

Runs live sessions on the backend: one serialised writer per open session, the turn loop that drives the AI ports through the gateway, and the guarantees around stopping, energy, budget caps, traces and citations that the MockClient already shows.

## Requirements

### Requirement: One writer per session
Every write to a session's rows SHALL be serialised through that session's single writer: commands, rename, mute, leave, end, delete and listener reactions. Event `seq` and message `seq` SHALL be allocated by that writer only, continuing from the highest stored values, with no gaps or duplicates. Two commands sent at the same time SHALL never interleave their events.

#### Scenario: Concurrent sends
- **WHEN** two `chat.send` commands for the same 1:1 session arrive at the same moment
- **THEN** the session's events have strictly consecutive `seq` values, and the two user messages and their replies are not interleaved

#### Scenario: Restart continues the sequence
- **WHEN** the backend restarts and a stored session with highest event `seq` 57 receives a command
- **THEN** its first new event has `seq` 58

### Requirement: Commands are accepted before they run
Every session command SHALL either be rejected before acceptance (see `http-api`) or be accepted with 202, with its results delivered only as session events. Once accepted, an energy shortage, a provider failure or a reached cap SHALL arrive as session events, never as the command's response.

#### Scenario: Provider failure after acceptance
- **WHEN** a send is accepted and the reply then fails with a provider error
- **THEN** the send has already returned 202, and the failure arrives as an `error` event followed by `turn.end` with `status: "error"`

### Requirement: Turn order
For each character turn, the backend SHALL:
1. choose the speaker;
2. allocate the reply's `messageId` before any model call;
3. check the speaker's energy;
4. reserve the budget;
5. run the turn engine;
6. emit the full trace as `insight`.

A turn whose speaker can't speak SHALL produce no model call.

#### Scenario: Message ID exists before spend
- **WHEN** a reply turn makes its paid chat call
- **THEN** the call's ledger row carries the reply's `messageId`, and that ID equals the `turn.start` message ID

### Requirement: Turn event sequence
A live character turn SHALL emit, in order, `turn.next`, `turn.thinking`, `turn.start`, then the reply's `token` and `emotion` events, then `turn.end`. After those come an `energy` event when energy was spent, and `insight` unless the turn ended in error. Listener `reaction` events MAY follow `turn.end`.

#### Scenario: 1:1 reply events
- **WHEN** a key is set, a 1:1 session is created, its greeting completes, and a message is sent and answered
- **THEN** the session stream carried `turn.next`, `turn.thinking`, `turn.start`, `token`, `emotion`, `turn.end`, `energy`, `insight` and `message` events, with consecutive `seq` values

### Requirement: Trace ownership
The backend SHALL own the trace sections `model`, `energy` and `routing`, the message's `usage`, and `TurnTrace.calls`, deriving usage and calls from the ledger rows for that message. A trace patch from an AI port that sets an owned section SHALL be rejected, and the rest of the patch SHALL still be applied. A later `insight` for the same message SHALL carry the full merged trace.

#### Scenario: Reply cost matches usage
- **WHEN** a live reply completes
- **THEN** its trace's `calls` include a `reply` entry whose `costUsd` equals the message's `usage.costUsd`, and both equal the ledger row's cost

#### Scenario: Engine tries to set energy
- **WHEN** a turn engine emits a trace patch containing an `energy` section and a `context` section
- **THEN** the emitted trace keeps the backend's `energy` section and includes the engine's `context` section

### Requirement: Stop and pause are prompt
`chat.stop`, `debate.pause`, `watch.pause`, `leave` and `end` SHALL cancel a running turn within 500 ms of acceptance. A partially streamed reply SHALL be closed with `turn.end { status: "interrupted", interruptedBy: "user" }`, keeping the text already streamed. Its spend SHALL stay in the ledger at the estimate when the provider has not reported the cost.

#### Scenario: Stop mid-stream
- **WHEN** Stop is sent while a reply is streaming
- **THEN** within 500 ms the message's status is `interrupted` with `interruptedBy: "user"`, and its content is exactly the text streamed before the stop

### Requirement: Stored events equal streamed events
Token deltas MAY be coalesced into fewer `token` events, but every event delivered live SHALL be exactly the stored event with the same `seq`, and replaying a session SHALL yield the same events as a live subscriber received.

#### Scenario: Replay equals live
- **WHEN** a subscriber records every event of a live 1:1 exchange, and the session's events are then fetched
- **THEN** the fetched events equal the recorded ones, field for field

### Requirement: Energy gate in turns
A character whose energy is below `estReplyPoints` for the current pricing period SHALL NOT speak. In group, debate and watch auto-turns, the backend SHALL skip that speaker and record `{ characterId, reason: "exhausted" }` in the routing trace. When the user addressed the character directly (1:1, an @mention, Ask), it SHALL post a system note "{name} is asleep" and an `error` event with `energy_exhausted`.

#### Scenario: Mentioned character asleep
- **WHEN** Takeshi has 0 energy and a group message @mentions him
- **THEN** a `system_note` containing "Takeshi is asleep" and an `error` event with code `energy_exhausted` are emitted, and Takeshi writes no reply

#### Scenario: Threshold follows the period
- **WHEN** Takeshi has 6 energy at peak and a group message gets an auto response
- **THEN** his opening `energy` event says `exhausted`, he does not speak, and a trace lists `{ characterId: "chr_seedTakeshi", reason: "exhausted" }` as skipped

### Requirement: Reply drains energy as a session event
When a reply's paid call is recorded, the backend SHALL drain the speaker's energy (see `energy`) and then emit a stored `energy` event with the speaker's settled `current`, `max`, `state` and the `spent` points.

#### Scenario: Drain visible on the stream and the character
- **WHEN** a live reply costing $0.0004 completes, with `usdPerPoint` 0.0001
- **THEN** an `energy` event with `spent: 4` follows its `turn.end`, and the character's energy read afterwards is 4 points lower than before the turn, net of regeneration

### Requirement: Daily cap pauses live sessions
When recorded spend reaches the daily cap, or a session's paid call is refused by it, every active live session SHALL pause with `pausedReason: "daily_budget"`, after letting a reply already streaming finish. A refused turn SHALL leave no message. Any further command that would spend in that session SHALL be rejected with `daily_budget_exceeded` until spend is below the cap again, for example after the day rolls over or the cap is raised.

#### Scenario: Cap reached by the greeting
- **WHEN** the daily cap is $0.00005 and a new 1:1 session's greeting is generated
- **THEN** the global stream carries `budget.reached`, the session reports `pausedReason: "daily_budget"`, and `chat.send` rejects with `daily_budget_exceeded`

### Requirement: Discarded prefetches still drain energy
Opening turns generated ahead of their speaking slot (at most 2 at a time) SHALL be held back unsequenced and released at speaking pace. When Stop discards them, their spend SHALL stay in the ledger with no message ID and SHALL drain each speaker's energy (D-77). Nothing from a discarded prefetch SHALL appear in the session's events.

#### Scenario: Stop during a debate opening
- **WHEN** a debate's opening round has one speaker streaming and another prefetched, and Stop is sent
- **THEN** the prefetched speaker's ledger row remains with an empty message ID, that speaker's energy is lower by its cost in points, and no event mentions the discarded reply

### Requirement: One streaming session at a time
At most one session SHALL be generating at a time. A command that would start generation in another session SHALL be rejected with `conflict` and `details.activeSessionId` naming the live session. A session that was left (`navigated_away`) or paused SHALL NOT count as generating.

#### Scenario: Second session refused, then allowed after leave
- **WHEN** session A is streaming a reply and a new 1:1 session is created
- **THEN** the create rejects with `conflict` and `details.activeSessionId` equal to A, and after `sessions.leave(A)` the same create succeeds

### Requirement: Idle sessions release their resources
A live session with no subscribers and no running or queued work SHALL release its runtime resources after 10 minutes of clock time, and on `leave` or `end`. A released session SHALL accept commands again exactly as before, resuming from its stored state.

#### Scenario: Command after idle release
- **WHEN** a paused 1:1 session has had no subscriber for 11 minutes of clock time and a message is sent to it
- **THEN** the send is accepted and answered, and its events continue the stored `seq`

### Requirement: Citations are stored at turn end
At `turn.end`, the backend SHALL keep only the citations whose marker `[n]` appears in the final content, including interrupted replies, and SHALL store one `message_citations` row per kept citation. `turn.end.citations` SHALL list the kept citations, omitted when none are kept.

#### Scenario: Unused citation dropped
- **WHEN** an engine offers citations 1 and 2 and the final content contains only `[1]`
- **THEN** `turn.end.citations` holds only citation 1, and one `message_citations` row exists for the message

### Requirement: A blocked reply is scrubbed
When the output guardrail blocks a reply after it has streamed, the backend SHALL end the turn with `status: "error"` and `content_refused`. It SHALL remove the reply's text from the stored message and from its stored `token` events, and SHALL exclude the reply from memory: the reply SHALL NOT be passed to the memory writer, and any memory derived from it SHALL be forgotten in the same way as a user Forget.

#### Scenario: Blocked after streaming
- **WHEN** the output guardrail blocks a completed reply
- **THEN** `turn.end` has `status: "error"`, the `error` event has `content_refused`, and neither the message content nor any stored `token` event contains the reply's text

#### Scenario: Blocked reply leaves no memory
- **WHEN** a memory writer that would remember every reply is attached and the output guardrail blocks a reply
- **THEN** the memory writer is not called for that reply, and no memory has that message as its source
