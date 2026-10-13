# Spec Delta

## MODIFIED Requirements

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
and in watch "is the talk finished?". No gate question SHALL be asked before M12. Its state SHALL be the turn-plan
state (see `conversation-context`) for that turn, with no document titles. The request SHALL be recorded as decision
spend and SHALL never drain energy.

#### Scenario: One request for the turn
- **WHEN** an `agent` 1:1 reply is planned
- **THEN** exactly one `turn_plan` request is sent, with one question keyed `emotion_reply:{characterId}` and a state holding `mode`, `quoted_user`, `quoted_cast`, `quoted_latest` and `quoted_recent`

#### Scenario: No gate questions yet
- **WHEN** an `agent` 1:1 reply is planned for a character with indexed knowledge
- **THEN** the request holds no "needs documents?" or "needs something from earlier?" question

#### Scenario: A group's call 1
- **WHEN** an `agent` group of three with no mention is planned
- **THEN** the one request holds `who_first` and three `emotion_reply:{characterId}` questions

## ADDED Requirements

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
