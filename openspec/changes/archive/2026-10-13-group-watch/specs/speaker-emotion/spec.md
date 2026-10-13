# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Faces in group and watch come from the plan
Under `agent`, every planned group and watch reply SHALL show its plan's face for its speaker, decided by the same face rule as 1:1 (the floor, keep, fade and the `neutral` + `none` merge). A second reply's face SHALL come from the follow plan, which saw the first reply. Debate replies SHALL keep the speaker's previous face until M11.

#### Scenario: Second replier reacts to the first
- **WHEN** a follow plan picks Rin and Jev's emotion answer for Rin is `surprised` with enough confidence
- **THEN** Rin's reply shows `surprised` with source `classifier`

#### Scenario: Everyone's prefetched replies
- **WHEN** an `agent` Everyone run prefetches its third reply
- **THEN** that reply's face is the one the run's single plan chose for that speaker
