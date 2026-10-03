# Spec Delta

## MODIFIED Requirements

### Requirement: Reset demo data restores seed records only
Reset SHALL be available as `admin.resetDemo()` on both clients and SHALL do the following:
- restore every seed world, character, session, memory, knowledge source and seed ledger row to its shipped state, upserting seed records in place;
- keep user-created worlds, characters, sessions (including forks of seed sessions), memories (including memories a seed character earned in user sessions) and ledger rows;
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

## ADDED Requirements

### Requirement: Seed import is validated
The backend SHALL validate every seed file against the contract schema before writing anything. If any file is invalid, the import SHALL write nothing and SHALL name the file. Imported seed records SHALL be marked as seed records. Seed knowledge passages and seed memories SHALL be searchable by keyword as soon as the import finishes. `seed/_mock/**` SHALL NOT be imported in normal runs.

#### Scenario: Invalid seed file
- **WHEN** a seed character file is missing `profile` and the backend starts on an empty database
- **THEN** startup fails with an error naming that file, and the database holds no seed rows

#### Scenario: Keyword search after import
- **WHEN** the seed has been imported
- **THEN** a full-text search within Amara's knowledge for a word in her "ED triage guidelines" passages returns those passages

#### Scenario: No mock overlays in a normal run
- **WHEN** the backend starts without `HORIZON_TEST=1`
- **THEN** no `chr_mock*`, `ses_mock*` or `job_mock*` record exists

### Requirement: Test mode carries the mock overlays
When `HORIZON_TEST=1`, the backend SHALL also import the default-scenario records from `seed/_mock/**` (characters, sessions, songs, jobs and ledger rows) and SHALL treat them as seed records. This lets the portable suite see the same dataset on both clients.

#### Scenario: Archived mock character in test mode
- **WHEN** the backend runs with `HORIZON_TEST=1` and the Sunny Hollow roster is listed with `includeArchived=true`
- **THEN** an archived character is present, as on the MockClient

### Requirement: Shipped seed world names are reserved
A user world SHALL NOT take the shipped name of a seed world (case-insensitive, ignoring surrounding spaces), even while that seed world is renamed or deleted. Creating or renaming a world to such a name SHALL reject with `conflict`, so a reset can always restore the seed names.

#### Scenario: Taking a seed name after renaming the seed world
- **WHEN** the user renames "Meridian Council" to "Council B", then creates a world named "meridian council"
- **THEN** the create rejects with `conflict`, and `details.field` is `"name"`
