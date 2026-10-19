# system1-trace Specification

## Purpose

The System 1 trace records every Jev question behind a character turn (its answer, probability, the comparisons code made, and what code did) and shows it in Insight. It is the product's "see the AI think" view of System 1.

## Requirements

### Requirement: One row per question asked
A turn's trace SHALL carry an optional `system1` section: an optional `seed`, and at most 64 question rows. Each row SHALL hold:
- the purpose;
- the bank id, version and label;
- an optional `about` (an ID only, never text);
- the answer;
- an optional `p` and `confidence`;
- the comparisons made, each `{name, value, threshold}`;
- the result: `used`, `below_threshold`, `fallback`, `not_used` or `shown_only`;
- an optional `action`.

A fallback row SHALL have no `p`.

#### Scenario: Fallback row
- **WHEN** the route decision times out
- **THEN** the reply's `system1` has a `route` row with `result: "fallback"`, an answer naming what the fallback did, and no `p`

### Requirement: Only the runtime writes the section
The `system1` section SHALL be written only by the runtime. A trace patch from an AI port that sets it SHALL be dropped, and the rest of the patch kept.

#### Scenario: Engine patch rejected
- **WHEN** a turn engine emits a trace patch with `system1` and `context`
- **THEN** the stored trace keeps the runtime's `system1` and the engine's `context`

### Requirement: Rows appended after the turn
The runtime SHALL add rows to a finished message through one operation that runs inside the session's single writer. The operation SHALL:
- read the message's current trace;
- drop the rows if the message's active variant has changed;
- merge rows by `(purpose, id, about)`, so a later row replaces an earlier one;
- append the new paid calls;
- emit the full trace as `insight`, keeping the stored engine metadata and creation time.

#### Scenario: After Regenerate
- **WHEN** rows are appended for variant A after the user regenerated the message to variant B
- **THEN** nothing is written, and the stored trace is unchanged

#### Scenario: Merge by key
- **WHEN** a row `(face_check, face, —)` is appended twice with different answers
- **THEN** the trace holds one such row, with the second answer

#### Scenario: Engine metadata kept
- **WHEN** an `insight` is appended to a message whose trace was written by engine `naive` version 2
- **THEN** the stored trace row still names engine `naive` version 2 and its original creation time

### Requirement: Appends to a streaming reply wait for its end
When the target message is still streaming, appended rows SHALL be merged into its in-progress trace without emitting anything. The turn's final trace SHALL merge them by key rather than replace them.

#### Scenario: Rows land mid-stream
- **WHEN** rows are appended while their target reply is streaming
- **THEN** no `insight` is emitted before `turn.end`, and the final `insight` includes the rows

### Requirement: Appends never restore forgotten memories
In the same transaction as the append, any recalled-memory entry and any `system1` row whose `about` names a memory that no longer exists SHALL be removed from the trace before it is stored.

#### Scenario: Forget between queue and write
- **WHEN** a memory is forgotten after an append naming it was queued, but before the append is written
- **THEN** the stored trace has no row about that memory, and no recalled entry with its text

### Requirement: The row limit
A trace SHALL be cut to 64 rows before it is sent, removing `not_used` rows first.

#### Scenario: Too many rows
- **WHEN** a turn produces 70 rows, 10 of them `not_used`
- **THEN** the emitted trace has 64 rows, and 4 `not_used` rows remain

### Requirement: Route rows
Every reply started by a router's decision (`naive` and `scripted` group routing) SHALL carry one `route` row. With Jev, the row SHALL hold the picked participant's ID (or `none`), its probability and the confidence, with result `used`. On a fallback, the result SHALL be `fallback`. The scripted profile and the MockClient SHALL take the row's fixed fields from the shared System 1 fixture, and fill the answer from the actual routing.

#### Scenario: Two replies from one decision
- **WHEN** a group message gets replies from Hana and then Rin under one routing decision
- **THEN** both replies' traces carry the same `route` row

#### Scenario: Scripted group turn
- **WHEN** a scripted group turn is answered by Mei
- **THEN** its trace's `route` row has the fixture's label and `p`, and the answer is Mei's ID

