# Spec Delta

## ADDED Requirements

### Requirement: The memory questions
The bank SHALL hold `earlier` (noul, purpose `turn_plan`, threshold `t_gate` starting 0.4, declaring every plan state field), `recall` (noul, purpose `deep_check`, threshold `t_recall` starting 0.5), `importance` (score with 5 written levels, purpose `importance`) and `memory_guard` (noul, purpose `memory_guard`, threshold `t_keep` starting 0.7), each with written instructions, examples and a state template of `quoted_*` text fields.

#### Scenario: Loaded and locked
- **WHEN** the bank loads
- **THEN** the four entries validate, their versions are in the lock file, and each instruction ends with the quoted-content sentence

#### Scenario: Importance as a unit
- **WHEN** Jev answers an `importance` question with its fourth level
- **THEN** the importance read is 0.75

### Requirement: The importance request leaves room for more questions
The importance request SHALL accept further questions about the same lines under their own ids without changing the `importance` entry or its version.

#### Scenario: An extra question
- **WHEN** a test adds a noul about each line to the importance request
- **THEN** the request carries both questions per line and `importance` keeps its version
