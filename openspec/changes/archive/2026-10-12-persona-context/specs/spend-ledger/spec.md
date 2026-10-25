# Spec Delta

## ADDED Requirements

### Requirement: Reply usage keeps a reported zero
A reply's usage, read from its ledger rows, SHALL include `tokensCached` whenever any of those rows reports a cached-token count, including 0. It SHALL omit `tokensCached` only when no row reports one. The message's `usage` and its trace's `model` SHALL carry the same value.

#### Scenario: Nothing cached
- **WHEN** a reply's only ledger row has `tokens_cached: 0`
- **THEN** the message's `usage.tokensCached` and its trace's `model.tokensCached` are both 0

#### Scenario: Not reported
- **WHEN** a reply's only ledger row has no cached-token count
- **THEN** neither the usage nor the trace has `tokensCached`