### Requirement: The Insight section
The Insight drawer SHALL show a "System 1 · Jev" section after Emotion:
- rows grouped by purpose, each group headed by its latency or "fallback";
- each row with its label, answer, `p` or confidence and its band, comparisons as "value ≥ threshold", and the action;
- `not_used` rows folded under "asked about the others (n)";
- IDs resolved to names or titles.

The section SHALL be hidden when there are no rows, and absent in Compact mode.

#### Scenario: No rows
- **WHEN** a `naive` 1:1 reply's Insight is opened
- **THEN** no System 1 section shows

#### Scenario: Route row shown
- **WHEN** a naive group reply's Insight is opened
- **THEN** the System 1 section shows "who replies?" with the speaker's name and `p` with its band

#### Scenario: Scripted 1:1 rows shown
- **WHEN** a scripted 1:1 reply with a non-neutral face is opened in Insight after its face check landed
- **THEN** the System 1 section shows the "emotion" row before the reply and the "face and words agree?" row after it

### Requirement: Emotion rows
Every planned reply SHALL carry one emotion row per candidate asked, with `about` set to the candidate's ID. The row SHALL hold the face sent or the fallback's outcome as its answer, Jev's `p` for that face and its confidence, the floor comparison, and an action naming what code did ("shown", "kept", "faded to neutral", or "recorded (MANUAL)"). A candidate who did not speak SHALL have `result: "not_used"`.

#### Scenario: Confident row
- **WHEN** a planned 1:1 reply shows `thinking` from Jev with confidence 0.62
- **THEN** its emotion row has answer `thinking`, comparison `confidence` 0.62 ≥ 0.6, result `used` and action "shown"

#### Scenario: MANUAL row
- **WHEN** a planned reply runs under MANUAL emotion mode and Jev picks `happy` confidently
- **THEN** its emotion row's action is "recorded (MANUAL)"

### Requirement: Face-check rows
A reply checked by the face check SHALL gain one row with purpose `face_check`, label "face and words agree?" and result `shown_only`, appended after the turn through the runtime's append operation. Its call SHALL appear in the trace's `calls` with its latency.

#### Scenario: Row after the reply
- **WHEN** an `agent` reply's face check answers 380 ms after `turn.end`
- **THEN** a second `insight` carries the full trace with the face-check row and a `face_check` call entry, and the earlier rows are unchanged

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

### Requirement: Debate member rows
A debate argument whose member was chosen by a debate plan with a member question SHALL carry that question's row, with purpose `debate_plan`, the pick's ID as its answer, its `p` and confidence, the floor comparison, and an action: "speaks", "next in order (unsure)", "next in order (late)" or "next in order (failed)". The speaker's `emotion_line` row SHALL be `used` and the other candidates' `not_used`. An opening, a slot with one eligible member and an Ask answer SHALL have no member row.

#### Scenario: A confident pick
- **WHEN** Jev picks Rin confidently for a rebuttal slot
- **THEN** Rin's argument has a `member_rebuttal` row with purpose `debate_plan`, answer Rin's ID, `result: "used"` and action "speaks", and Amara's `emotion_line` row is `not_used`

### Requirement: Late debate-plan answers
A debate plan's answer that lands after the member deadline or after its turn started SHALL be written to the argument it started, through the runtime's append, replacing the fallback rows by key. The rows SHALL keep `result: "fallback"`, add Jev's late answer and `p`, and say "next in order (Jev answered late)" or "kept the face (Jev answered late)", so the trace never claims a face or member the turn didn't use.

#### Scenario: A late answer during the argument
- **WHEN** the debate plan's answer lands while the announced member's argument is streaming
- **THEN** the argument's final trace has the member and emotion rows with `result: "fallback"`, Jev's late answers and `p`, and one `debate_plan` call entry

### Requirement: A re-asked face keeps the member row
When a stored debate plan's fingerprint no longer matches at the turn's start, the argument SHALL keep the stored plan's member row (it decided who was announced), carry the new `emotion_line` rows with purpose `turn_plan`, and drop the stored plan's emotion rows.

#### Scenario: Faces asked again after an Ask
- **WHEN** an Ask changes the fingerprint before Rin's announced rebuttal
- **THEN** Rin's trace has the `member_rebuttal` row with purpose `debate_plan` and an `emotion_line` row with purpose `turn_plan`

