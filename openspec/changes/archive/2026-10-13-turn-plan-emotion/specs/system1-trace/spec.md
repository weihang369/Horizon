## MODIFIED Requirements

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

## ADDED Requirements

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
