# Spec Delta

## ADDED Requirements

### Requirement: The debate plan asks the earlier gate per member
The debate plan SHALL ask "needs something from earlier?" about each member with something to search, in the same request. The answer SHALL be used only if it is back by the turn's start; otherwise the turn SHALL run no recall. A member's recall SHALL search the motion and the last opposing argument, and start once the member is fixed.

#### Scenario: Late gate
- **WHEN** the member is fixed at the deadline and the `earlier` answers land after the turn starts
- **THEN** the turn runs no recall, and its `earlier` row records the fallback

#### Scenario: Recall in a rebuttal
- **WHEN** a rebuttal member's `earlier` answer is back with p 0.7 before the turn starts
- **THEN** the turn searches the motion and the last opposing argument over the debate's indexed lines and the member's overflow

### Requirement: A long debate cuts its arguments before its gates
When a debate plan's state is still over its 2,000-token cap after the existing cuts, it SHALL cut each member's latest argument to 30 words, then the last opposing argument to 120 tokens, and only then drop members' gates.

#### Scenario: Late in a three-a-side debate
- **WHEN** a three-a-side debate's state is over the cap after the recent-line cuts, and fits once the arguments are cut
- **THEN** every member's `docs` and `earlier` questions are still asked, and no gate is reported dropped

#### Scenario: Still over after the cuts
- **WHEN** the state is still over the cap after cutting the arguments
- **THEN** the members furthest down the last-spoke order lose their gates, as before

#### Scenario: Short debate unchanged
- **WHEN** a debate state is under the cap
- **THEN** its arguments are not cut and its bytes are unchanged