### Requirement: The verdict and host lines have no System 1 rows
The rubric request and host lines SHALL write no System 1 rows. Their spend SHALL show in Settings → Cost.

#### Scenario: Verdict rows
- **WHEN** an `agent` debate's verdict is delivered
- **THEN** no message's trace has a `rubric` row

### Requirement: Gate rows
A reply whose plan asked "needs documents?" SHALL carry one row per candidate asked, `used` for the speaker and `not_used` for the others, comparing p against `t_gate`. When "standalone?" and "English?" were asked, the reply that relied on them SHALL carry one row each, comparing p against its threshold, `used` when a rewrite was considered and `not_used` otherwise.

#### Scenario: Rewritten follow-up
- **WHEN** a deep 1:1 reply was rewritten because its message wasn't standalone
- **THEN** its trace has a `docs` row with `result: "used"`, and a `standalone` row whose answer is "no" with `result: "used"`

### Requirement: Passage rows
A deep reply SHALL carry one `deep_check` row per checked candidate, about that passage's chunk id, with the level Jev chose, comparing p(answers) + p(partly) against `t_keep`: `used` when kept, `below_threshold` when dropped, `fallback` when its answer was missing. A set check SHALL add one row. The rows SHALL be grouped as "passages" with the slowest check's latency.

#### Scenario: Two kept, six dropped
- **WHEN** a deep reply kept two of eight checked passages
- **THEN** its trace has eight `deep_check` rows, two `used` and six `below_threshold`, each resolving to its passage's title in Insight

#### Scenario: Within the row limit
- **WHEN** a five-candidate group reply goes deep with a set check
- **THEN** its System 1 section holds at most 64 rows and no row is dropped

### Requirement: Earlier-gate and recall rows
A reply whose plan asked "needs something from earlier?" SHALL carry one `earlier` row per candidate asked, `used` for the speaker and `not_used` for the others, comparing p against its `t_gate`. A reply that ran recall SHALL carry one `recall` row per checked candidate, about that line's message id or that memory's id and never its text, `used`, `below_threshold` or `fallback`.

#### Scenario: Recall rows
- **WHEN** a reply checked 6 recall candidates and kept 2
- **THEN** its trace has 6 `recall` rows, 2 `used`, each `about` a `msg_` or `mem_` id

#### Scenario: Forgotten memory row
- **WHEN** a memory named by a `recall` row is forgotten
- **THEN** that row is gone from the stored trace and from any later append

### Requirement: Pause runs are not in System 1
The Jev and DeepSeek calls of a memory pause run SHALL NOT add rows to any message's System 1 section. They SHALL appear only in the ledger and the AI-call log.

#### Scenario: After a run
- **WHEN** a pause run made importance and guard requests for a session
- **THEN** no message trace of that session gains a row from them

### Requirement: Safety rows
A plan that asks "unsafe request?" or "at risk?" SHALL write one row for each, shared by every reply the plan starts, with p, the threshold and an action (steer cue, care cue, care (stay), no cue, or flagged). A reply using a stored answer SHALL show it with result `used` and no call. The output check SHALL write one `guardrail` row on the reply's trace, with action pass, flag or block.

#### Scenario: A shared input row
- **WHEN** an `agent` group Everyone plan asks `unsafe_request`, and one reply is given
- **THEN** that reply's System 1 holds one `unsafe_request` row with the answer's p and the threshold 0.7

#### Scenario: A stored answer
- **WHEN** a steered message's reply is regenerated
- **THEN** the new reply's `unsafe_request` row has result `used` and its action says the answer was stored, and the regenerate's `turn_plan` request holds no `unsafe_request`

#### Scenario: The output row after Stop
- **WHEN** an interrupted reply's after-the-fact check passes
- **THEN** a later `insight` appends its `output_rules` row to that reply's System 1

### Requirement: Checks outside a turn are not in System 1
The motion check, the image and song prompt checks and the memory instruction check SHALL write no System 1 row. Their spend SHALL appear under the `decision` category.

#### Scenario: A motion check
- **WHEN** a debate is created and its motion is checked
- **THEN** no message's System 1 holds a `motion_rules` row, and one `guardrail` ledger row exists with no message ID
