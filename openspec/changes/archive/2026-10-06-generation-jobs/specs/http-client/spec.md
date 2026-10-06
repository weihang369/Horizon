## ADDED Requirements

### Requirement: Characters, jobs and covers over HTTP
The `HttpClient` SHALL implement, against the backend routes:
- `characters` `createDraft`, `update`, `lockPortrait`, `approve`, `archive`, `restore`, `delete` and `acceptAssetVersion`;
- `jobs` `estimate`, `start`, `cancel` and `retryTask`;
- `worlds.uploadCover`, as a `multipart/form-data` request with one `file` part.

None of these SHALL reject as "not available yet". Every `POST` among them SHALL carry an `Idempotency-Key`.

#### Scenario: Upload a cover over HTTP
- **WHEN** `worlds.uploadCover("wld_seedMeridian", pngFile)` is called
- **THEN** one multipart `POST /worlds/wld_seedMeridian/cover` is sent with an `Idempotency-Key`, and the returned `World` has `cover.kind: "upload"`

#### Scenario: Start a job over HTTP
- **WHEN** `jobs.start({ characterId, kind: "portrait_candidates" })` is called with a key set
- **THEN** one `POST /jobs` is sent, it resolves with the `GenerationJob`, and `jobs.subscribe` on its ID delivers its `task.update` and `job.done` events from the global stream

## MODIFIED Requirements

### Requirement: Methods without a backend yet
A `HorizonClient` method whose backend milestone has not shipped SHALL reject immediately, without sending a request, with a non-retryable `HorizonError` (`code: "validation"`). Its message SHALL say the feature is not available on the local backend yet, and `details.availableIn` SHALL name the milestone.

#### Scenario: Sending a chat message in M1b
- **WHEN** a method from a milestone the backend has not shipped is called on the `HttpClient` (`chat.send` before M3; `characters.addKnowledge` from M4 until M5)
- **THEN** it rejects with `code: "validation"`, `retryable: false` and `details.availableIn` naming that milestone (`"M3"` for `chat.send` before M3, `"M5"` for `characters.addKnowledge`), and no request is made
