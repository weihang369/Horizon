# Spec Delta

## ADDED Requirements

### Requirement: The agent reply engine reads its passages from the plan
Under `agent`, a planned reply's passages SHALL come only from its frozen plan; the runtime SHALL NOT run the knowledge or memory retrievers for it. A planned reply that did not go deep SHALL reach the engine with no passages and no memories.

#### Scenario: Quick agent reply
- **WHEN** an `agent` reply's plan ends quick for a character with documents
- **THEN** its turn context holds no passages, and no keyword or vector search runs for it

#### Scenario: Deep agent reply
- **WHEN** an `agent` reply's plan kept two passages
- **THEN** its turn context holds exactly those two, in their numbered order

### Requirement: The planner runs a speaker's deep work
The planner port SHALL offer to run one speaker's deep work from a frozen request (the session, the speaker, the texts to search, the gate's answer, any stored rewrite) and the speaker's read-only scoped index, and return a frozen result. A profile whose planner doesn't decide retrieval SHALL return nothing. A bug inside it SHALL give a quick reply, never a failed one.

#### Scenario: Naive and scripted
- **WHEN** a `naive` or `scripted` turn is prepared
- **THEN** no deep work is started, and retrieval runs as before

#### Scenario: Deep work fails inside
- **WHEN** the deep work raises an unexpected error
- **THEN** the reply is written as a quick one, and its trace marks the fallback
