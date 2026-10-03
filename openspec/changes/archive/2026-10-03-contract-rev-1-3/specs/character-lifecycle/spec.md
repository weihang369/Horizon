# Spec Delta: character-lifecycle

## Purpose

Defines what deleting a character does, so old transcripts keep rendering while the character disappears from everything the user can act on (D-70).

## ADDED Requirements

### Requirement: Delete leaves a tombstone
`characters.delete` SHALL turn the character into a tombstone. It SHALL:
- set `deletedAt`;
- keep `id`, `worldId`, the name, the palette and the active neutral portrait;
- remove the character's memory, knowledge, songs, other assets and non-terminal jobs.

#### Scenario: Tombstone after delete
- **WHEN** an approved character is deleted
- **THEN** `characters.get(id)` resolves with `deletedAt` set, `profile.name` unchanged and `emotions.neutral` still present, while `characters.memory(id)` and `characters.knowledge(id)` resolve empty

### Requirement: Tombstones are hidden from lists and actions
`characters.list` SHALL exclude tombstones. Every command on a tombstoned character SHALL reject with `not_found`, including updating it, starting a job and adding it to a session.

#### Scenario: Roster after delete
- **WHEN** a character is deleted and the world's roster is listed
- **THEN** the character is absent, and `World.characterCount` no longer counts it

#### Scenario: Acting on a tombstone
- **WHEN** `characters.update` or `jobs.start` targets a tombstoned character
- **THEN** the call rejects with `not_found`

### Requirement: Transcripts survive deletion
Sessions that include a deleted character SHALL still open, replay and export, showing the tombstone's name and neutral portrait.

#### Scenario: Old session after delete
- **WHEN** a character who spoke in a session is deleted and the session is opened
- **THEN** their messages render with their name and neutral portrait, and the session is not removed

### Requirement: Delete is refused while the character is streaming
Deleting a character who is in the currently live session SHALL reject with `conflict`.

#### Scenario: Delete during a live reply
- **WHEN** `characters.delete` is called while a live session with that character is active
- **THEN** the call rejects with `conflict`, and the character is unchanged
