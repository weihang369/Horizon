## Purpose

Defines how character generation jobs (profile drafts, portraits, emotions, songs) are estimated, started, run, cancelled, retried and recovered after a restart, so a provider is never paid twice for the same work without an explicit user Retry.

## ADDED Requirements

### Requirement: Job estimate
`jobs.estimate(input)` SHALL return `{ estimatedCostUsd }`, the sum of the job's task estimates from the committed price table, rounded to 6 decimals. It SHALL spend nothing, need no key, and reject with `not_found` for an unknown or tombstoned character.

#### Scenario: Lean emotion set estimate
- **WHEN** `generationMode` is `lean` and an `emotion_set` job is estimated for a character
- **THEN** the estimate is 3 × the emotion-edit price, and no ledger row is written

#### Scenario: Estimate for a tombstone
- **WHEN** `jobs.estimate` targets a deleted character
- **THEN** it rejects with `not_found`

### Requirement: Task plan per job kind
Each job kind SHALL expand into ordered tasks as the MockClient does:
- `profile_draft`: profile, appearance summary, palette pick and song brief;
- `profile_regenerate`: one profile task;
- `portrait_candidates`: 1 candidate in Lean mode, 2 in Standard; `portrait_tweak`: one;
- `emotion_set`: one edit per emotion (Lean: happy, sad, angry; Standard: all six plus a blink frame), or one expression sheet;
- `emotion_regenerate`: one per listed emotion;
- `song`: one theme song.

#### Scenario: Lean emotion set
- **WHEN** an `emotion_set` job starts in Lean mode with no `emotions` given
- **THEN** its tasks are three `emotion_image` tasks for happy, sad and angry, in that order

#### Scenario: Standard candidates
- **WHEN** a `portrait_candidates` job starts in Standard mode
- **THEN** it has two `portrait_candidate` tasks

### Requirement: Starting a job
`jobs.start(input)` SHALL check the following, in this order, before anything is stored:
- a usable key (`missing_key` / `invalid_key`);
- the character exists and is not a tombstone (`not_found`);
- no non-terminal job for the character (`conflict`);
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

### Requirement: Jobs run on the backend clock
Tasks SHALL run in plan order, at most the plan's parallelism at a time and within the provider limits (images 2, music 1, LLM shared with sessions). A task SHALL become `running` with `attempt` incremented. Job `progress` SHALL be the mean task progress, rounded to 3 decimals, and 1 when done. With the scripted ports, task durations SHALL follow the shared timing table.

#### Scenario: Profile draft under the frozen clock
- **WHEN** the clock is frozen, a draft is created, and the clock is advanced by 5,000 ms
- **THEN** the `profile_draft` job is `succeeded` and the character's profile name and role are filled in

### Requirement: Job outcome
When no task is queued or running, the job SHALL become:
- `succeeded` if no task failed;
- `failed` if no task succeeded (with `error.code: "provider_error"`);
- `partial` otherwise.

It SHALL record `finishedAt`, clear the character's `activeJobId`, release the remaining reservation and set `actualCostUsd` to the sum of its ledger rows. A succeeded task's result SHALL be kept even when a sibling task fails.

#### Scenario: One candidate fails
- **WHEN** a two-candidate job finishes with one task `failed`
- **THEN** the job is `partial`, the other candidate is `ready` with a URL, and `activeJobId` is cleared

### Requirement: Retry a failed task
`jobs.retryTask(jobId, taskId)` SHALL need a usable key, SHALL only accept a `failed` task, and SHALL reject with `conflict` when the task has used `maxAttempts` (3). It SHALL requeue the task, set the job back to `running`, reserve that task's estimate and set `activeJobId` again. A retry is the only way a task is sent to a provider again.

#### Scenario: Retry succeeds
- **WHEN** a task failed, its job is `partial`, and the task is retried
- **THEN** the task runs again, and the job ends `succeeded`

#### Scenario: Out of attempts
- **WHEN** a task has failed on its third attempt and is retried
- **THEN** the call rejects with `conflict`

### Requirement: Cancel a job
`jobs.cancel(jobId)` SHALL need no key. It SHALL mark every queued or running task `skipped`, set the job to `cancelled` with `finishedAt`, release the remaining reservation and clear `activeJobId`. Completed results SHALL be kept. A provider call already sent SHALL be allowed to finish and be recorded in the ledger at its real cost, with its result stored but not applied.

#### Scenario: Cancel during an emotion set
- **WHEN** an emotion set with happy done and sad in flight is cancelled
- **THEN** the job is `cancelled`, happy stays on the character, sad is `skipped`, and the in-flight image is recorded in the ledger

### Requirement: Never pay twice
A task SHALL be marked as sent, durably, after its cap preflight passes and before its provider request. The provider's output SHALL be stored durably before the task records its result, and the result and the task's ledger row SHALL be committed together. Derived files SHALL be made afterwards and SHALL be re-derivable from the stored output at no cost.

#### Scenario: Crash after the provider answered
- **WHEN** the backend stops after a task's provider call returned but before its result was committed, and is started again
- **THEN** the task is `failed` with a retryable `provider_error`, no provider call is made for it during recovery, and its job is `partial` or `failed`

### Requirement: Restart recovery
On startup, before serving requests, the backend SHALL recover every job left `queued` or `running`:
- a task never sent SHALL be requeued;
- a task with a stored result SHALL only finish its derived output;
- a task sent with no result SHALL become `failed` (retryable).

The job SHALL then continue, and its whole remaining estimate SHALL be reserved again.

#### Scenario: Kill mid-job and restart
- **WHEN** a two-candidate job has one task finished and one in flight, the process stops, and the backend restarts over the same data directory
- **THEN** the provider receives no further request for either task, the finished candidate is still `ready`, and the in-flight one is `failed` and retryable

#### Scenario: Queued task resumes
- **WHEN** the backend restarts while a job has a task that was never sent
- **THEN** that task runs after startup, and is sent to the provider exactly once

### Requirement: Job events on the global stream
Job changes SHALL be published on the global stream:
- `task.update { jobId, task }` when a task starts, gets a `previewUrl`, succeeds, fails or is skipped;
- `job.progress { job }` while the job runs;
- `job.done { job }` once when it reaches a terminal status;
- `entity.changed { kind: "job", id }` after each change.

Every payload SHALL validate against the contract schema.

#### Scenario: Subscriber sees a portrait job
- **WHEN** a global subscriber is connected and a portrait job runs to the end
- **THEN** it receives `task.update` events for that job, then exactly one `job.done` whose job is terminal

### Requirement: Job fault scenarios
In test mode, `image_fail_partial` SHALL make the second image task of the next jobs fail at 60 % on its first attempt. `image_fail_all` SHALL make every image task fail. `song_fails` SHALL make theme-song tasks fail. Each failure is a retryable `provider_error`, and with `image_fail_partial` a retry succeeds.

#### Scenario: Partial failure then retry
- **WHEN** `image_fail_partial` is applied, Standard mode is set, and a `portrait_candidates` job runs
- **THEN** the job ends `partial`, and after retrying the failed task it ends `succeeded`
