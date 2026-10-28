# session-modes Specification

## Purpose

Defines what each session command does in each mode (1:1, group, debate and watch): who speaks and when, how the user steers, how debates move through phases to a verdict, and how a watch scene paces itself and stops at its turn cap.

## Requirements

### Requirement: 1:1 conversation
In a 1:1 session, `chat.send` SHALL post the user's message and queue one reply from the single participant. `chat.regenerate(messageId)` SHALL stream a new variant into the same message, keeping earlier variants (D-58; an interrupted reply offers one chip, Regenerate). Sending to a paused 1:1 session SHALL resume it first (`session.resumed`), unless it is paused by the daily cap and the cap is still reached. Under the `agent` profile in M9, a 1:1 turn SHALL retrieve no knowledge and no memories, and a sent message SHALL start no query embedding, until the plan's gates exist.

#### Scenario: Regenerate keeps the original
- **WHEN** a completed reply is regenerated
- **THEN** the message has two variants, the new one is active, and the first variant's text is unchanged

#### Scenario: Paused 1:1 auto-resumes
- **WHEN** a 1:1 session was left (`navigated_away`) and a message is sent to it
- **THEN** a `session.resumed` event precedes the user's message, and a reply follows

#### Scenario: Agent 1:1 is quick
- **WHEN** a message is sent to an `agent` 1:1 session whose character has indexed knowledge
- **THEN** no `query_embed` ledger row is written, and the reply's trace has no `knowledge` section

### Requirement: Group responders
In a group session, `chat.send` SHALL post the user's message, then answer with:
- @mentioned participants first, each marked `forcedSpeaker`;
- then responders by policy: `auto` adds one first responder when nobody is mentioned (someone always answers) and,
  under `agent`, at most one second responder chosen after the first reply by the follow plan (see `follow-plan`), or
  under `naive` and `scripted` the router's up-front picks, up to 2 responders in all; `everyone` adds every other
  eligible participant; `mentioned` adds none.

Muted participants SHALL be skipped as `muted`, and exhausted unmentioned ones as `exhausted`. A muted participant SHALL
never reply, even when mentioned: each muted mention SHALL get the note "{name} is muted." and be dropped from the mentions,
and when every mention was muted nobody else SHALL answer. That note is for the user: it SHALL NOT enter any prompt or summary. When every mentioned participant is asleep, each SHALL get the
asleep note and nobody else SHALL answer, in every profile.

#### Scenario: A muted participant is mentioned
- **WHEN** a participant is muted and the user's message mentions only them
- **THEN** the log gets "{name} is muted." and nobody replies

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

### Requirement: Session settings commands
`chat.setEmotionMode`, `chat.setResponderPolicy`, `chat.setMusicPolicy` and `chat.setReadableMode` SHALL each emit one `session.state` event carrying only the changed settings. Switching the emotion mode to MANUAL SHALL drop every pending listener reaction. `chat.setEmotion` SHALL emit an `emotion` event with no `messageId` and `source: "user"`.

#### Scenario: Readable mode on
- **WHEN** `chat.setReadableMode(sid, true)` is sent
- **THEN** one `session.state` event with `settings: { readableMode: true }` is emitted, and the session reads `readableMode: true`

#### Scenario: MANUAL drops reactions
- **WHEN** `chat.setEmotionMode(sid, "user")` is sent while two reactions are pending
- **THEN** neither reaction is emitted

### Requirement: Debate phases
A debate SHALL run its configured phases in order. Each phase SHALL open with a `phase` event and a `ROUND n · LABEL` note, plus host narration when the moderator is `auto_host`. A phase SHALL be a list of slots: alternating prop/opp in two-sided debates (one per member), or one per panellist. Each slot SHALL be filled when it comes up by an eligible member of its side (awake and not yet heard in this phase-iteration): by the debate plan under `agent`, else the first in fixed order. Each turn SHALL be marked `forcedBy: "round_order"` and tagged with phase, round and iteration. With `autoAdvance`, the next turn SHALL start `pauseMs` after the previous one ends.
A debate loaded from storage while active and un-held (after a restart or an idle release) SHALL go on auto-advancing from its first command, after that command's own work (an Ask's answer speaks first); a debate whose actor started or stepped it SHALL never gain a second chain.

#### Scenario: Quick debate to a verdict
- **WHEN** a quick two-sided debate (opening, closing) with one debater per side and arbiter verdict runs for 90 seconds of clock time
- **THEN** it holds 4 character messages and a `verdict` message, the session is `ended`, and its state has `phase: "ended"` and `verdict.decidedBy: "arbiter"`

#### Scenario: A debate loaded mid-round goes on after its first command
- **WHEN** an auto-advance debate's actor is released mid-round, 20 seconds pass, and the user then asks Mei a question
- **THEN** nothing moves during the 20 seconds; Mei answers once, then the remaining slots run in order and the debate ends

#### Scenario: Fixed order while everyone is awake
- **WHEN** a `scripted` 2 v 2 Standard debate runs with everyone awake
- **THEN** each phase's speakers are prop[0], opp[0], prop[1], opp[1], as before this change

#### Scenario: A side heard already skips the slot
- **WHEN** in the rebuttal, the Proposition's second slot comes up, Amara (already heard) is awake and Rin is asleep
- **THEN** the note "Rin is asleep, skipping." is added, the slot is used, and the debate continues with the Opposition

#### Scenario: The cursor survives an idle release
- **WHEN** a debate is released while idle after the rebuttal's second slot and is then resumed
- **THEN** the third slot of the rebuttal is the next to run, counting arguments and skip notes since the round's banner

