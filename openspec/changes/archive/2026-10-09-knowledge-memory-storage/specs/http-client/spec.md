## MODIFIED Requirements

### Requirement: Methods without a backend yet
A `HorizonClient` method whose backend milestone has not shipped SHALL reject immediately, without sending a request, with a non-retryable `HorizonError` (`code: "validation"`). Its message SHALL say the feature is not available on the local backend yet, and `details.availableIn` SHALL name the milestone. From M5, every `HorizonClient` method has a backend route, so none SHALL reject this way.

#### Scenario: Sending a chat message in M1b
- **WHEN** a method from a milestone the backend has not shipped is called on the `HttpClient` (`chat.send` before M3; `characters.addKnowledge` before M5)
- **THEN** it rejects with `code: "validation"`, `retryable: false` and `details.availableIn` naming that milestone (`"M3"` for `chat.send` before M3, `"M5"` for `characters.addKnowledge`), and no request is made

#### Scenario: Nothing is held back in M5
- **WHEN** any `HorizonClient` method is called on the `HttpClient` from M5
- **THEN** it sends its request, and none rejects with `details.availableIn`

## ADDED Requirements

### Requirement: Knowledge and memory over HTTP
The `HttpClient` SHALL implement `characters.addKnowledge` (a `multipart/form-data` request with one `file` part for a file, a JSON request for pasted text), `deleteKnowledge`, `reindexKnowledge` and `forgetMemory` against the backend routes. Every `POST` among them SHALL carry an `Idempotency-Key`.

#### Scenario: Upload a Markdown file over HTTP
- **WHEN** `characters.addKnowledge("chr_seedHana", { file })` is called with a `.md` file
- **THEN** one multipart `POST /characters/chr_seedHana/knowledge` is sent with an `Idempotency-Key`, and the returned source has `status: "indexing"`

#### Scenario: Forget over HTTP
- **WHEN** `characters.forgetMemory(id)` is called for an existing memory
- **THEN** one `DELETE /memory/{id}` is sent, and it resolves with no value
