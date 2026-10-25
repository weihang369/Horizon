# Spec Delta

## Purpose

Decides everything about a turn before its reply is written: one Jev request (`turn_plan`), turned by code into a
frozen plan that the reply, the trace and replay all read. In M9 it runs in `agent` 1:1 and asks only the emotion.

## ADDED Requirements

### Requirement: The plan runs before an agent 1:1 reply
Under the `agent` profile with a key, every 1:1 character turn that calls a model SHALL be planned before its reply
request is sent: a sent message, a regenerate and a generated greeting. A verbatim line, every turn in the other modes
and every turn under the `naive` profile SHALL make no `turn_plan` call.

#### Scenario: A 1:1 send is planned
- **WHEN** a key is set, the profile is `agent`, and a message is sent in a 1:1 session
- **THEN** one `turn_plan` decision row is written for the reply before its chat row, and the reply's trace carries the plan's System 1 rows

#### Scenario: The first-chat greeting asks nothing
- **WHEN** a character's first chat opens with its stored greeting under `agent`
- **THEN** no `turn_plan` request is made for that greeting

#### Scenario: Group stays unplanned in M9
- **WHEN** an `agent` group message is answered
- **THEN** no `turn_plan` request is made, and the routing decision is the naive router's

#### Scenario: Naive asks nothing new
- **WHEN** a `naive` 1:1 reply completes
- **THEN** the ledger has no `turn_plan` row, and the trace has no System 1 section

### Requirement: Jev call 1 is one request with only the questions that apply
A turn's plan SHALL make at most one `turn_plan` request, holding the emotion question for each candidate and no other
question in M9. Its state SHALL be the turn-plan state (see `conversation-context`) for that turn, with no document
titles. The request SHALL be recorded as decision spend and SHALL never drain energy.

#### Scenario: One request for the turn
- **WHEN** an `agent` 1:1 reply is planned
- **THEN** exactly one `turn_plan` request is sent, with one question keyed `emotion_reply:{characterId}` and a state holding `mode`, `quoted_user`, `quoted_cast`, `quoted_latest` and `quoted_recent`

#### Scenario: No gate questions yet
- **WHEN** an `agent` 1:1 reply is planned for a character with indexed knowledge
- **THEN** the request holds no "needs documents?" or "needs something from earlier?" question

### Requirement: The plan has a deadline and a fallback
The plan SHALL wait for Jev until the `turn_plan` deadline (700 ms after the request started). A late, failed,
refused or oversized request SHALL produce the fallback plan at once and never delay the reply further. A late answer
SHALL still be recorded in the ledger and then discarded.

#### Scenario: Late answer
- **WHEN** Jev's answer is held past the 700 ms deadline
- **THEN** the reply starts with the fallback face, the System 1 emotion row has `result: "fallback"`, and the late answer's ledger row exists with its outcome `late`

#### Scenario: Rate limited
- **WHEN** the `turn_plan` request returns HTTP 429
- **THEN** the plan falls back at once, with no retry

### Requirement: The plan starts before the preamble
The planner's request SHALL start before the turn's `turn.next` event, so the turn's thinking delay overlaps the Jev
call. The reply request SHALL be sent no later than when both the preamble and the plan are done.

#### Scenario: Overlap with the thinking delay
- **WHEN** an `agent` 1:1 turn runs on the virtual clock with Jev answering in 400 ms
- **THEN** the reply request is sent 400 ms after the turn began, not 400 ms after `turn.thinking`

### Requirement: The plan is frozen into the turn context
The runtime SHALL freeze the finished plan into the turn's context before the reply request is built. The plan SHALL
be JSON-serialisable, hold its seed, its System 1 rows, its paid call and the chosen face, and be enough to rebuild
the reply request without asking Jev again.

#### Scenario: Replay from JSON
- **WHEN** a planned turn's context is serialised to JSON and loaded again
- **THEN** the reply request built from it is byte-identical to the original, and no decision request is made

#### Scenario: Captured with the turn
- **WHEN** AI-call capture is on and an `agent` 1:1 reply completes
- **THEN** the captured turn row's response holds the plan, not null

### Requirement: Stop during a plan
Stop, pause, leave, end and a cap pause SHALL cancel a turn whose plan is still running, within 500 ms. No message
SHALL be created, the decision's readers SHALL be detached, and the request already sent SHALL be allowed to finish
and be recorded. Nothing else started by the plan SHALL keep running.

#### Scenario: Stop while Jev is thinking
- **WHEN** Stop is sent while the `turn_plan` request is held open
- **THEN** within 500 ms no turn is running, no `turn.start` was emitted, and when the request is released its ledger row is written with outcome `cancelled`

#### Scenario: Nothing leaks
- **WHEN** Stop is sent during a plan on the virtual clock and the request is then released
- **THEN** the clock settles with no task left from the plan

### Requirement: The plan graph settles on the virtual clock
Every task the plan starts SHALL be visible to the runtime's activity tracking, so a virtual-clock advance waits for
it. The planner's own work, Jev's time excluded, SHALL add under 50 ms to a turn.

#### Scenario: Deterministic settle
- **WHEN** 100 planned turns run on the virtual clock with scripted answers
- **THEN** every clock advance settles without timing out, and the outputs are identical across two runs

### Requirement: Planner per profile
The `agent` profile SHALL resolve the planner to the Jev planner. `naive` SHALL resolve it to no planner. `scripted`
SHALL resolve it to a planner that makes no request, records one simulated `turn_plan` decision call, and leaves the
face to the scripted reply.

#### Scenario: Scripted 1:1 turn
- **WHEN** a scripted 1:1 reply completes
- **THEN** one simulated `turn_plan` ledger row exists for it, and its trace's System 1 section has the fixture's emotion row with the answer set to the face the reply showed

#### Scenario: Naive with a key
- **WHEN** the profile is `naive` with a key and a 1:1 reply completes
- **THEN** no `turn_plan` row, simulated or real, exists
