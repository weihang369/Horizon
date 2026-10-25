# Spec Delta

## MODIFIED Requirements

### Requirement: Debate phases
A debate SHALL run its configured phases in order. Each phase SHALL open with a `phase` event and a `ROUND n · LABEL` note, plus host narration when the moderator is `auto_host`. A phase SHALL be a list of slots: alternating prop/opp in two-sided debates (one per member), or one per panellist. Each slot SHALL be filled when it comes up by an eligible member of its side (awake and not yet heard in this phase-iteration): by the debate plan under `agent`, else the first in fixed order. Each turn SHALL be marked `forcedBy: "round_order"` and tagged with phase, round and iteration. With `autoAdvance`, the next turn SHALL start `pauseMs` after the previous one ends.

#### Scenario: Quick debate to a verdict
- **WHEN** a quick two-sided debate (opening, closing) with one debater per side and arbiter verdict runs for 90 seconds of clock time
- **THEN** it holds 4 character messages and a `verdict` message, the session is `ended`, and its state has `phase: "ended"` and `verdict.decidedBy: "arbiter"`

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

## ADDED Requirements

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
When a debate reaches its verdict, the turns each side missed SHALL be computed from the log (the slots of every reached phase-iteration minus that side's arguments), with the reason "asleep" when the side had a skip or pause note there, or "the debate ended early". The verdict's prose SHALL say so plainly.

#### Scenario: A side that slept through a round
- **WHEN** the Opposition missed both rebuttal slots asleep and the user ended the debate during the pause
- **THEN** the verdict work is told "Opposition: 2 turns missed, everyone on that side was asleep"
