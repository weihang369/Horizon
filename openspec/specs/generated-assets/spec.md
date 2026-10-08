# generated-assets Specification

## Purpose

Defines the files and asset records that generation produces: paid originals kept first, small WebP derivatives served immutably, portrait candidates, versioned emotion images, the locked base portrait and the theme song, so the UI always shows a consistent, affordable set.

## Requirements

### Requirement: Originals first, WebP derivatives
For every generated image the backend SHALL write the provider's original under `data/originals/` before anything points to it. It SHALL then derive a 768×1024 WebP (centre-cropped, never stretched) under `data/assets/gen/{worldId}/{characterId}/`, at most 250 KB. Files SHALL be written atomically, so no reader ever sees a partial file.

#### Scenario: Emotion image on disk
- **WHEN** an emotion edit succeeds
- **THEN** the asset's URL is under `/assets/gen/`, the served file is a 768×1024 WebP of at most 250 KB, and the provider's original exists under `data/originals/`

#### Scenario: Derived file re-made for free
- **WHEN** a task's original was stored but its WebP was not written before a restart
- **THEN** after startup the WebP exists and no provider call was made

### Requirement: Generated files are immutable
A generated file's name SHALL never be reused for different content: every new candidate, emotion version, cover or song gets a new name. Generated files SHALL be served with year-long immutable caching.

#### Scenario: Regenerated emotion gets a new URL
- **WHEN** an approved character's happy emotion is regenerated
- **THEN** the new version's URL differs from the previous version's URL, and the previous URL still serves the old image

### Requirement: Portrait candidates
A `portrait_candidates` or `portrait_tweak` job SHALL add its candidates to the character with status `generating` as soon as it starts. Each becomes `ready` with a URL, or `failed`, when its task ends. The character's candidates SHALL be:
- the latest `portrait_candidates` batch, plus any later tweak batches;
- plus earlier candidates that are `selected`;
- or the seed batch when no job has run.

#### Scenario: Candidates appear immediately
- **WHEN** a two-candidate job starts
- **THEN** `characters.get` shows two new candidates with status `generating` and a blank placeholder URL

#### Scenario: Tweak keeps the batch
- **WHEN** a tweak job runs after a two-candidate batch
- **THEN** the character shows three candidates: the two earlier ones and the tweak

### Requirement: Lock the base portrait
`characters.lockPortrait(id, candidateId)` SHALL reject with `not_found` for an unknown candidate and with `conflict` for a candidate that is not `ready`. Otherwise it SHALL mark that candidate `selected` (the others not), and store it as the next neutral emotion version, active. The character's `basePortraitUrl` and `emotions.neutral` SHALL then show it, and a draft's `creationStep` SHALL move on to `emotions`.

#### Scenario: Lock a ready candidate
- **WHEN** a ready candidate is locked
- **THEN** `emotions.neutral.url` and `appearance.basePortraitUrl` equal that candidate's URL, and only that candidate is `selected`

#### Scenario: Lock a generating candidate
- **WHEN** a candidate that is still generating is locked
- **THEN** the call rejects with `conflict`

### Requirement: Emotion asset versions
Each generated emotion or blink image SHALL be stored as a new version for its `(emotion, variant)` slot, with at most one active version per slot. On a character that is not yet approved, or whose slot has no active version, the new version SHALL become active. On an approved character with an active version, it SHALL stay inactive until accepted. `characters.assets(id)` SHALL list every version.

#### Scenario: Draft emotions go live
- **WHEN** an emotion set succeeds for a draft
- **THEN** `characters.get` shows the new happy, sad and angry images in `emotions`

#### Scenario: Approved character keeps its face until accepted
- **WHEN** an approved character's sad emotion is regenerated
- **THEN** `emotions.sad` still shows the old image, and `characters.assets` lists both versions with the new one inactive

### Requirement: Accept an asset version
`characters.acceptAssetVersion(assetId)` SHALL make that version the only active one in its slot, in one transaction, and return the character with the slot pointing at it. It SHALL reject with `not_found` for an unknown asset or a tombstoned owner. An accepted version on an approved character SHALL bump the character's `version`.

#### Scenario: Accept a regenerated emotion
- **WHEN** the inactive sad version is accepted
- **THEN** `emotions.sad` shows it, the previous sad version is inactive, and exactly one sad version is active

### Requirement: Expression sheet
An `emotion_set` with technique `expression_sheet` SHALL make one sheet image. Its emotion tasks SHALL succeed from cells of that sheet without further provider calls. If the sheet fails, its emotion tasks SHALL be `skipped`.

#### Scenario: Sheet slices into emotions
- **WHEN** an expression-sheet emotion set succeeds
- **THEN** each requested emotion has a new image, and the ledger has one image row for the job

### Requirement: Theme song
A `song` job SHALL produce a `ThemeSong` from the character's brief (or the edited brief in the job input) as a new version, and make it the character's `themeSongId`. With the naive song generator, the song SHALL be the provider's audio: an MP3 served under the character's generated files, with `format: "mp3"`, `bytes`, `durationSec`, the model and recorded cost in `generation`, and a `licenseNote` naming the model. With the scripted song generator, the song SHALL be the free procedural theme: a `.proc.json` spec that the app renders. It SHALL cost nothing, its `format` SHALL be omitted, and its `licenseNote` SHALL say so.

#### Scenario: Procedural theme
- **WHEN** a `song` job runs with the scripted song generator
- **THEN** `characters.song(id)` returns a ready song whose URL ends in `.proc.json`, and no music ledger row is written

#### Scenario: Lyria song
- **WHEN** a `song` job runs with the naive song generator and the provider returns an MP3 clip
- **THEN** `characters.song(id)` returns a ready song whose URL ends in `.mp3` with `format: "mp3"` and a positive `durationSec`, the provider's original is kept, and exactly one ledger row with `category: "music"` and `purpose: "song"` carries the job's `job_id`

### Requirement: Procedural fallback for a failed song
When the naive music call fails because the provider could not make the song (a provider error, a timeout, a refusal, a rate limit, or audio that is not a usable MP3), the theme-song task SHALL still succeed with the free procedural theme, and its `licenseNote` SHALL say the music model was unavailable. Any charge the provider may have made SHALL still be recorded. A missing or invalid key, insufficient credits or a reached cap SHALL fail the task as for any other paid task, with no fallback.

#### Scenario: Provider error falls back
- **WHEN** a naive `song` job runs and the provider answers the music call with a 5xx error
- **THEN** the job is `succeeded`, the song's URL ends in `.proc.json`, its `licenseNote` says the music model was unavailable, and no music ledger row is written

#### Scenario: Charged timeout falls back and is billed
- **WHEN** a naive `song` job's music call times out after the request was sent
- **THEN** the job is `succeeded` with the procedural theme, and one music ledger row at the song estimate carries the job's `job_id`

#### Scenario: Cap reached does not fall back
- **WHEN** the daily cap is reached between the job start and the music call's preflight
- **THEN** the theme-song task is `failed` with `daily_budget_exceeded`, the character's song is unchanged, and no provider request is sent

### Requirement: Orphaned files are swept
At startup the backend SHALL delete temporary files, and generated files under `assets/gen/` that no record references and that are older than one hour. It SHALL NOT delete originals that a task still references.

#### Scenario: Leftover temp file
- **WHEN** a `.tmp` file is left under `data/assets/gen/` and the backend starts
- **THEN** the file no longer exists
