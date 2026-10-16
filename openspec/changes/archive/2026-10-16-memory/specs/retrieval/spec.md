# Spec Delta

## ADDED Requirements

### Requirement: The agent search runs over any corpus
The agent search pipeline SHALL run the same way over any corpus the runtime binds to the speaker's scope (documents, a session's indexed lines, a character's memories), taking its numbers from the caller. For documents its results SHALL be exactly what they were before.

#### Scenario: Documents unchanged
- **WHEN** the committed retrieval fixtures are searched after the change
- **THEN** every candidate list and score equals the committed one

#### Scenario: Recall's numbers
- **WHEN** recall searches a session's lines
- **THEN** each list takes at most 10 hits, as recall's settings say
