# Spec Delta

## ADDED Requirements

### Requirement: The planner plans debate turns
Under `agent`, the planner SHALL plan every debate turn:
- rebuttal, closing and panel slots through the debate plan;
- each opening with its own `turn_plan` request (`emotion_debate_opening` for that speaker): the first opening during the start delay, every later one when its prefetch starts;
- each Ask answer at its turn start (`emotion_reply`).

No debate turn SHALL be planned under `naive` or `scripted`.

#### Scenario: The first opening's face is ready at its start
- **WHEN** an `agent` debate starts and its first opening speaker is Amara
- **THEN** a `turn_plan` request asking `emotion_debate_opening` about Amara is made during the 1.6 s start delay, and Amara's opening uses its answer

#### Scenario: A prefetched opening keeps its own plan
- **WHEN** Victor's opening is prefetched while Amara's streams
- **THEN** Victor's prefetch carries its own `emotion_debate_opening` answer, asked when the prefetch started

#### Scenario: Ask answers are planned
- **WHEN** the user asks Rin a question in an `agent` debate
- **THEN** Rin's answer is planned with `emotion_reply` at its turn start, under the `turn_plan` deadline

### Requirement: Debate plans per profile
`naive` and `scripted` SHALL fill debate slots in fixed order and send no plan, so their speakers are today's while everyone is awake. Their faces SHALL come from their own engines.

#### Scenario: Scripted debate makes no Jev call
- **WHEN** a `scripted` debate runs to its verdict
- **THEN** no `turn_plan`, `debate_plan` or `rubric` ledger row exists
