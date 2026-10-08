## MODIFIED Requirements

### Requirement: Theme song
A `song` job SHALL produce a `ThemeSong` from the character's brief (or the edited brief in the job input) as a new version, and make it the character's `themeSongId`. With the naive song generator, the song SHALL be the provider's audio: an MP3 served under the character's generated files, with `format: "mp3"`, `bytes`, `durationSec`, the model and recorded cost in `generation`, and a `licenseNote` naming the model. With the scripted song generator, the song SHALL be the free procedural theme: a `.proc.json` spec that the app renders. It SHALL cost nothing, its `format` SHALL be omitted, and its `licenseNote` SHALL say so.

#### Scenario: Procedural theme
- **WHEN** a `song` job runs with the scripted song generator
- **THEN** `characters.song(id)` returns a ready song whose URL ends in `.proc.json`, and no music ledger row is written

#### Scenario: Lyria song
- **WHEN** a `song` job runs with the naive song generator and the provider returns an MP3 clip
- **THEN** `characters.song(id)` returns a ready song whose URL ends in `.mp3` with `format: "mp3"` and a positive `durationSec`, the provider's original is kept, and exactly one ledger row with `category: "music"` and `purpose: "song"` carries the job's `job_id`

## ADDED Requirements

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
