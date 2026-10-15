# Spec Delta

## ADDED Requirements

### Requirement: The per-message AI table
Migration 0004 SHALL add `message_ai_meta`, keyed by message id with a foreign key to messages that cascades on delete, holding the per-speaker query rewrites as JSON. Downgrading SHALL drop it. It SHALL hold no vectors.

#### Scenario: Upgrade and downgrade
- **WHEN** migrations run to 0004 and back to 0003
- **THEN** `message_ai_meta` exists after the upgrade, is gone after the downgrade, and every other table is unchanged

#### Scenario: Cascade
- **WHEN** a session holding messages with stored rewrites is deleted
- **THEN** no `message_ai_meta` row for its messages remains
