## MODIFIED Requirements

### Requirement: Reactions run after the turn
After a completed character reply in AUTO mode in group, debate or watch, the runtime SHALL start one reactions task
for that message. It SHALL never delay the next speaker. 1:1 sessions, interrupted, failed or blocked replies, replies
whose care cue is on, and MANUAL mode SHALL get no reactions.

#### Scenario: Next speaker not delayed
- **WHEN** an `agent` group reply ends and Jev's reaction answer is held for 1 s
- **THEN** the next turn's `turn.next` is emitted at the normal turn gap, without waiting for the answer

#### Scenario: No reactions in 1:1
- **WHEN** an `agent` 1:1 reply completes
- **THEN** no `reaction` decision request is made

#### Scenario: No reactions to a care reply
- **WHEN** an `agent` group reply to a care message completes
- **THEN** no `reaction` decision request is made, and no `reaction` event follows it
