## MODIFIED Requirements

### Requirement: Starting a job
`jobs.start(input)` SHALL check the following, in this order, before anything is stored:
- a usable key (`missing_key` / `invalid_key`);
- the character exists and is not a tombstone (`not_found`);
- no non-terminal job for the character (`conflict`);
- under `agent`, for `portrait_candidates`, `portrait_tweak` and an expression sheet, the compiled user-written text passes the image text check (`content_refused`);
- the whole estimate fits the caps (402).

On success it SHALL store the job as `queued`, set the character's `activeJobId`, reserve the estimate and return the `GenerationJob` (201).

#### Scenario: Second job for the same character
- **WHEN** a character has a running job and another `jobs.start` targets it
- **THEN** the call rejects with `conflict`, and no second job exists

#### Scenario: Without a key
- **WHEN** no key is set and `jobs.start` is called for a draft character
- **THEN** it rejects with `missing_key`, and no job row is written

#### Scenario: Same Idempotency-Key after a restart
- **WHEN** `POST /jobs` succeeds, the backend restarts, and the same request is sent again with the same `Idempotency-Key`
- **THEN** the stored response is replayed, and no second job is created

#### Scenario: A likeness tweak is refused
- **WHEN** an `agent` `portrait_tweak` starts with "make him look like Henry Cavill" and Jev answers the likeness question p 0.93
- **THEN** it rejects with `content_refused` and "Tweaks can't make a portrait look like a real person or an existing character, or add nudity, gore, weapons or a childlike look. Change the wording and try again.", no job row or hold exists, and no image request is sent

#### Scenario: Jev down lets the job start
- **WHEN** the image text check's request fails
- **THEN** the job starts, and the skip is logged

## ADDED Requirements

### Requirement: What the image text check reads
The check SHALL read the compiled text the job would send: the subject block (and the API-only note) for portrait candidates and the expression sheet, and the compiled tweak for a tweak. Emotion edits and `emotion_regenerate` SHALL NOT be checked. Its spend SHALL carry the character's ID and no job ID.

#### Scenario: Edits are not checked
- **WHEN** an `agent` `emotion_set` with edits starts
- **THEN** no `guardrail` decision request is made
