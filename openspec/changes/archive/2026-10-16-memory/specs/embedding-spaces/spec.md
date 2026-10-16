# Spec Delta

## ADDED Requirements

### Requirement: Dropped lines have vectors in the space
Indexed dropped lines SHALL be embedded as documents with no header, in the active space, never through the response store. A build of a new space SHALL fill them too: by copying the vectors when the model and dimensions are unchanged, otherwise by embedding them again, and its estimate SHALL count them.

#### Scenario: Build with lines
- **WHEN** `horizon space build` targets a space with a different model while 300 lines are indexed
- **THEN** its estimate counts those 300 lines, and after the switch recall's dense search finds them

#### Scenario: Not stored
- **WHEN** lines are embedded at a window drop
- **THEN** the response store gains no entry for them

### Requirement: Memory work embeds each new text once
A pause run SHALL embed each added line at most once per space: the vector used for its duplicate check SHALL be the one stored with it.

#### Scenario: One add
- **WHEN** a run adds one new memory with a key set and one non-retired space
- **THEN** exactly one embedding request carries that line's text
