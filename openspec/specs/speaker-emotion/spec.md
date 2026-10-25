# speaker-emotion Specification

## Purpose
Chooses the speaking character's face before the first word: Jev's pick when it is confident, otherwise the current
face, with short faces fading. Also covers how the face reaches the screen and the trace, and what MANUAL mode does.

## Requirements

### Requirement: The emotion question
Each emotion question SHALL offer the 7 emotions and `none` ("no clear change: keep the current face"), each with a
`what`, a `not_for` and examples, shuffled by a seed derived from the turn's System 1 seed and the question key. A
reply to the user (1:1, a group's first or second reply, Step in) SHALL use `emotion_reply`; a generated greeting
SHALL use `emotion_greeting`; a watch turn after the opening and a group Next speaker SHALL use `emotion_line`; a
watch's first turn SHALL use `emotion_opening`. Each question SHALL name its candidate.

#### Scenario: Same seed, same order
- **WHEN** the same turn is planned twice with the same session seed and turn index
- **THEN** both requests list the options in the same order, and the System 1 section's `seed` is `"{session seed}:{turn index}"`

#### Scenario: A generated greeting
- **WHEN** an `agent` 1:1 session opens for a character who has chatted before
- **THEN** its `turn_plan` request asks `emotion_greeting` for that character, and not `emotion_reply`

#### Scenario: A watch turn
- **WHEN** an `agent` watch plans its fifth turn
- **THEN** its request asks `emotion_line` for each candidate, and not `emotion_reply`

### Requirement: The face rule
The face sent SHALL be Jev's pick when it is not `none` and Jev's confidence reaches the question's floor (0.6 to
start). Otherwise the base face SHALL be kept, except that a kept `surprised` or `embarrassed` face SHALL become
`neutral` (the `emotion.fade` set in the runtime config). While the reply's care cue is on, the face from any of these
paths SHALL be `neutral`, `sad` or `thinking`, and any other face SHALL become `neutral`.

#### Scenario: Confident pick
- **WHEN** Jev picks `sad` with confidence 0.74 for a character whose face is `happy`
- **THEN** the reply's face is `sad` with source `classifier`

#### Scenario: Unsure keeps the face
- **WHEN** Jev picks `angry` with confidence 0.41 for a character whose face is `thinking`
- **THEN** the reply's face is `thinking` with source `default`, and the emotion row's result is `below_threshold`

#### Scenario: A kept short face fades
- **WHEN** Jev answers `none` for a character whose face is `surprised`
- **THEN** the reply's face is `neutral` with source `default`, and the row's action says it faded

#### Scenario: Jev failed
- **WHEN** the `turn_plan` request fails for a character whose face is `embarrassed`
- **THEN** the reply's face is `neutral` with source `default`, and the row's result is `fallback`

#### Scenario: Care keeps the face calm
- **WHEN** Jev picks `happy` with confidence 0.9 for a reply whose care cue is on
- **THEN** the reply's face is `neutral`, and the emotion row's action says the care cue kept it calm

#### Scenario: Care keeps a sad pick
- **WHEN** Jev picks `sad` with confidence 0.8 for a reply whose care cue is on
- **THEN** the reply's face is `sad`

### Requirement: Neutral and none are one answer on a neutral face
When the base face is `neutral`, code SHALL add the probabilities of `neutral` and `none` together as `neutral` before
the pick and floor are decided. When this makes `neutral` the pick, the value compared with the floor SHALL be that
sum, and the row SHALL show the comparison by that name.

#### Scenario: A split between neutral and none
- **WHEN** the base face is `neutral` and Jev answers `none` 0.38, `neutral` 0.35, `happy` 0.27 with confidence 0.38
- **THEN** the face is `neutral` with source `classifier`, and the row compares `p_neutral+p_none` 0.73 with 0.6

### Requirement: The face shows with the first word
The `agent` engine SHALL yield the planned face on the model's first chunk, before any token. The runtime SHALL append
`turn.start` and that `emotion` event in one write, so no other event lands between them. The `agent` path SHALL never
set `turn.start.emotion`. A reply refused before its first chunk SHALL leave no face change.

#### Scenario: One write
- **WHEN** an `agent` 1:1 reply starts streaming
- **THEN** its `turn.start` and `emotion` events have consecutive `seq` values and were stored in one transaction

#### Scenario: Refused reply
- **WHEN** the reply's preflight is refused by the daily cap after the plan chose `happy`
- **THEN** no `turn.start` and no `emotion` event are emitted, and the portrait keeps its face

### Requirement: MANUAL still asks
Under MANUAL emotion mode, the plan SHALL still ask the emotion question. The turn's `emotion` event SHALL carry what
AUTO would have chosen, so it is recorded on the message and in the trace but never shown on the portrait. Its base
face SHALL be the character's last AI-chosen face in this session, else `neutral`, never the face the user set.

#### Scenario: Base face under MANUAL
- **WHEN** the user set Amara's face to `angry`, her last reply's face was `thinking`, and Jev answers `none`
- **THEN** the new message's emotion is `thinking` with source `default`, and the portrait still shows `angry`

### Requirement: The trace explains the face
`TurnTrace.emotion` SHALL hold the face sent, its source, and the top 3 emotions by Jev's probability (`neutral`
merged as above, `none` left out), with no candidates when Jev failed. The System 1 section SHALL hold one emotion row
per candidate asked, with `not_used` for a candidate who did not speak.

#### Scenario: Candidates on a confident turn
- **WHEN** Jev answers `sad` 0.6, `thinking` 0.2, `none` 0.1, `happy` 0.1
- **THEN** the trace's `emotion.candidates` are `sad`, `thinking` and `happy` in that order, without `none`

### Requirement: Insight marks a kept face
When the trace's chosen face is not its top candidate, Insight's Emotion section SHALL show the chip "kept" instead of
the source, and no confidence band next to the chosen face. A face with no candidates SHALL keep its source label.

#### Scenario: Kept face in Insight
- **WHEN** a reply kept `thinking` while Jev's top candidate was `angry` at 0.41
- **THEN** the Emotion section shows `thinking` with the chip "kept" and no band, and the bars list `angry` first

### Requirement: Faces in group and watch come from the plan
Under `agent`, every planned group, watch and debate reply SHALL show its plan's face for its speaker, decided by the same face rule as 1:1 (the floor, keep, fade and the `neutral` + `none` merge). A second reply's face SHALL come from the follow plan, which saw the first reply. A debate rebuttal or closing SHALL take its face from the debate plan (`emotion_line` about the argument just made), an opening from its own plan (`emotion_debate_opening`), and an Ask answer from its plan (`emotion_reply`).

#### Scenario: Second replier reacts to the first
- **WHEN** a follow plan picks Rin and Jev's emotion answer for Rin is `surprised` with enough confidence
- **THEN** Rin's reply shows `surprised` with source `classifier`

#### Scenario: Everyone's prefetched replies
- **WHEN** an `agent` Everyone run prefetches its third reply
- **THEN** that reply's face is the one the run's single plan chose for that speaker

#### Scenario: A rebuttal reacts to the argument it answers
- **WHEN** the debate plan's `emotion_line` answer for Rin about Victor's argument is `angry` with enough confidence
- **THEN** Rin's rebuttal shows `angry` with source `classifier`

#### Scenario: A late face is a kept face
- **WHEN** the debate plan's answer lands after Rin's turn has started
- **THEN** Rin's rebuttal keeps her previous face (or fades it), with the fallback source
