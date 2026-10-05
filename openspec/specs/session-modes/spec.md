# session-modes Specification

## Purpose

Defines what each session command does in each mode (1:1, group, debate and watch): who speaks and when, how the user steers, how debates move through phases to a verdict, and how a watch scene paces itself and stops at its turn cap.

## Requirements

### Requirement: 1:1 conversation
In a 1:1 session, `chat.send` SHALL post the user's message and queue one reply from the single participant. `chat.regenerate(messageId)` SHALL stream a new variant into the same message, keeping earlier variants (D-58: "Continue" means regenerate). Sending to a paused 1:1 session SHALL resume it first (`session.resumed`), unless it is paused by the daily cap and the cap is still reached.

#### Scenario: Regenerate keeps the original
- **WHEN** a completed reply is regenerated
- **THEN** the message has two variants, the new one is active, and the first variant's text is unchanged

#### Scenario: Paused 1:1 auto-resumes
- **WHEN** a 1:1 session was left (`navigated_away`) and a message is sent to it
- **THEN** a `session.resumed` event precedes the user's message, and a reply follows

### Requirement: Group responders
In a group session, `chat.send` SHALL post the user's message, then answer with:
- @mentioned participants first, each marked `forcedSpeaker`;
- then responders by policy: `auto` adds router picks up to 2 responders in all, `everyone` adds every other eligible participant, `mentioned` adds none.

Muted participants SHALL be skipped as `muted`, and exhausted unmentioned ones as `exhausted`.

#### Scenario: Auto policy with a mention
- **WHEN** a three-person group with policy `auto` receives a message mentioning one participant
- **THEN** that participant replies first with `forcedSpeaker: true`, and at most one other participant replies

### Requirement: Group routing is traced
When the router chooses responders, every reply of that turn SHALL carry a routing trace with the question, the selected speaker and the candidates' probabilities. `TurnTrace.calls` SHALL include the paid `route` decision. When the router falls back (timeout or failure), the trace SHALL mark the fallback and carry no candidates.

#### Scenario: Route call in the trace
- **WHEN** a group message gets automatic responders and the replies complete
- **THEN** at least one reply's `trace.calls` has an entry with `purpose: "route"`

### Requirement: Group steering commands
`chat.everyoneAnswer` SHALL queue a reply from every unmuted participant to the last user message. `chat.nextSpeaker(characterId?)` SHALL queue one reply: from the named participant (`forcedBy: "nudge"`), or else from a random eligible participant who did not speak last. `chat.muteParticipant` SHALL toggle `mutedByUser` through a `session.state` participants event.

#### Scenario: Muted participant is skipped
- **WHEN** a participant is muted and `everyoneAnswer` is sent
- **THEN** every other participant replies, and the muted one does not

### Requirement: Session settings commands
`chat.setEmotionMode`, `chat.setResponderPolicy`, `chat.setMusicPolicy` and `chat.setReadableMode` SHALL each emit one `session.state` event carrying only the changed settings. `chat.setEmotion` SHALL emit an `emotion` event with no `messageId` and `source: "user"`.

#### Scenario: Readable mode on
- **WHEN** `chat.setReadableMode(sid, true)` is sent
- **THEN** one `session.state` event with `settings: { readableMode: true }` is emitted, and the session reads `readableMode: true`

### Requirement: Debate phases
A debate SHALL run its configured phases in order. Each phase SHALL open with a `phase` event and a `ROUND n · LABEL` note, plus host narration when the moderator is `auto_host`. Speakers SHALL alternate prop/opp in two-sided debates, or follow cast order in a panel, each marked `forcedBy: "round_order"` and tagged with phase, round and iteration. With `autoAdvance`, the next turn SHALL start `pauseMs` after the previous one ends.

#### Scenario: Quick debate to a verdict
- **WHEN** a quick two-sided debate (opening, closing) with one debater per side and arbiter verdict runs for 90 seconds of clock time
- **THEN** it holds 4 character messages and a `verdict` message, the session is `ended`, and its state has `phase: "ended"` and `verdict.decidedBy: "arbiter"`

### Requirement: Debate moderation
- `debate.pause` and `debate.resume` SHALL hold and continue auto-advance.
- `debate.next` SHALL run one step.
- `debate.extendRound` SHALL repeat the current phase as the next iteration.
- `debate.skipToClosing` SHALL jump to closing at the next boundary.
- `debate.askCharacter` SHALL post a `steer` message and run that debater's answer next.
- `debate.interject` SHALL post an `interject` message.

Steering SHALL land at the next turn boundary, never inside a streaming reply.

#### Scenario: Ask lands at the boundary
- **WHEN** Ask is sent to a debater while another debater's reply is streaming
- **THEN** the streaming reply completes, and then the asked debater answers with `forcedSpeaker: true` and `forcedBy: "user_ask"`

### Requirement: Debate verdict
After the last phase, a `verdict` phase SHALL begin. With `verdictBy` `arbiter`, a paid decision SHALL produce a `Verdict` with rubric scores from 0 to 10, a `verdict` message, and the session ended. With `user`, the debate SHALL wait for `debate.pickStrongerCase(side)`. `debate.endDebate(withVerdict)` SHALL end the debate early, with or without a verdict.

#### Scenario: User decides
- **WHEN** a debate with `verdictBy: "user"` reaches the verdict phase and the user picks `prop`
- **THEN** the verdict has `decidedBy: "user"` and `strongerCase: "prop"`, and the session is ended

### Requirement: Watch pacing and the turn cap
A watch SHALL post its premise as a `direction` message and play turns round-robin from the opening speaker, waiting `paceMs` between turns on the session clock. Each turn SHALL increment `turnsTaken` (`watch.state` + `session.state`). When `turnsTaken` reaches `turnLimit`, the watch SHALL stop with `session.paused { reason: "turn_cap" }`. `watch.extendWatch(n)` (default 10) SHALL raise the limit and resume.

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
