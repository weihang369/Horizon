## ADDED Requirements

### Requirement: Knowledge and memory write routes
The backend SHALL serve the knowledge and memory write routes (see `knowledge-sources` and `long-term-memory`):

| Route | Response |
|---|---|
| `POST /characters/{id}/knowledge`, multipart `file` or JSON `{ type: "text", title, text }` | 201 `KnowledgeSource` (`status: "indexing"`) |
| `DELETE /knowledge/{sourceId}` | 204 |
| `POST /knowledge/{sourceId}/reindex` | `KnowledgeSource` |
| `DELETE /memory/{memoryItemId}` | 204 |

Any other `Content-Type` on the knowledge route SHALL be `validation`. Unknown or tombstoned characters, sources and memories SHALL be 404 `not_found`. Every JSON response SHALL validate against `schema.json`.

#### Scenario: Pasted text over HTTP
- **WHEN** `POST /characters/chr_seedHana/knowledge` is sent with JSON `{ "type": "text", "title": "Notes", "text": "Rice first." }`
- **THEN** the response is 201 with a `KnowledgeSource` of `type: "text"` and `status: "indexing"`, valid against `schema.json`

#### Scenario: Unsupported body
- **WHEN** the knowledge route is called with `Content-Type: text/plain`
- **THEN** the response is 422 `validation`, and no source is created

#### Scenario: Forget over HTTP
- **WHEN** `DELETE /memory/{id}` is sent for an existing memory
- **THEN** the response is 204, and `GET /characters/{id}/memory` no longer lists it

### Requirement: Knowledge upload limit is enforced while reading
A knowledge upload whose declared length is over 10 MB SHALL be refused before its body is read. The body SHALL also be counted while it is read, so an upload without a length can't exceed the limit. Both cases SHALL be 413 with the `validation` error and `details.limit` of 10,485,760. The limit SHALL also hold for a request carrying an `Idempotency-Key`.

#### Scenario: Chunked oversize upload
- **WHEN** an 11 MB file is sent to the knowledge route without a `Content-Length` header
- **THEN** the response is 413 `validation` with `details.limit: 10485760`, and nothing is stored

#### Scenario: Keyed oversize upload
- **WHEN** an 11 MB file is sent with an `Idempotency-Key`
- **THEN** the response is 413 `validation`, and nothing is stored
