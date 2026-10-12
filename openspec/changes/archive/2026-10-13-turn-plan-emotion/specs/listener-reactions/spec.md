# Spec Delta

## Purpose

How listeners' faces react to a completed line in group, debate and watch: one Jev request after `turn.end`, a code
rule for which reactions show, when pending reactions are dropped, and a reducer guard so a reaction never changes the
face of the character who is speaking.

## ADDED Requirements

### Requirement: Reactions run after the turn
After a completed character reply in AUTO mode in group, debate or watch, the runtime SHALL start one reactions task
for that message. It SHALL never delay the next speaker. 1:1 sessions, interrupted, failed or blocked replies, and
MANUAL mode SHALL get no reactions.

#### Scenario: Next speaker not delayed
- **WHEN** an `agent` group reply ends and Jev's reaction answer is held for 1 s
- **THEN** the next turn's `turn.next` is emitted at the normal turn gap, without waiting for the answer

#### Scenario: No reactions in 1:1
- **WHEN** an `agent` 1:1 reply completes
- **THEN** no `reaction` decision request is made

### Requirement: Listeners are read when the task runs
The task SHALL take its listeners from the session's current state when it runs: present participants who are not
muted, not the speaker, and have enough energy for a reply. A muted or exhausted character SHALL get no Jev question.

#### Scenario: Muted after the reply
- **WHEN** Rin is muted between the reply's `turn.end` and the reactions task starting
- **THEN** the reaction request has no question about Rin

### Requirement: One Jev request per message
Under `agent`, the task SHALL send one `reaction` decision request holding one choice question per listener: the 7
emotions plus `none` ("no visible reaction"), each listener named, with its seed derived as
`"{turn seed}:react:{listenerId}"`. Its state SHALL hold the line and the line before it as quoted text, each
listener's name and short description (and debate side), and the mode. It SHALL NOT show the listener's current face:
Jev anchored on it (design D37); code still uses the face for "differs" and the fades.

#### Scenario: Two listeners
- **WHEN** Hana's group reply completes with Rin and Kai listening
- **THEN** one `reaction` request is sent with the questions `reaction:chr_seedRin` and `reaction:chr_seedKai`

### Requirement: Which reactions show
A reaction SHALL show only if its pick is not `none`, its confidence reaches the reaction floor (0.6 to start), and
its face differs from the listener's current face when it is appended. At most the 2 most confident SHALL show per
message.

#### Scenario: Cap of two
- **WHEN** three listeners get confident, different faces with confidences 0.9, 0.8 and 0.7
- **THEN** only the 0.9 and 0.8 reactions are emitted, each with `source: "classifier"` and its option's `p`

#### Scenario: Same face
- **WHEN** Jev picks `happy` for a listener whose face is already `happy`
- **THEN** no reaction is emitted for that listener

### Requirement: Listener faces fade
A listener whose face is `surprised` or `embarrassed` and who gets no reaction from a pass SHALL get a `neutral`
reaction with `source: "default"` and no `p`, outside the cap of two. This includes muted and exhausted characters,
and passes where Jev failed.

#### Scenario: Muted listener fades
- **WHEN** a muted character's face is `surprised` and another character's reply completes
- **THEN** a `neutral` reaction with source `default` is emitted for them, and no Jev question asks about them

### Requirement: Reaction timing
Each shown reaction SHALL play at its own delay in the shared timing table's `reactionDelayMs` range after `turn.end`,
taken from the derived seed, or as soon as Jev answers if that is later. The reaction request SHALL time out after
1,500 ms, and a late or failed request SHALL show no Jev reaction.

#### Scenario: Late answer
- **WHEN** the reaction request is held past 1,500 ms
- **THEN** no `classifier` reaction is emitted for that message

### Requirement: Pending reactions are dropped
A new user message, switching to MANUAL, Stop, leave, a cap pause and the session's end SHALL drop every pending
reaction. The start of the next turn SHALL drop only that turn's speaker's pending reaction. The check and the append
SHALL happen under the session's single writer, so a reaction is never appended after its listener's `turn.start`.

#### Scenario: The next speaker's reaction
- **WHEN** Rin's reaction to Hana's line is due 600 ms after `turn.end` but Rin's own turn starts at 500 ms
- **THEN** Rin's reaction is never emitted, and Kai's still plays

#### Scenario: A user message
- **WHEN** the user sends a message while two reactions are pending
- **THEN** neither reaction is emitted

### Requirement: Reaction failures never touch the session
Any error in the reactions task, including a budget refusal of the reaction request, SHALL be caught and logged. It
SHALL never pause the session, emit an `error` event, or affect the next turn. Reaction spend SHALL count toward the
daily cap as decision spend and SHALL never drain energy.

#### Scenario: Budget refusal
- **WHEN** the reaction request is refused by the daily cap
- **THEN** no `session.paused` and no `error` event is emitted by the reactions task

### Requirement: Scripted and mock reactions
The scripted predictor SHALL keep its seeded random reactions, run inside the task, and record one simulated
`reaction` call per message only under the `scripted` profile. Under `naive` it SHALL record nothing. The MockClient
SHALL charge the same simulated call and apply the same drop rules.

#### Scenario: Naive group with a key
- **WHEN** a `naive` group reply completes and listeners react
- **THEN** no `reaction` ledger row is written

#### Scenario: Scripted group
- **WHEN** a scripted group reply completes with listeners
- **THEN** one simulated `reaction` row with category `decision` is written, and no energy changes

### Requirement: A reaction never changes the speaker's face
Both reducers SHALL record a reaction on its message but SHALL NOT apply its face when the reacting character is the
author of the message currently streaming, from its `turn.start` to its `turn.end`.

#### Scenario: Reaction during the speaker's own turn
- **WHEN** a reaction for Rin arrives after Rin's `turn.start` and before her `turn.end`
- **THEN** the reaction is on the reacted message's `reactions`, and Rin's portrait face is unchanged
