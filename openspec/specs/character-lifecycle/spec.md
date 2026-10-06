# character-lifecycle Specification

## Purpose

Defines what deleting a character does, so old transcripts keep rendering while the character disappears from everything the user can act on (D-70).

## Requirements

### Requirement: Delete leaves a tombstone
`characters.delete` SHALL turn the character into a tombstone. It SHALL:
- set `deletedAt`;
- keep `id`, `worldId`, the name, the palette and the active neutral portrait;
- cancel its non-terminal job;
- remove the character's memory, knowledge, songs, other assets and their files, and its jobs;
- queue the deletion for the AI state hooks.

#### Scenario: Tombstone after delete
- **WHEN** an approved character is deleted
- **THEN** `characters.get(id)` resolves with `deletedAt` set, `profile.name` unchanged and `emotions.neutral` still present, while `characters.memory(id)` and `characters.knowledge(id)` resolve empty

#### Scenario: Delete during a generation job
- **WHEN** a draft with a running emotion job is deleted on the backend
- **THEN** the job is cancelled, no further provider call is made for it, and the character's generated files other than the neutral portrait no longer exist

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

### Requirement: Create a draft
`characters.createDraft(worldId, { seedPrompt, intent })` SHALL need a usable key and an existing world. It SHALL create a `draft` character with `creationStep: "seed"`, the seed prompt cut to 300 characters, `advisory` true for the `expert` intent, placeholder profile values that satisfy the contract until the draft fills them, every emotion empty and full energy. It SHALL start its `profile_draft` job, and return `{ character, job }`.

#### Scenario: Draft from a seed prompt
- **WHEN** a key is set and `createDraft("wld_seedMeridian", { seedPrompt: "Sarah, a doctor", intent: "expert" })` is called and the job finishes
- **THEN** the character is a `draft` with `advisory: true`, its profile name is "Sarah", its role is not empty, and its `creationStep` is `profile`

#### Scenario: Draft without a key
- **WHEN** no key is set and `createDraft` is called
- **THEN** it rejects with `missing_key`, and no character is created

### Requirement: Edit a character
`characters.update(id, patch)` SHALL deep-merge `profile` and `appearance` (objects are merged key by key, lists are replaced), and set any other given fields. It SHALL bump `version` when the character is approved, set `updatedAt`, and never lose a concurrent write to the same character by a running job. It SHALL need no key.

#### Scenario: Edit one profile field
- **WHEN** `update(id, { profile: { tagline: "New" } })` is called
- **THEN** only the tagline changes, and the other profile fields keep their values

#### Scenario: Edit while a job writes
- **WHEN** a profile edit commits while the character's portrait job is storing a candidate
- **THEN** both the edit and the candidate are present afterwards

### Requirement: Approve a character
`characters.approve(id)` SHALL reject with `validation` unless the profile has a name and a role, `age` is at least 18, and a base portrait is locked. On success the character SHALL become `approved` with `approvedAt` set and no `creationStep`, and SHALL stop counting toward the creation cap.

#### Scenario: Approve without a portrait
- **WHEN** a draft with a valid profile but no locked portrait is approved
- **THEN** the call rejects with `validation`, and the status stays `draft`

#### Scenario: Approve a complete draft
- **WHEN** a draft with a valid adult profile and a locked portrait is approved
- **THEN** it returns the character with `status: "approved"` and `approvedAt` set

### Requirement: Archive and restore
`characters.archive(id)` SHALL set `status: "archived"` and `archivedAt`. `characters.restore(id)` SHALL clear `archivedAt` and set the status back to `approved` when the character was approved or is a seed character, and to `draft` otherwise. Neither SHALL need a key.

#### Scenario: Archive then restore
- **WHEN** an approved character is archived and then restored
- **THEN** it is hidden from the default roster while archived, and is `approved` again after the restore
