# Spec Delta: worlds

## Purpose

Defines world-level behaviour exposed through the client contract, starting with uploading a custom world cover image.

## ADDED Requirements

### Requirement: Upload a world cover
`worlds.uploadCover(id, file)` SHALL accept a PNG, JPEG or WebP image of at most 5 MB. It SHALL return the world with `cover.kind: "upload"` and a `cover.url` that the UI can display.

#### Scenario: Valid upload
- **WHEN** a 1 MB PNG is uploaded as a world's cover
- **THEN** the returned world has `cover.kind: "upload"` and a non-empty `cover.url`, and `entity.changed { kind: "world", id }` is emitted

#### Scenario: Wrong type or too large
- **WHEN** a GIF, or a 6 MB JPEG, is uploaded
- **THEN** the call rejects with `validation`, and the world's cover is unchanged

#### Scenario: Unknown world
- **WHEN** `uploadCover` targets a world ID that doesn't exist
- **THEN** the call rejects with `not_found`
