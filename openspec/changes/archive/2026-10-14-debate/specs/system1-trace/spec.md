# Spec Delta

## ADDED Requirements

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
