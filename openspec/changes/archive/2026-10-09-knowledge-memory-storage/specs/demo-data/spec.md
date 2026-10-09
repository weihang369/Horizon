## MODIFIED Requirements

### Requirement: Reset demo data restores seed records only
Reset SHALL be available as `admin.resetDemo()` on both clients and SHALL do the following:
- restore every seed world, character, session, memory, knowledge source and seed ledger row to its shipped state, upserting seed records in place;
- keep user-created worlds, characters, sessions (including forks of seed sessions), memories (including memories a seed character earned in user sessions), knowledge sources and ledger rows;
- on the backend, cancel any non-terminal job on a seed character, and keep the user-generated asset versions of seed characters as inactive versions (they were paid for);
- on the backend, stop any indexing of seed sources and return them to `keyword_only`, without vectors, until they are indexed again;
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

#### Scenario: Indexed seed source after reset
- **WHEN** on the backend the user indexes one of Amara's seed sources, adds a source of their own to Amara, then resets demo data
- **THEN** the seed source is `keyword_only` with its shipped passages, and the user's source is unchanged

#### Scenario: Forgotten seed memory comes back
- **WHEN** the user forgets one of Hana's seed memories, then resets demo data
- **THEN** Hana's memory list shows that seed memory again
