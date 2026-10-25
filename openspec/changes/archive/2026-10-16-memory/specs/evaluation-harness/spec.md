# Spec Delta

## ADDED Requirements

### Requirement: The memory decision slices
The decision suite SHALL include `importance` (100 lines, at least 30 to drop), `memory_guard` (about 120 rewrites, at least 60 lossy), `earlier` (about 120 plan states, at least 60 yes) and `recall` (about 120 pairs, at least 60 relevant), each split dev / test at creation, and SHALL choose `t_keep`, the earlier `t_gate` and `t_recall` on dev by their stated rules.

#### Scenario: Guard threshold
- **WHEN** the guard slice runs on dev
- **THEN** the report gives the lowest threshold letting at most 5 % of lossy rewrites through

### Requirement: The memory suite
A `memory` suite SHALL run, on synthetic items only: 24 rewrite stretches with planted lists, secrets and small-talk stretches; 60 in-session and 40 overflow recall probes reported beside keyword-only, dense-only and no-MMR arms; and 20 two-session pairs with the `agent` writer and recall, scoring probe use and over-mentioning. Every rate SHALL carry a Wilson interval.

#### Scenario: Secret stored
- **WHEN** a rewrite stretch's answer stores a planted card number
- **THEN** the report counts a stored secret against its target of 0 and lists the item

#### Scenario: Recall arms
- **WHEN** the recall probes run
- **THEN** hit@3 is reported for the hybrid and for each of the three arms

### Requirement: The memory judges are validated first
The "Memory rewrite" judge (covered, supported, lost a fact) and the "Over-mention" judge SHALL be validated on planted items before their scores count.

#### Scenario: Unvalidated judge
- **WHEN** the over-mention judge has not passed validation
- **THEN** the suite reports its scores as not counted
