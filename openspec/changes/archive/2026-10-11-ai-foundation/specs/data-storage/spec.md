## ADDED Requirements

### Requirement: AI foundation migration
A numbered migration SHALL add:
- `usage_records.finish_reason` (text, nullable) and `usage_records.tokens_reasoning` (integer, nullable);
- the `ai_calls` table, with indexes on `created_at`, `character_id`, `session_id` and `message_id`. Its world and session references SHALL cascade on delete, and its character and message references SHALL have no foreign key.

Existing rows SHALL read `NULL` in the new columns. Like every Horizon migration, it SHALL be forward-only: rollback is a copy of `data/`.

#### Scenario: Upgrade an M6 database
- **WHEN** a database at the previous migration is upgraded
- **THEN** existing ledger rows are unchanged with `finish_reason` and `tokens_reasoning` null, and `ai_calls` exists and is empty

#### Scenario: Session delete cascades
- **WHEN** a session with captured AI calls is deleted
- **THEN** its `ai_calls` rows are deleted in the same transaction
