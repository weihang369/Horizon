# turn-plan Specification

## Purpose
Decides everything about a turn before its reply is written: one Jev request (`turn_plan`), turned by code into a
frozen plan that the reply, the trace and replay all read. In M9 it runs in `agent` 1:1 and asks only the emotion.

## Requirements

### Requirement: The plan runs before an agent 1:1 reply
Under the `agent` profile with a key, every 1:1 character turn that calls a model SHALL be planned before its reply
request is sent: a sent message, a regenerate and a generated greeting. From M10, group and watch turns under `agent`
are planned by the cast plan (see "The cast plan for group and watch") and debate turns stay unplanned. A verbatim
line and every turn under the `naive` profile SHALL make no `turn_plan` call.

#### Scenario: A 1:1 send is planned
- **WHEN** a key is set, the profile is `agent`, and a message is sent in a 1:1 session
- **THEN** one `turn_plan` decision row is written for the reply before its chat row, and the reply's trace carries the plan's System 1 rows

#### Scenario: The first-chat greeting asks nothing
- **WHEN** a character's first chat opens with its stored greeting under `agent`
- **THEN** no `turn_plan` request is made for that greeting

#### Scenario: Group stays unplanned in M9
- **WHEN** an `agent` group message is answered with the planner overridden to `naive` (`HORIZON_AI_PLANNER=naive`, M9's behaviour and M10's rollback)
- **THEN** no `turn_plan` request is made, and the routing decision is the naive router's

#### Scenario: Group is planned from M10
- **WHEN** an `agent` group message with no mention is answered
- **THEN** one `turn_plan` request is made before the first reply's `turn.next`, and no `route` request is made

#### Scenario: Debate stays unplanned
- **WHEN** an `agent` debate turn is answered
- **THEN** no `turn_plan` request is made for it

#### Scenario: Naive asks nothing new
- **WHEN** a `naive` 1:1 reply completes
- **THEN** the ledger has no `turn_plan` row, and the trace has no System 1 section

### Requirement: Jev call 1 is one request with only the questions that apply
A turn's plan SHALL make at most one `turn_plan` request. In 1:1 it SHALL hold the emotion question for the speaker.
In group and watch it SHALL hold the who-speaks question when one is asked, the emotion question for each candidate,
and in watch "is the talk finished?". From M12 it SHALL also hold "needs documents?" for each candidate with a
searchable source, and, in 1:1 and when a group message is answered, "standalone?" and "English?" once when any
"needs documents?" is asked. From M14 it SHALL also hold "unsafe request?" once about a user-written line with no
stored safety answer, and in 1:1, group and Step in "at risk?" beside it. Its state SHALL be the turn-plan state (see
`conversation-context`) for that turn, with the document titles of the candidates asked "needs documents?". The
request SHALL be recorded as decision spend and SHALL never drain energy.

#### Scenario: One request for the turn
- **WHEN** an `agent` 1:1 reply is planned for a character with no documents, for a message already checked
- **THEN** exactly one `turn_plan` request is sent, with one question keyed `emotion_reply:{characterId}` and a state holding `mode`, `quoted_user`, `quoted_cast`, `quoted_latest` and `quoted_recent`

#### Scenario: No gate questions yet
- **WHEN** an `agent` 1:1 reply is planned for a character with no searchable source
- **THEN** the request holds no "needs documents?", "standalone?", "English?" or "needs something from earlier?" question

#### Scenario: The gates for a character with documents
- **WHEN** an `agent` 1:1 reply is planned for Amara, whose sources are keyword-only
- **THEN** the one request also holds `docs:chr_seedAmara`, `standalone` and `english`, and its state lists her document titles under `quoted_documents`

#### Scenario: A group's call 1
- **WHEN** an `agent` group of three with no mention is planned for a message already checked, and only one of them has documents
- **THEN** the one request holds `who_first`, three `emotion_reply:{characterId}` questions, one `docs:{characterId}` question, `standalone` and `english`

#### Scenario: Watch asks no rewrite questions
- **WHEN** a watch turn is planned for a cast where two characters have documents
- **THEN** the request holds two `docs` questions and no `standalone` or `english` question

#### Scenario: A new message is checked in the same request
- **WHEN** an `agent` 1:1 reply is planned for a message with no stored safety answer
- **THEN** the one request also holds `unsafe_request` and `at_risk`, and no second request is made

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

### Requirement: The cast plan for group and watch
Under `agent` with a key, group Auto, Everyone, Next speaker, Step in and every watch turn SHALL be planned by one `turn_plan` request made before the first affected `turn.next`. The plan SHALL fix who speaks (or the order, for Everyone) and every candidate's face. Each reply it starts SHALL carry a frozen per-turn plan, so the turn replays from its stored context with no Jev call.

#### Scenario: Replay a group reply
- **WHEN** a planned `agent` group reply's stored turn context is replayed
- **THEN** the reply request is identical, and no Jev call is made

### Requirement: Who-speaks fallbacks
When Jev is unsure (below the floor), the who-speaks pick SHALL be the least recently spoken of Jev's top 2. When Jev fails or is late, it SHALL be the least recently spoken eligible character. The last speaker SHALL stay excluded where the question excludes them, and someone SHALL always answer a user's message.

#### Scenario: Late call 1 in a group
- **WHEN** an `agent` group's call 1 is held past its 700 ms deadline
- **THEN** the least recently spoken eligible character answers, the routing trace marks the fallback, and the late answer's ledger row has outcome `late`

