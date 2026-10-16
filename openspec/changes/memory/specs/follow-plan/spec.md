# Spec Delta

## ADDED Requirements

### Requirement: The follow plan asks the earlier gate
The follow plan SHALL ask "needs something from earlier?" about each follow candidate with something to search, in the same request. A second replier whose earlier gate says yes SHALL run its own recall, starting when the follow plan lands, and a new user message SHALL cancel it with the plan.

#### Scenario: Second replier recalls
- **WHEN** the follow plan picks Mei and her `earlier` answer is p 0.6 with `t_gate` 0.4
- **THEN** Mei's reply carries her own recalled lines, and its recall checks started before her `turn.next`
