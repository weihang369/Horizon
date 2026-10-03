# Spec Delta

## ADDED Requirements

### Requirement: Status reflects stored vectors
A source SHALL report `indexed` only when its passages are embedded in the active embedding space. A source that has readable passages but no vectors SHALL report `keyword_only`. On the backend, imported seed sources have no vectors until they are explicitly indexed, so they SHALL read `keyword_only`, with their passages viewable.

#### Scenario: Seed source on a fresh backend
- **WHEN** Amara's "ED triage guidelines" source is read from a freshly seeded backend
- **THEN** its status is `keyword_only`, and `knowledgeSource(id)` returns its passages in order with their locators

#### Scenario: Seed failure keeps its reason
- **WHEN** Mei's password-protected appendix is read from the backend
- **THEN** its status is `failed`, with the shipped `error` text
