# Spec Delta

## ADDED Requirements

### Requirement: A plan made ahead starts its speaker's deep work
When a watch plan made during the wait picks a speaker whose "needs documents?" answer is yes, the speaker's deep work SHALL start as soon as the plan lands and be stored with it. A change that makes the plan stale SHALL cancel both. A watch turn SHALL search the last message, and the two earlier lines with it, and SHALL never rewrite or abstain.

#### Scenario: Deep work ready by the turn
- **WHEN** a plan made ahead picks Mei with her gate at p 0.8, and the pause is longer than the deep work
- **THEN** Mei's reply request is sent without waiting for any `deep_check` request after her `turn.next`

#### Scenario: Stale plan
- **WHEN** a director's note arrives while the deep work of a plan made ahead is in flight
- **THEN** both are discarded, their requests are recorded `cancelled`, and a new plan is made
