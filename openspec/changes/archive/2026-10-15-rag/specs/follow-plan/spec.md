# Spec Delta

## ADDED Requirements

### Requirement: The follow plan asks the gates
The follow plan SHALL ask "needs documents?" for each candidate with a searchable source, in the same request as its other questions. It SHALL reuse the "standalone?" and "English?" answers of the cast plan for the same user message, and ask them only if that plan didn't. A second reply whose gate says yes SHALL go deep with its own query and rewrite, reusing the message's embedding.

#### Scenario: Second replier goes deep
- **WHEN** the follow plan picks Mei, her `docs` answer is p 0.7, and the cast plan already asked `standalone` and `english`
- **THEN** the follow plan's request holds `docs:{Mei's id}` and no `standalone` or `english` question, and Mei's reply carries its own kept passages

#### Scenario: No second reply
- **WHEN** the follow plan answers `none`
- **THEN** no deep work starts for any follow candidate

### Requirement: The second reply's deep work starts when the follow plan lands
When the follow plan picks a second replier whose gate says yes, that reply's deep work SHALL start as soon as the plan's answer is in, before the second reply's `turn.next`. A new user message SHALL cancel it with the follow plan.

#### Scenario: Superseded during the deep work
- **WHEN** the user sends a new message while the second reply's `deep_check` requests are in flight
- **THEN** no second reply is written, and those requests are recorded `cancelled`
