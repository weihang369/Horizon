# Spec Delta

## ADDED Requirements

### Requirement: Who speaks next is judged on fit, not on turns since
Jev's who-speaks question for a watch turn (`who_scene`) and a group Next speaker (`who_next`) SHALL see no "last spoke" label on the candidates. Fairness SHALL stay with code: the nobody-left-out guard SHALL keep counting turns since each character last spoke from the log.

#### Scenario: The guard still forces the silent
- **WHEN** a character has been silent for two full rounds in an `agent` watch
- **THEN** the guard forces them next with `forcedBy: "round_order"`, though the scene question's state carries no `last_spoke`

#### Scenario: The question sees no turn counts
- **WHEN** an `agent` watch turn asks `who_scene`
- **THEN** its state's cast entries have names, roles, `about` and faces, and no `last_spoke`