### Requirement: Group and watch plans per profile
`naive` and `scripted` SHALL make no cast plan and no follow plan: their group and watch turns keep their own routing (the Jev router, the scripted scores, round-robin and random picks). `agent` without a key SHALL behave as `scripted`.

#### Scenario: Scripted group
- **WHEN** a scripted group message is answered
- **THEN** the ledger has a simulated `route` row and no `turn_plan` or `follow_plan` row

### Requirement: Cancelling a cast plan
Stop, leave, a cap pause, the session's end, a superseding user message (group and Step in) and a changed plan-ahead fingerprint (watch) SHALL cancel a cast plan in flight. Its request SHALL settle with outcome `cancelled`, it SHALL write no rows, and the session's writer SHALL be free afterwards.

#### Scenario: Cancelled during a write
- **WHEN** a cast plan is cancelled again and again while the session appends a user message
- **THEN** the append either commits whole or not at all, the plan's ledger row has outcome `cancelled`, and a new write succeeds within 5 seconds

### Requirement: The planner plans debate turns
Under `agent`, the planner SHALL plan every debate turn:
- rebuttal, closing and panel slots through the debate plan;
- each opening with its own `turn_plan` request (`emotion_debate_opening` for that speaker): the first opening during the start delay, every later one when its prefetch starts;
- each Ask answer at its turn start (`emotion_reply`).

No debate turn SHALL be planned under `naive` or `scripted`.

#### Scenario: The first opening's face is ready at its start
- **WHEN** an `agent` debate starts and its first opening speaker is Amara
- **THEN** a `turn_plan` request asking `emotion_debate_opening` about Amara is made during the 1.6 s start delay, and Amara's opening uses its answer

#### Scenario: A prefetched opening keeps its own plan
- **WHEN** Victor's opening is prefetched while Amara's streams
- **THEN** Victor's prefetch carries its own `emotion_debate_opening` answer, asked when the prefetch started

#### Scenario: Ask answers are planned
- **WHEN** the user asks Rin a question in an `agent` debate
- **THEN** Rin's answer is planned with `emotion_reply` at its turn start, under the `turn_plan` deadline

### Requirement: Debate plans per profile
`naive` and `scripted` SHALL fill debate slots in fixed order and send no plan, so their speakers are today's while everyone is awake. Their faces SHALL come from their own engines.

#### Scenario: Scripted debate makes no Jev call
- **WHEN** a `scripted` debate runs to its verdict
- **THEN** no `turn_plan`, `debate_plan` or `rubric` ledger row exists

### Requirement: The 1:1 plan takes the deep branch on its gate
In 1:1, when the speaker's "needs documents?" answer is at or above `t_gate`, the plan SHALL continue on its deep branch (see `deep-turn`) and return with the passages it kept, so the reply waits for the whole plan. Otherwise the plan SHALL end quick, as before.

#### Scenario: Deep 1:1 plan
- **WHEN** Amara's 1:1 gate answers p 0.8 with `t_gate` 0.35
- **THEN** the plan's graph path ends with the deep steps, and the reply request holds the kept passages

#### Scenario: Quick 1:1 plan
- **WHEN** her gate answers p 0.1
- **THEN** the plan's graph path ends at `route`, and no `deep_check` request is made

### Requirement: A planned reply in any mode carries its passages
A planned reply that went deep SHALL carry its kept passages, its outcome, its candidates and its query in its frozen plan, in every mode, and the reply engine SHALL read them from there. A planned reply that did not go deep SHALL carry none.

#### Scenario: Group second reply
- **WHEN** a group's second replier goes deep
- **THEN** its frozen plan holds its own kept passages, independent of the first reply's

### Requirement: Only the speaker's gate is used
In a plan that asked "needs documents?" about several candidates, only the speaker's own answer SHALL decide whether their reply goes deep. Every other candidate's gate answer SHALL be recorded as asked but not used.

#### Scenario: Group first slot
- **WHEN** a group plan asks `docs` about Amara and Mei and picks Mei
- **THEN** Mei's gate decides her reply's branch, and Amara's `docs` row is `not_used`

### Requirement: Jev call 1 and the cast plan ask the earlier gate
The 1:1 plan and the cast plan (group, Everyone, Next speaker, Step in, watch) SHALL ask "needs something from earlier?" about each candidate with something to search (see `session-recall`), in the same request as their other questions and with no new state field.

#### Scenario: Group with dropped lines
- **WHEN** a group session with indexed lines plans its first slot over Amara and Mei
- **THEN** the one request holds `earlier:{Amara's id}` and `earlier:{Mei's id}`

### Requirement: A turn goes deep on either gate
A planned reply SHALL take the deep branch when its speaker's documents gate or earlier gate is at or above its threshold, and SHALL run only the parts its gates asked for. Only the speaker's own earlier answer SHALL decide; the others SHALL be recorded as asked but not used.

#### Scenario: Recall only
- **WHEN** Amara's `docs` answer is p 0.1 and her `earlier` answer is p 0.8
- **THEN** her plan goes deep, runs recall, and makes no `deep_check` request about any passage

#### Scenario: Neither
- **WHEN** both of her gates are below their thresholds
- **THEN** the plan ends quick and no `deep_check` request is made

### Requirement: The plan carries the safety cue
The frozen plan SHALL carry the safety decision that applies to its reply (no cue, steer, care, or both, with the stored probabilities), so a replayed turn needs no Jev call and a regenerate uses the stored answer.

#### Scenario: Replay from the plan
- **WHEN** a steered turn's frozen plan is replayed with the Decider unavailable
- **THEN** the reply's request carries the steer sentence, and no decision request is made
