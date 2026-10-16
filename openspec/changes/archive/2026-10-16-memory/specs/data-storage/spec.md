# Spec Delta

## ADDED Requirements

### Requirement: The memory migration
Migration 0005 SHALL add the sessions' memory checkpoint (set to each existing session's highest message number), the re-read list and the try count, and a table of indexed dropped lines keyed by an integer row id with a cascading foreign key to messages and a keyword index kept by triggers. Downgrading SHALL remove them and leave every other table unchanged.

#### Scenario: Upgrade and downgrade
- **WHEN** migrations run to 0005 and back to 0004
- **THEN** the new columns and tables exist after the upgrade, are gone after the downgrade, and every other table is unchanged

#### Scenario: Existing session
- **WHEN** a database holding a session with 57 messages upgrades to 0005
- **THEN** that session's memory checkpoint is 57

### Requirement: Message vector tables exist at startup
At startup the backend SHALL also ensure, for the active space and any building space, a message vector table partitioned by session, with a delete trigger on the indexed lines. A restart SHALL NOT recreate or empty it, and migrations SHALL never create it.

#### Scenario: First start after the upgrade
- **WHEN** the backend starts after upgrading to 0005
- **THEN** the active space's message vector table exists and is empty

### Requirement: Stored rewrites hold no forgotten memory
The per-message AI table's stored rewrites SHALL hold no text of a forgotten memory: removing a memory through the Forget path SHALL delete that character's stored rewrites in that world.

#### Scenario: Forget then look
- **WHEN** a character's memory is forgotten
- **THEN** no stored rewrite of that character remains in that world's sessions
