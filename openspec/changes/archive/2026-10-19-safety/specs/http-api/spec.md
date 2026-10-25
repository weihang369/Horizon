## ADDED Requirements

### Requirement: Content refusals at creation and job start
`POST /sessions` (debate and watch) and `POST /jobs` (portrait candidates, tweak and the expression sheet) SHALL answer HTTP 451 with the standard error envelope, code `content_refused` and `retryable: true`, when the motion check or the image text check refuses, and SHALL store nothing.

#### Scenario: Refused motion
- **WHEN** `POST /sessions` creates an `agent` debate whose motion is refused
- **THEN** the response is 451 with `{ error: { code: "content_refused", … } }`, and `GET /sessions` lists no new session

#### Scenario: Reworded and sent again
- **WHEN** a tweak refused with 451 is sent again as a new request with reworded text that Jev passes
- **THEN** the response is 201 with the job
