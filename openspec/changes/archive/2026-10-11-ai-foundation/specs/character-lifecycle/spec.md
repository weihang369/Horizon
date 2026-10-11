## ADDED Requirements

### Requirement: Deleting a character purges its captured AI calls
After a character's deletion commits, the purge hooks SHALL delete every captured AI call of that character. The tombstone, the transcripts and the ledger rows SHALL stay.

#### Scenario: Purged after delete
- **WHEN** a character with captured AI calls is deleted and the purge worker runs
- **THEN** no `ai_calls` row names that character, and its ledger rows are unchanged
