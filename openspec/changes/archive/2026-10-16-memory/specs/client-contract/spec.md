# Spec Delta

## ADDED Requirements

### Requirement: Both clients hide a dangling memory source
The MockClient SHALL apply the same read-time rule as the backend: a memory whose source session no longer exists SHALL be listed without `sourceSessionId`. The portable contract suite SHALL check it on both clients.

#### Scenario: Portable check
- **WHEN** the portable suite deletes a session that is a memory's source and lists the character's memories
- **THEN** on both clients that memory has no `sourceSessionId`
