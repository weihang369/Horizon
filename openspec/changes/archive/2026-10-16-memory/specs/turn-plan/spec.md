# Spec Delta

## ADDED Requirements

### Requirement: Jev call 1 and the cast plan ask the earlier gate
The 1:1 plan and the cast plan (group, Everyone, Next speaker, Step in, watch) SHALL ask "needs something from earlier?" about each candidate with something to search (see `session-recall`), in the same request as their other questions and with no new state field.

#### Scenario: Group with dropped lines
- **WHEN** a group session with indexed lines plans its first slot over Amara and Mei
- **THEN** the one request holds `earlier:{Amara's id}` and `earlier:{Mei's id}`

### Requirement: A turn goes deep on either gate
A planned reply SHALL take the deep branch when its speaker's documents gate or earlier gate is at or above its threshold, and SHALL run only the parts its gates asked for. Only the speaker's own earlier answer SHALL decide; the others SHALL be recorded as asked but not used.

#### Scenario: Recall only
- **WHEN** Amara's `docs` answer is p 0.1 and her `earlier` answer is p 0.8
- **THEN** her plan goes deep, runs recall, and makes no `deep_check` request about any passage

#### Scenario: Neither
- **WHEN** both of her gates are below their thresholds
- **THEN** the plan ends quick and no `deep_check` request is made
