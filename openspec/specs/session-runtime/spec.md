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

### Requirement: Trace ownership
The backend SHALL own:
- the trace sections `model`, `energy`, `routing` and `system1`;
- the message's `usage`;
- `TurnTrace.calls`, with usage and calls derived from the ledger rows for that message.

A trace patch from an AI port that sets an owned section SHALL be rejected, and the rest of the patch SHALL still be applied. A later `insight` for the same message SHALL carry the full merged trace, and SHALL keep the stored engine name, versions and creation time when it carries no engine metadata of its own.

#### Scenario: Reply cost matches usage
- **WHEN** a live reply completes
- **THEN** its trace's `calls` include a `reply` entry whose `costUsd` equals the message's `usage.costUsd`, and both equal the ledger row's cost

#### Scenario: Engine tries to set energy
- **WHEN** a turn engine emits a trace patch containing an `energy` section and a `context` section
- **THEN** the emitted trace keeps the backend's `energy` section and includes the engine's `context` section

#### Scenario: Engine tries to set System 1
- **WHEN** a turn engine emits a trace patch containing `system1`
- **THEN** the patch's `system1` is dropped

### Requirement: Stop and pause are prompt
`chat.stop`, `debate.pause`, `watch.pause`, `leave` and `end` SHALL cancel a running turn within 500 ms of acceptance, including a turn whose plan is still waiting for Jev. A partially streamed reply SHALL be closed with `turn.end { status: "interrupted", interruptedBy: "user" }`, keeping the text already streamed. Its spend SHALL stay in the ledger at the estimate when the provider has not reported the cost.

#### Scenario: Stop mid-stream
- **WHEN** Stop is sent while a reply is streaming
- **THEN** within 500 ms the message's status is `interrupted` with `interruptedBy: "user"`, and its content is exactly the text streamed before the stop

#### Scenario: Stop during the plan
- **WHEN** Stop is sent while an `agent` 1:1 turn's plan is waiting for Jev
- **THEN** within 500 ms no turn is running and no message was created

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

### Requirement: The reply cap is chosen after the plan
The runtime SHALL choose a reply's `max_tokens` after retrieval and after the turn's plan is known, from the mode and whether the plan made the turn deep. With no plan, or a plan that made the turn quick (every plan in M9), the turn SHALL use the quick cap. Prefetched turns SHALL follow the same rule.

#### Scenario: Prefetched debate opening
- **WHEN** a debate opening is prefetched in a `short` debate
- **THEN** its request's `max_tokens` is 200

#### Scenario: Planned 1:1 turn
- **WHEN** an `agent` 1:1 turn is planned
- **THEN** its request's `max_tokens` is the quick cap for 1:1

### Requirement: A verbatim line is spoken without a model call
A turn whose line is marked verbatim SHALL stream that exact text as the speaker's message, in every profile, paced by the shared timing table, with emotion `happy` from source `default`. It SHALL make no planner, model, gateway or guardrail call, write no ledger row, drain no energy, emit no `energy` event, and carry no `usage`. Its trace SHALL have no `model` section, and its stored engine SHALL be `verbatim` with no prompt version.

#### Scenario: Verbatim greeting trace
- **WHEN** a first-chat greeting completes
- **THEN** its `insight` trace has `emotion: {chosen: "happy", source: "default"}`, no `model` section and an empty `calls` list, and the ledger has no row for the message

#### Scenario: Stop during a verbatim line
- **WHEN** Stop is sent while a verbatim greeting is streaming
- **THEN** the message ends `interrupted` with the text streamed so far, and nothing is spent

#### Scenario: Regenerating a verbatim greeting
- **WHEN** a verbatim greeting is regenerated with a key set
- **THEN** the new variant is generated by the profile's turn engine and billed as a reply

#### Scenario: Regenerating a generated greeting
- **WHEN** a 1:1 greeting (a character message with no user line before it) is regenerated under `naive` or `agent`
- **THEN** the new variant is a generated greeting (the greeting cue; `emotion_greeting` under `agent`), not a reply

### Requirement: The summary check follows each turn
After a turn that did not end in error, the runtime SHALL ask the session's summary task to check the window (see `conversation-context`). The check SHALL NOT delay the next queued turn or hold an LLM slot.

#### Scenario: Next speaker not delayed
- **WHEN** a group turn ends with the window over its size and another speaker is queued
- **THEN** the next speaker's `turn.next` follows the turn gap (or, for a follow plan's second reply, the follow plan's answer), whether or not the summary call has returned

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

### Requirement: The runtime keeps each sitting's memory list
The runtime SHALL read each `agent` speaker's memory list once per sitting, when it first builds that speaker's view, and reuse it for every later turn of the sitting. It SHALL drop it when one of its memories is forgotten or when a pause run commits memories for that character, so the next turn reads it again.

#### Scenario: Run commits in another tab
- **WHEN** a run in session A commits a memory for Amara while session B with Amara is live
- **THEN** B's next Amara turn shows the new memory in its list, and the turn after it sends the same system message

### Requirement: An interrupted reply is checked after the fact
Under `agent`, a reply ended by Stop (including Stop during its check) SHALL be checked by a named after-turn task that reuses any check already in flight or already answered, so nothing is paid twice. The task SHALL survive Stop, End, a cap pause, leave and Reset demo (which keeps user sessions), and SHALL be cancelled by a session, character or world delete and by shutdown. A block SHALL scrub the reply as a live block does.

#### Scenario: Stop during the check
- **WHEN** the user presses Stop while a finished reply's output check is in flight, and the check then answers p 0.95
- **THEN** exactly one `guardrail` ledger row exists for that message, and the message ends with empty content and status `error`

#### Scenario: Stop after the check answered
- **WHEN** the output check has answered p 0.95 and Stop lands before `turn.end` is written
- **THEN** that answer is reused: exactly one `guardrail` ledger row exists for that message, and the message ends with empty content and status `error`

#### Scenario: Deleted meanwhile
- **WHEN** a session is deleted while an after-the-fact check is in flight
- **THEN** the task is cancelled, and nothing is written for the deleted message

### Requirement: The output check doesn't stretch the turn cadence
The waits after a character turn (the turn gap, a debate's `pauseMs`, a watch's `paceMs`) SHALL count from the moment the reply's stream ended, and the next turn SHALL start no earlier than the turn's `turn.end`. Deadlines that count from `turn.end` (the follow plan, the debate member) SHALL keep counting from it.

#### Scenario: A short check is hidden in the pace
- **WHEN** a watch with `paceMs` 2,000 has a reply whose output check takes 500 ms
- **THEN** the next turn's `turn.next` comes 2,000 ms after that reply's stream ended, not 2,500 ms
