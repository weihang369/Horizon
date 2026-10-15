# Spec Delta

## ADDED Requirements

### Requirement: Gate rows
A reply whose plan asked "needs documents?" SHALL carry one row per candidate asked, `used` for the speaker and `not_used` for the others, comparing p against `t_gate`. When "standalone?" and "English?" were asked, the reply that relied on them SHALL carry one row each, comparing p against its threshold, `used` when a rewrite was considered and `not_used` otherwise.

#### Scenario: Rewritten follow-up
- **WHEN** a deep 1:1 reply was rewritten because its message wasn't standalone
- **THEN** its trace has a `docs` row with `result: "used"`, and a `standalone` row whose answer is "no" with `result: "used"`

### Requirement: Passage rows
A deep reply SHALL carry one `deep_check` row per checked candidate, about that passage's chunk id, with the level Jev chose, comparing p(answers) + p(partly) against `t_keep`: `used` when kept, `below_threshold` when dropped, `fallback` when its answer was missing. A set check SHALL add one row. The rows SHALL be grouped as "passages" with the slowest check's latency.

#### Scenario: Two kept, six dropped
- **WHEN** a deep reply kept two of eight checked passages
- **THEN** its trace has eight `deep_check` rows, two `used` and six `below_threshold`, each resolving to its passage's title in Insight

#### Scenario: Within the row limit
- **WHEN** a five-candidate group reply goes deep with a set check
- **THEN** its System 1 section holds at most 64 rows and no row is dropped
