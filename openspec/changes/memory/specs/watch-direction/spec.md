# Spec Delta

## ADDED Requirements

### Requirement: A plan made ahead starts its speaker's recall
When a watch plan made during the wait picks a speaker whose "needs something from earlier?" answer is yes, the speaker's recall SHALL start as soon as the plan lands and be stored with it, searching the last line and the two lines before it. A change that makes the plan stale SHALL cancel both.

#### Scenario: Stale plan
- **WHEN** a director's note arrives while a plan made ahead is running its speaker's recall checks
- **THEN** both are discarded, the checks are recorded `cancelled`, and a new plan is made
