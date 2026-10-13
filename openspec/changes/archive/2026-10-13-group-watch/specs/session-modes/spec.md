# Spec Delta

## MODIFIED Requirements

### Requirement: Group responders
In a group session, `chat.send` SHALL post the user's message, then answer with:
- @mentioned participants first, each marked `forcedSpeaker`;
- then responders by policy: `auto` adds one first responder when nobody is mentioned (someone always answers) and,
  under `agent`, at most one second responder chosen after the first reply by the follow plan (see `follow-plan`), or
  under `naive` and `scripted` the router's up-front picks, up to 2 responders in all; `everyone` adds every other
  eligible participant; `mentioned` adds none.

Muted participants SHALL be skipped as `muted`, and exhausted unmentioned ones as `exhausted`. When every mentioned
participant is asleep, each SHALL get the asleep note and nobody else SHALL answer, in every profile.

#### Scenario: Auto policy with a mention
- **WHEN** a three-person group with policy `auto` receives a message mentioning one participant
- **THEN** that participant replies first with `forcedSpeaker: true`, and at most one other participant replies

#### Scenario: Someone always answers
- **WHEN** a group with policy `auto` receives a message mentioning nobody, and Jev's routing answer would favour nobody
- **THEN** exactly one participant answers first, in every profile with a key

#### Scenario: Asleep mention
- **WHEN** a group message mentions only Rin, who is asleep
- **THEN** Rin gets the asleep note with Top up, and no other participant replies

### Requirement: Group routing is traced
When the router or the planner chooses responders, every reply of that turn SHALL carry a routing trace with the
question, the selected speaker and the candidates' probabilities. `TurnTrace.calls` SHALL include the paid decision
that chose the speaker: `route` under `naive` and `scripted`, `turn_plan` or `follow_plan` under `agent`. When the
choice falls back (timeout or failure), the trace SHALL mark the fallback and carry no candidates.

#### Scenario: Route call in the trace
- **WHEN** a `naive` group message gets automatic responders and the replies complete
- **THEN** at least one reply's `trace.calls` has an entry with `purpose: "route"`

#### Scenario: Plan call in the trace
- **WHEN** an `agent` group message gets automatic responders and the replies complete
- **THEN** the first reply's `trace.calls` has an entry with `purpose: "turn_plan"`, and its `routing.question` is "who answers first?"

### Requirement: Group steering commands
`chat.everyoneAnswer` SHALL queue a reply from every unmuted participant to the last user message. `chat.nextSpeaker(characterId?)` SHALL queue one reply: from the named participant (`forcedBy: "nudge"`), or else from an eligible participant who did not speak last, chosen at random under `naive` and `scripted` and by the planner under `agent`. Under `agent`, Everyone's speaking order SHALL follow one plan's probabilities. `chat.muteParticipant` SHALL toggle `mutedByUser` through a `session.state` participants event.

#### Scenario: Muted participant is skipped
- **WHEN** a participant is muted and `everyoneAnswer` is sent
- **THEN** every other participant replies, and the muted one does not

#### Scenario: Everyone in Jev's order
- **WHEN** an `agent` group's Everyone run is planned and Jev ranks Rin above Hana above Mei
- **THEN** the replies come from Rin, then Hana, then Mei, and only one `turn_plan` request is made for the run

#### Scenario: Next speaker under agent
- **WHEN** `chat.nextSpeaker` is sent with no character in an `agent` group whose last speaker was Hana
- **THEN** the planner's `who_next` question does not offer Hana, and the reply's cue carries "Nobody asked you directly"

### Requirement: Watch pacing and the turn cap
A watch SHALL post its premise as a `direction` message and play turns from the opening speaker, waiting `paceMs` between turns on the session clock: round-robin under `naive` and `scripted`, and by the watch direction rules under `agent` (see `watch-direction`). Each turn SHALL increment `turnsTaken` (`watch.state` + `session.state`). When `turnsTaken` reaches `turnLimit`, the watch SHALL stop with `session.paused { reason: "turn_cap" }`. `watch.extendWatch(n)` (default 10) SHALL raise the limit and resume.

#### Scenario: Stop at the cap, then extend
- **WHEN** a two-character watch with `maxTurns` 10 and `paceMs` 500 runs for 200 seconds of clock time, and is then extended by 10
- **THEN** it stops with exactly 10 character messages and `pausedReason: "turn_cap"`, and after the extension more than 10 character messages exist

## ADDED Requirements

### Requirement: A user message cancels the previous message's unannounced replies
In group and on Step in, in every profile, a new user message SHALL cancel every reply to an earlier message that has not emitted `turn.next`: a follow plan in flight and its second reply, the rest of an Everyone run, unreleased prefetches and queued reply jobs. A reply that has emitted `turn.next` SHALL run to its end, and a streaming reply SHALL never be cut by a send.

#### Scenario: Sent in the gap
- **WHEN** a group message gets its first reply, and the user sends another message before the second reply's `turn.next`
- **THEN** no second reply to the first message appears, and the new message is answered

#### Scenario: Announced reply finishes
- **WHEN** the user sends a message after a reply's `turn.next` but before its first token
- **THEN** that reply streams and completes before the new message is answered

#### Scenario: Mock parity
- **WHEN** the shared supersede contract test runs on the scripted backend and on the MockClient
- **THEN** both produce the same sequence of event types and speakers

### Requirement: Step in follows the group rule under agent
Under `agent`, `watch.stepIn` SHALL pause, post the user's line, and answer with one character chosen by the planner (no `none`), then at most one more chosen by the follow plan. Under `naive` and `scripted`, it SHALL keep letting up to 2 characters reply.

#### Scenario: Step in under agent
- **WHEN** the user steps into an `agent` watch with three awake characters
- **THEN** one character answers first with no random pick, and a second answers only if the follow plan picks one

### Requirement: Agent group and watch retrieve nothing before M12
Under `agent`, a group or watch turn SHALL retrieve no knowledge and no memories, and no user message SHALL start a query embedding, until the plan's gates exist.

#### Scenario: Agent group is quick
- **WHEN** a message is sent to an `agent` group whose characters have indexed knowledge
- **THEN** no `query_embed` ledger row is written, and no reply's trace has a `knowledge` section
