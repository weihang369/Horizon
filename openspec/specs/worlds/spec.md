# worlds Specification

## Purpose

Defines world-level behaviour exposed through the client contract, starting with uploading a custom world cover image.

## Requirements

### Requirement: Upload a world cover
`worlds.uploadCover(id, file)` SHALL accept a PNG, JPEG or WebP image of at most 5 MB, judged by the file's content (its magic bytes), not by its name or declared type. It SHALL return the world with `cover.kind: "upload"` and a `cover.url` that the UI can display. On the backend, the stored cover SHALL be a 1600×900 WebP with a new URL for every upload. It SHALL need no key.

#### Scenario: Valid upload
- **WHEN** a 1 MB PNG is uploaded as a world's cover
- **THEN** the returned world has `cover.kind: "upload"` and a non-empty `cover.url`, and `entity.changed { kind: "world", id }` is emitted

#### Scenario: Wrong type or too large
- **WHEN** a GIF, or a 6 MB JPEG, is uploaded
- **THEN** the call rejects with `validation`, and the world's cover is unchanged

#### Scenario: Declared type does not match the content
- **WHEN** a text file named `b.png` with type `image/png` is uploaded
- **THEN** the call rejects with `validation`

#### Scenario: Unknown world
- **WHEN** `uploadCover` targets a world ID that doesn't exist
- **THEN** the call rejects with `not_found`

#### Scenario: Stored cover on the backend
- **WHEN** a 3000×2000 JPEG is uploaded as a cover on the backend
- **THEN** the cover URL serves a 1600×900 WebP under `/assets/gen/{worldId}/`

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

### Requirement: The world editor uploads covers
The world editor SHALL send a chosen cover image through `worlds.uploadCover` after the world is created or saved, rather than storing the image inside the world record. It SHALL accept PNG, JPEG and WebP files up to 5 MB, preview the image before saving, and show the upload's `validation` error if it is rejected.

#### Scenario: New world with an uploaded cover
- **WHEN** the user creates a world and picks a PNG cover
- **THEN** the world is created, `worlds.uploadCover` is called once for it, and the world hub shows the uploaded cover

#### Scenario: Oversized file
- **WHEN** the user picks a 6 MB image in the editor
- **THEN** the editor shows an error and nothing is uploaded
