# Spec Delta

## MODIFIED Requirements

### Requirement: Route rows
Every reply started by a router's decision (`naive` and `scripted` group routing) SHALL carry one `route` row. With Jev, the row SHALL hold the picked participant's ID (or `none`), its probability and the confidence, with result `used`. On a fallback, the result SHALL be `fallback`. The scripted profile and the MockClient SHALL take the row's fixed fields from the shared System 1 fixture, and fill the answer from the actual routing.

#### Scenario: Two replies from one decision
- **WHEN** a group message gets replies from Hana and then Rin under one routing decision
- **THEN** both replies' traces carry the same `route` row

#### Scenario: Scripted group turn
- **WHEN** a scripted group turn is answered by Mei
- **THEN** its trace's `route` row has the fixture's label and `p`, and the answer is Mei's ID

## ADDED Requirements

### Requirement: Who-speaks rows
A reply whose speaker was chosen by a plan's who-speaks question SHALL carry that question's row: the pick's ID as its answer, its `p` and confidence, the floor comparison, and an action ("answers first", "speaks next", "speaks second", "sets the order"). An unsure pick SHALL have `result: "below_threshold"`; a failed or late call SHALL have `result: "fallback"` and no `p`. A speaker forced by a mention, a nudge or the guard SHALL have no who-speaks row.

#### Scenario: Group first slot
- **WHEN** Jev picks Hana confidently for an `agent` group's first slot
- **THEN** Hana's trace has a `who_first` row with answer Hana's ID, `result: "used"` and action "answers first"

#### Scenario: Guard turn
- **WHEN** a watch turn's speaker is forced by the nobody-left-out rule
- **THEN** its trace has no `who_scene` row

### Requirement: Rows carry the call's purpose
A row SHALL carry the purpose of the request that asked it, so the same bank question asked by call 1 and by a follow plan keeps two rows (`turn_plan` and `follow_plan`) under the row key (purpose, id, about).

#### Scenario: Emotion asked twice
- **WHEN** Rin's emotion is asked in call 1 (not used) and again in the follow plan that picks Rin
- **THEN** Rin's reply has an `emotion_reply` row with purpose `follow_plan`, and no call-1 emotion row about Rin is marked `used`

### Requirement: Rows of a plan that starts several replies
Each reply started by a cast plan SHALL carry the plan's shared rows (who speaks, "is the talk finished?") plus the rows about its own speaker. Other candidates' rows SHALL be marked `not_used` on a group first reply, a Next speaker reply and a watch turn. An Everyone reply SHALL carry only its own speaker's rows, plus the shared order row.

#### Scenario: Everyone rows
- **WHEN** an `agent` Everyone run of three replies completes
- **THEN** each reply carries the `who_first` order row and exactly one `emotion_reply` row, about its own speaker

### Requirement: Talk-finished rows
Every planned watch turn after the opening SHALL carry one `talk_finished` row with `p`, the `t_end` comparison and an action: "steer", "no steer", "no steer (steered recently)" or "no steer (director's note)". A failed or late call SHALL give `result: "fallback"` and action "no steer".

#### Scenario: Steered turn
- **WHEN** a watch turn's "is the talk finished?" answer is p 0.86 with `t_end` 0.8 and no recent steer
- **THEN** its row has answer `yes`, comparison 0.86 ≥ 0.8, `result: "used"` and action "steer"

### Requirement: A plan that is dropped writes nothing
A cast or follow plan cancelled by `clear()`, by a newer user message or by a changed plan-ahead fingerprint SHALL write no System 1 rows anywhere.

#### Scenario: Superseded follow plan
- **WHEN** a follow plan is cancelled by a new user message
- **THEN** neither the first reply nor any later reply gains a `follow_plan` row from it
