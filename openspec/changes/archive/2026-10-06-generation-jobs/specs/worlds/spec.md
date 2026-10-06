## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: The world editor uploads covers
The world editor SHALL send a chosen cover image through `worlds.uploadCover` after the world is created or saved, rather than storing the image inside the world record. It SHALL accept PNG, JPEG and WebP files up to 5 MB, preview the image before saving, and show the upload's `validation` error if it is rejected.

#### Scenario: New world with an uploaded cover
- **WHEN** the user creates a world and picks a PNG cover
- **THEN** the world is created, `worlds.uploadCover` is called once for it, and the world hub shows the uploaded cover

#### Scenario: Oversized file
- **WHEN** the user picks a 6 MB image in the editor
- **THEN** the editor shows an error and nothing is uploaded
