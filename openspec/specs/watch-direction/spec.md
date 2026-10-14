# watch-direction Specification

## Purpose
Decides who speaks next in an `agent` watch and keeps the scene moving: a nudge first, then a rule that nobody is left
out, then Jev's pick; a steer when the thread has run dry; and the next plan made during the wait between turns.

## Requirements

### Requirement: The order of precedence for the next watch speaker
Under `agent` with a key, each watch turn's speaker SHALL be: a Speak next nudge when one is set; else a character silent for 2 full rounds (the guard); else Jev's `who_scene` pick over the awake, unmuted cast without the last speaker, with no `none`. With one candidate left, no who question SHALL be asked. `scripted` and `naive` SHALL keep round-robin.

#### Scenario: Never twice in a row
- **WHEN** an `agent` watch with three awake characters runs 30 turns with scripted Jev answers that always favour the last speaker
- **THEN** no character speaks two turns in a row

#### Scenario: Naive stays round-robin
- **WHEN** a `naive` watch with three characters runs 6 turns
- **THEN** the speakers follow cast order from the opening speaker, twice

### Requirement: Nobody is left out
A character SHALL be forced next when at least 2 rounds of character messages exist since the premise and none of the last 2 rounds is theirs, where a round is the number of awake, unmuted characters. It SHALL be counted from the stored messages, so it survives an idle release. Several qualifying: the one silent longest. The trace SHALL say `forcedBy: "round_order"` and give the reason.

#### Scenario: The guard fires
- **WHEN** in an `agent` watch with three awake characters, Mei has not spoken in the last 6 character messages
- **THEN** Mei speaks next, her trace has `routing.forcedBy: "round_order"` and `routing.reason` "Mei hadn't spoken for 6 turns.", and no `who_scene` row

#### Scenario: Survives a release
- **WHEN** the session's actor is released while idle and rebuilt, and the next turn runs
- **THEN** the guard's count is the same as before the release

### Requirement: The Auto opening asks Jev
In an `agent` watch whose opening speaker is "Auto", the first turn SHALL ask `who_scene` with the premise and no lines, and `emotion_opening` per candidate, and no "is the talk finished?" question. A chosen opening speaker SHALL be forced.

#### Scenario: Auto opening
- **WHEN** an `agent` watch with opening speaker "Auto" starts
- **THEN** its first `turn_plan` request holds `who_scene` and one `emotion_opening` question per character, and no `talk_finished` question

### Requirement: The steer
Every planned watch turn after the opening SHALL ask "is the talk finished?". A probability at or above `t_end` SHALL add the steer sentence to that turn's cue, unless a steer happened in the last 2 character turns (read from their stored traces) or a director's note is active. A failed or late answer SHALL never steer. The scene SHALL still end only at its turn limit, the daily cap or when everyone is asleep.

#### Scenario: Steer, then cap
- **WHEN** Jev answers "is the talk finished?" with p 0.9 on three turns in a row, and `t_end` is 0.8
- **THEN** only the first of those turns carries the steer sentence, and the next two traces' rows say "no steer (steered recently)"

#### Scenario: No steer during a note
- **WHEN** a director's note was posted one turn ago and Jev answers p 0.95
- **THEN** the turn carries no steer sentence, and the row's action is "no steer (director's note)"

### Requirement: The next plan is made during the wait
After an `agent` watch turn's `turn.end`, the next turn's plan SHALL start at once, unless the turn was a manual Step, the scene is paused, the turn limit is reached or the session is ending. It SHALL wait for Jev until the next turn is due. No reply SHALL be generated ahead.

#### Scenario: Hidden by the pace
- **WHEN** an `agent` watch at Normal pace has Jev answer the next plan in 1.2 seconds
- **THEN** the next turn uses that plan with no fallback, and its `turn.next` comes when the pace timer fires

#### Scenario: None at the limit
- **WHEN** a watch turn reaches the turn limit
- **THEN** no further `turn_plan` request is made

### Requirement: A plan made ahead is redone when its inputs change
A plan made ahead SHALL be stored with a fingerprint of its inputs: the actor's clear epoch, the reply epoch, the last message's sequence number, the director's note and its turns left, the nudge, the emotion mode, and each participant's awake, muted and face state. At turn time, a different fingerprint SHALL discard the stored plan (cancelling its request if it is still waiting, recorded `cancelled`) and plan again.

#### Scenario: A director's note in the gap
- **WHEN** a director's note is posted while the next plan is being made ahead
- **THEN** that plan is not used: a new `turn_plan` request is made for the turn, and the turn uses the new plan

#### Scenario: Unchanged inputs
- **WHEN** nothing happens between `turn.end` and the next turn
- **THEN** exactly one `turn_plan` request is made for that next turn

### Requirement: Clearing the session cancels a plan made ahead
Stop, leave, a cap pause, Summarise and the session's end SHALL cancel a plan being made ahead, and it SHALL write nothing to any trace.

#### Scenario: Stop during the gap
- **WHEN** the user presses Stop while a plan is being made ahead
- **THEN** the plan's request is recorded `cancelled`, no `turn.next` follows, and the session's writer is free

### Requirement: Who speaks next is judged on fit, not on turns since
Jev's who-speaks question for a watch turn (`who_scene`) and a group Next speaker (`who_next`) SHALL see no "last spoke" label on the candidates. Fairness SHALL stay with code: the nobody-left-out guard SHALL keep counting turns since each character last spoke from the log.

#### Scenario: The guard still forces the silent
- **WHEN** a character has been silent for two full rounds in an `agent` watch
- **THEN** the guard forces them next with `forcedBy: "round_order"`, though the scene question's state carries no `last_spoke`

#### Scenario: The question sees no turn counts
- **WHEN** an `agent` watch turn asks `who_scene`
- **THEN** its state's cast entries have names, roles, `about` and faces, and no `last_spoke`
