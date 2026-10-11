## ADDED Requirements

### Requirement: Forget deletes captured AI calls
Forgetting a memory SHALL, inside Forget's own writer transaction, delete every captured AI call of that character and every captured AI call of that world that has no character. Captured rows still queued for writing that belong to that character, or to that world with no character, and were created before the Forget, SHALL never be written.

#### Scenario: Forget with capture on
- **WHEN** capture is on, a reply that recalled a memory is captured, and the memory is forgotten
- **THEN** after the Forget, no `ai_calls` row and no queued capture row contains the memory's text, and the existing byte-level Forget check passes with capture on

#### Scenario: Queued row dropped
- **WHEN** a row for the character is queued but not yet written when Forget commits
- **THEN** the writer drops it, and it never reaches the table
