# Spec Delta

## ADDED Requirements

### Requirement: The memory list never points to a deleted session
`GET /characters/{id}/memory` SHALL omit `sourceSessionId` from a memory whose source session no longer exists, decided at read time, and SHALL keep it otherwise.

#### Scenario: Source session deleted
- **WHEN** a memory's source session is deleted and the character's memories are listed
- **THEN** that memory has no `sourceSessionId`, and its other fields are unchanged
