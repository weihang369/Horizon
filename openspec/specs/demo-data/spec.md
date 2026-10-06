# demo-data Specification

## Purpose

Defines the shipped seed dataset (its models, prices, sources and identifiers) and what "Reset demo data" restores, so the demo is reproducible without destroying user work.

## Requirements

### Requirement: Seed models and prices match the decision log
The seed SHALL record the following:
- **Image model:** `bytedance-seed/seedream-5-0-flash` at $0.018 per image, for every image generation price (D-61).
- **Decision model:** `typesafe/jev-1.13` at $0.042 per million input tokens, $0 output.
- **Embedding model:** a model with its price per million tokens.

#### Scenario: Pricing file
- **WHEN** `seed/pricing.json` is read
- **THEN** `decision.inputPerM` is `0.042`, `decision.outputPerM` is `0`, each image price is `0.018`, and an `embedding` entry exists

#### Scenario: Settings models
- **WHEN** `seed/settings.json` is read
- **THEN** `models.image` is `bytedance-seed/seedream-5-0-flash` and `models.embedding` is set

### Requirement: Seed knowledge uses supported types only
Seed knowledge sources SHALL be `file` or `text` only:
- Amara's "ED triage guidelines" is a `file` source;
- the seed SHALL contain no CSV source.

#### Scenario: No url or csv in the seed
- **WHEN** all seed knowledge sources are listed
- **THEN** none has `type: "url"`, and none has a title ending in `.csv`

### Requirement: Seed IDs are globally unique
Every ID in the seed SHALL be unique across the whole dataset, including portrait candidate IDs.

#### Scenario: Candidate IDs
- **WHEN** every `appearance.candidates[].id` in the seed is collected
- **THEN** no ID appears twice, and each one matches the contract ID format

### Requirement: Seed check guards the generated files
`seed:check` SHALL fail whenever the committed `seed/` differs from what the seed build generates.

#### Scenario: Stale seed
- **WHEN** a seed-build source changes and `seed:build` is not run
- **THEN** `seed:check` exits non-zero and lists the differing files

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

### Requirement: Test-mode overlay jobs resume
In test mode, a seed overlay job that is shipped as `running` (Kenji's emotion set) SHALL be recovered like any job after a restart: its tasks that were never sent run, and its finished tasks keep their results.

#### Scenario: Kenji's job finishes
- **WHEN** the backend starts in test mode and the clock is advanced by 60 seconds
- **THEN** `job_mockKenjiEmotions` is terminal, and its three shipped emotions are unchanged
