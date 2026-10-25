# Spec Delta

## ADDED Requirements

### Requirement: Create and rename a world
`worlds.create` SHALL return a new world with:
- an ID matching `^wld_[0-9A-Za-z]{1,40}$`;
- `isSeed: false` and `characterCount: 0`;
- `createdAt`, `updatedAt` and `lastActiveAt` set to now.

Names SHALL be trimmed and cut to 40 characters, and an empty name becomes "New World". `worlds.update` SHALL change the given fields, apply the same name rules and set `updatedAt`. `worlds.list` SHALL be ordered by `lastActiveAt`, newest first.

#### Scenario: Create
- **WHEN** a world named "  My Street  " is created with a preset cover
- **THEN** the returned world is named "My Street", has `isSeed: false` and `characterCount: 0`, and is listed first

#### Scenario: Rename an unknown world
- **WHEN** `worlds.update` targets a world ID that doesn't exist
- **THEN** the call rejects with `not_found`

### Requirement: World names are unique
No two worlds SHALL have the same name, compared case-insensitively after trimming. A create or rename that would duplicate a name SHALL reject with `conflict`, with `details.field: "name"`, and SHALL change nothing. Renaming a world to its own current name SHALL succeed.

#### Scenario: Duplicate on create
- **WHEN** a world named "My Street" exists and another world named "my street" is created
- **THEN** the call rejects with `conflict`, and only one such world exists

#### Scenario: Same name on rename
- **WHEN** "My Street" is renamed to "My Street"
- **THEN** the call succeeds

### Requirement: Delete a world
`worlds.delete` SHALL remove the following:
- the world;
- its characters, sessions, memories and knowledge;
- its generated files and uploaded documents.

Ledger rows SHALL be kept, with their references to the deleted records cleared. Afterwards `worlds.get` SHALL reject with `not_found`, and `entity.changed { kind: "world", id }` SHALL be emitted.

#### Scenario: Delete a world with content
- **WHEN** a world with characters, sessions and knowledge is deleted
- **THEN** `worlds.get(id)`, `characters.get` of its characters and `sessions.get` of its sessions all reject with `not_found`, and the usage list still contains its ledger rows

#### Scenario: Files removed
- **WHEN** a world is deleted on the backend
- **THEN** its `assets/gen/{worldId}` and `knowledge/{worldId}` folders no longer exist
