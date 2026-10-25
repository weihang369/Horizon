## MODIFIED Requirements

### Requirement: Procedural fallback for a failed song
When the naive music call fails because the provider could not make the song (a provider error, a timeout, a refusal, a rate limit, or audio that is not a usable MP3), the theme-song task SHALL still succeed with the free procedural theme. Its `licenseNote` SHALL say the music model declined the brief after a provider refusal, and that the music model was unavailable otherwise. Any charge the provider may have made SHALL still be recorded. A missing or invalid key, insufficient credits or a reached cap SHALL fail the task as for any other paid task, with no fallback.

#### Scenario: Provider error falls back
- **WHEN** a naive `song` job runs and the provider answers the music call with a 5xx error
- **THEN** the job is `succeeded`, the song's URL ends in `.proc.json`, its `licenseNote` says the music model was unavailable, and no music ledger row is written

#### Scenario: Charged timeout falls back and is billed
- **WHEN** a naive `song` job's music call times out after the request was sent
- **THEN** the job is `succeeded` with the procedural theme, and one music ledger row at the song estimate carries the job's `job_id`

#### Scenario: Cap reached does not fall back
- **WHEN** the daily cap is reached between the job start and the music call's preflight
- **THEN** the theme-song task is `failed` with `daily_budget_exceeded`, the character's song is unchanged, and no provider request is sent

#### Scenario: A provider refusal says so
- **WHEN** the music call is refused by the provider
- **THEN** the job is `succeeded` with the procedural theme, and its `licenseNote` reads "The music model declined this brief, so this is the procedural theme rendered in the app."

## ADDED Requirements

### Requirement: A brief naming an artist gets the procedural theme
Under `agent`, the song task SHALL check the brief it would send before the music call. At or above `safety.tSong` it SHALL make no music call and SHALL succeed with the procedural theme, whose `licenseNote` names the reason. A late or failed check SHALL call the music model as before. The check's spend SHALL carry the job's ID.

#### Scenario: A named band
- **WHEN** an `agent` song job's brief says "sounds like Coldplay's Yellow" and Jev answers p 0.95
- **THEN** no music request is sent, the job is `succeeded`, and the `licenseNote` reads "The brief names an artist or an existing piece, so this is the procedural theme rendered in the app. Edit the brief and compose again for a recorded one."

#### Scenario: A genre brief
- **WHEN** the brief says "warm British indie rock, chiming guitars" and Jev answers p 0.06
- **THEN** the music model is called
