# Spec Delta

## MODIFIED Requirements

### Requirement: Methods without a backend yet
A `HorizonClient` method whose backend milestone has not shipped SHALL reject immediately, without sending a request, with a non-retryable `HorizonError` (`code: "validation"`). Its message SHALL say the feature is not available on the local backend yet, and `details.availableIn` SHALL name the milestone.

#### Scenario: Sending a chat message in M1b
- **WHEN** a method from a milestone the backend has not shipped is called on the `HttpClient` (`chat.send` before M3; `jobs.start` from M3 until M4)
- **THEN** it rejects with `code: "validation"`, `retryable: false` and `details.availableIn` naming that milestone (`"M3"` for `chat.send` before M3, `"M4"` for `jobs.start`), and no request is made

## ADDED Requirements

### Requirement: Sessions and commands over HTTP
The `HttpClient` SHALL implement, against the session routes:
- `sessions` `create`, `rename`, `delete`, `forkSeedSession`, `export`, `leave` and `end`;
- every `chat`, `debate` and `watch` command.

None of these SHALL reject as "not available yet". Every `POST` among them SHALL carry an `Idempotency-Key`. A command SHALL resolve when the backend accepts it (202). Its effects SHALL arrive through `sessions.subscribe`.

#### Scenario: Send over HTTP
- **WHEN** `chat.send(sid, "hello")` is called on a live 1:1 session
- **THEN** one `POST /sessions/{sid}/send` is sent with an `Idempotency-Key`, the promise resolves, and the user message and reply arrive through `sessions.subscribe`

#### Scenario: Conflict surfaces with details
- **WHEN** `sessions.create` is refused because another session is streaming
- **THEN** it rejects with a `HorizonError` whose `code` is `conflict` and whose `details.activeSessionId` names the live session

#### Scenario: Export as text
- **WHEN** `sessions.export("ses_seedDebate4Day")` is called
- **THEN** it resolves with the Markdown body as a string
