## ADDED Requirements

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
