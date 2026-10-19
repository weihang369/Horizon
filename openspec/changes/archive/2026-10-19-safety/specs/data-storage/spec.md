## ADDED Requirements

### Requirement: The safety migration
Migration 0006 SHALL add a nullable JSON column `safety` to `message_ai_meta`, holding the stored safety answers for a user line. Rows without it SHALL read as not flagged. Downgrading SHALL drop the column and keep the rest of the table.

#### Scenario: Upgrade and downgrade
- **WHEN** migrations run to 0006 and back to 0005
- **THEN** `message_ai_meta.safety` exists after the upgrade, is gone after the downgrade, and the stored rewrites are unchanged

#### Scenario: Old rows
- **WHEN** a database from before 0006 is upgraded
- **THEN** every existing row has `safety` NULL, and no message reads as steered or at risk
