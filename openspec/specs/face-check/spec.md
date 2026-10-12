# face-check Specification

## Purpose
The live face-and-words check: after a reply ends, Jev reads only its words and says which emotion they show, and
Insight records whether that agrees with the face shown. It is display only and never changes the face.

## Requirements

### Requirement: When the face check runs
Under `agent`, after `turn.end` of a completed reply that was in AUTO mode at its `turn.start` and whose face is not
`neutral`, the runtime SHALL start one face-check task for the session. It SHALL be skipped for MANUAL, neutral,
blocked, interrupted and failed replies, and for a verbatim greeting. `naive` SHALL have no check.

#### Scenario: Non-neutral AUTO reply
- **WHEN** an `agent` 1:1 reply completes with face `sad` in AUTO mode
- **THEN** one `face_check` decision request is sent after its `turn.end`

#### Scenario: Neutral reply
- **WHEN** an `agent` reply completes with face `neutral`
- **THEN** no `face_check` request is sent

#### Scenario: Switched to MANUAL mid-reply
- **WHEN** a reply started in MANUAL mode and the user switched to AUTO before it ended
- **THEN** no `face_check` request is sent

### Requirement: What the face check asks
The face check SHALL send one choice question over the 7 emotions, with no `none`, whose state is only the reply's
text as quoted content, cut to its last 600 tokens. It SHALL time out after 1,500 ms.

#### Scenario: A long reply
- **WHEN** a 900-token reply is checked
- **THEN** the request's state holds only `quoted_reply`, holding the reply's last 600 tokens

### Requirement: The face-check row
When the answer arrives in time, the runtime SHALL append one System 1 row to the reply's trace with label "face and
words agree?" and result `shown_only`. The answer SHALL be `yes` when Jev's pick is the face shown, `clash` when one
is `happy` and the other `sad` or `angry`, and otherwise `no (words read: {pick})`. `p` SHALL be Jev's probability for
the face shown.

#### Scenario: Agreement
- **WHEN** the reply's face is `sad` and Jev picks `sad` with p 0.66
- **THEN** the trace gains the row answer `yes`, `p` 0.66, result `shown_only`, and the call's latency appears in `calls`

#### Scenario: Clash
- **WHEN** the reply's face is `happy` and Jev picks `angry`
- **THEN** the row's answer is `clash`

### Requirement: The face check never changes the face
The face check SHALL never emit an `emotion` or `reaction` event. A late, failed or refused check SHALL add no row and
SHALL never pause the session or emit an `error` event. Its spend SHALL count toward the daily cap as decision spend
and SHALL never drain energy.

#### Scenario: Failed check
- **WHEN** the `face_check` request fails
- **THEN** the reply's trace and face are unchanged, and no `error` or `session.paused` event is emitted

### Requirement: Cancelling the face check
`clear()` (Stop, leave, a cap pause, the session's end) SHALL cancel a pending face check, and no row SHALL be added
afterwards. A new user message and the next turn's start SHALL NOT cancel it. A row for a variant that is no longer
active SHALL be dropped.

#### Scenario: Next turn does not cancel
- **WHEN** a group reply's face check is pending and the next speaker's turn starts
- **THEN** the check's row is still appended to the first reply's trace when Jev answers

#### Scenario: Regenerated before the row
- **WHEN** a reply is regenerated before its face check answers
- **THEN** the check's row is dropped, and the new variant's trace has no row from it

### Requirement: Scripted and mock face checks
The scripted profile SHALL record one simulated `face_check` call for each reply the agent rule would check, and
append the fixture's row with answer `yes` after the shared timing table's `faceCheckMs`. The MockClient SHALL do the
same.

#### Scenario: Scripted check
- **WHEN** a scripted 1:1 reply completes with face `happy` in AUTO
- **THEN** a simulated `face_check` row is written, and a second `insight` adds the "face and words agree?" row with answer `yes`