### Requirement: Debate moderation
- `debate.pause` and `debate.resume` SHALL hold and continue auto-advance.
- `debate.next` SHALL run one step.
- `debate.extendRound` SHALL repeat the current phase as the next iteration.
- `debate.skipToClosing` SHALL jump to closing at the next boundary.
- `debate.askCharacter` SHALL post a `steer` message and run that debater's answer next.
- `debate.interject` SHALL post an `interject` message, and under `agent` the next argument's cue SHALL take the moderator's note into account.

Steering SHALL land at the next turn boundary, never inside a streaming reply. Steering that changes what a stored debate plan, host line or verdict work was made from SHALL make it be redone or dropped.

#### Scenario: Ask lands at the boundary
- **WHEN** Ask is sent to a debater while another debater's reply is streaming
- **THEN** the streaming reply completes, and then the asked debater answers with `forcedSpeaker: true` and `forcedBy: "user_ask"`

#### Scenario: Interject reaches the next argument once
- **WHEN** the moderator interjects during an `agent` rebuttal and two more arguments follow
- **THEN** the first of them carries "Take the moderator's last note into account." in its cue, and the second doesn't

### Requirement: Debate verdict
After the last phase, a `verdict` phase SHALL begin, and its work SHALL follow the debate-verdict capability. With `verdictBy` `arbiter`, the verdict SHALL be delivered with rubric scores from 0 to 10 (or a summary only when scoring failed), a `verdict` message, and the session ended. With `user`, the verdict SHALL be delivered after `debate.pickStrongerCase(side)`, which never waits for the work. `debate.endDebate(withVerdict)` SHALL end the debate early, with or without a verdict.

#### Scenario: User decides
- **WHEN** a debate with `verdictBy: "user"` reaches the verdict phase and the user picks `prop`
- **THEN** the verdict has `decidedBy: "user"` and `strongerCase: "prop"`, and the session is ended

### Requirement: Watch pacing and the turn cap
A watch SHALL post its premise as a `direction` message and play turns from the opening speaker, waiting `paceMs` between turns on the session clock: round-robin under `naive` and `scripted`, and by the watch direction rules under `agent` (see `watch-direction`). Each turn SHALL increment `turnsTaken` (`watch.state` + `session.state`). When `turnsTaken` reaches `turnLimit`, the watch SHALL stop with `session.paused { reason: "turn_cap" }`. `watch.extendWatch(n)` (default 10) SHALL raise the limit and resume.

#### Scenario: Stop at the cap, then extend
- **WHEN** a two-character watch with `maxTurns` 10 and `paceMs` 500 runs for 200 seconds of clock time, and is then extended by 10
- **THEN** it stops with exactly 10 character messages and `pausedReason: "turn_cap"`, and after the extension more than 10 character messages exist

### Requirement: Watch controls
- `watch.play` and `watch.pause` SHALL toggle playing.
- `watch.step` SHALL run exactly one turn while paused.
- `watch.setPace` SHALL change `paceMs` for the next gap.
- `watch.direct` SHALL post a `direction` note that colours the next 2 turns.
- `watch.stepIn` SHALL pause, post the user's line, and let up to 2 characters reply.
- `chat.nextSpeaker` SHALL choose the next watch speaker.
- `watch.summarise` SHALL post a `summary` message.

When everyone is exhausted, the watch SHALL pause with a note.

#### Scenario: Step while paused
- **WHEN** a paused watch receives `watch.step`
- **THEN** exactly one character turn runs, and the watch stays paused

### Requirement: Pacing uses the session clock
All waits in live sessions SHALL use the backend clock: greeting delay, first token, streaming speed, turn gaps, debate pauses, watch pace and reaction delays. With the test clock frozen, nothing SHALL advance until the clock is advanced. The pacing values SHALL come from the same committed timing table that the MockClient uses.

#### Scenario: Frozen clock holds the greeting
- **WHEN** the test clock is frozen and a 1:1 session is created
- **THEN** no character message exists until the clock is advanced past the greeting delay and the first-token time

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

### Requirement: A side with nobody awake pauses the debate
When a slot comes up and nobody on its side is awake (in a panel, nobody on the panel), the debate SHALL pause in every profile. Every asleep member of that side SHALL get the note "{name} is asleep (⚡ {current})." with `energy_exhausted`. A system note SHALL say "The Proposition is asleep. Top someone up to continue the debate." (Opposition, or "Everyone on the panel is asleep. …"). `session.paused` SHALL have reason `user`, and the slot SHALL be kept.

#### Scenario: The Opposition falls asleep
- **WHEN** both Opposition members are asleep when the Opposition's closing slot comes up
- **THEN** each gets an asleep note with Top up, the system note names the Opposition, the session pauses with reason `user`, and no Proposition argument follows

#### Scenario: The slot runs after a top-up
- **WHEN** the user tops up Victor and presses ▶
- **THEN** the same Opposition closing slot runs, with Victor speaking

#### Scenario: Play without a top-up
- **WHEN** the user presses ▶ without a top-up
- **THEN** the debate pauses again with the same notes

### Requirement: The verdict knows the missed turns
When a debate reaches its verdict, the turns each side missed SHALL be computed from the log (the slots of every reached phase-iteration minus that side's arguments), with the reason "asleep" when most of them were missed in a phase-iteration where the side had a skip or pause note (an Ask to an asleep member uses no slot and gives no reason), or "the debate ended early". The verdict's prose SHALL say so plainly.

#### Scenario: A side that slept through a round
- **WHEN** the Opposition missed both rebuttal slots asleep and the user ended the debate during the pause
- **THEN** the verdict work is told "Opposition: 2 turns missed, everyone on that side was asleep"
