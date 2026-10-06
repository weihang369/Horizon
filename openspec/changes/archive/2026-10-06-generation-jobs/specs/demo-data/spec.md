## MODIFIED Requirements

### Requirement: Reset demo data restores seed records only
Reset SHALL be available as `admin.resetDemo()` on both clients and SHALL do the following:
- restore every seed world, character, session, memory, knowledge source and seed ledger row to its shipped state, upserting seed records in place;
- keep user-created worlds, characters, sessions (including forks of seed sessions), memories (including memories a seed character earned in user sessions) and ledger rows;
- on the backend, cancel any non-terminal job on a seed character, and keep the user-generated asset versions of seed characters as inactive versions (they were paid for);
- leave settings and the API key unchanged;
- emit `mock.reset` afterwards.

#### Scenario: Fork survives reset
- **WHEN** the user forks a seed session, edits a seed character, then resets demo data
- **THEN** the fork still exists and opens, the seed character is back to its shipped profile, and `mock.reset` is emitted

#### Scenario: User world survives reset
- **WHEN** the user creates a world with a character, then resets demo data
- **THEN** that world and character are unchanged

#### Scenario: Renamed and deleted seed worlds come back
- **WHEN** the user renames one seed world, deletes the other, then resets demo data
- **THEN** both seed worlds are listed with their shipped names, characters and sessions

#### Scenario: Regenerated seed emotion after reset
- **WHEN** on the backend the user regenerates and accepts a new happy emotion for Hana, then resets demo data
- **THEN** Hana shows her shipped happy portrait, and `characters.assets` still lists the generated version as inactive

## ADDED Requirements

### Requirement: Test-mode overlay jobs resume
In test mode, a seed overlay job that is shipped as `running` (Kenji's emotion set) SHALL be recovered like any job after a restart: its tasks that were never sent run, and its finished tasks keep their results.

#### Scenario: Kenji's job finishes
- **WHEN** the backend starts in test mode and the clock is advanced by 60 seconds
- **THEN** `job_mockKenjiEmotions` is terminal, and its three shipped emotions are unchanged
