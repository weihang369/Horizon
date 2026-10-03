# client-contract Specification

## Purpose

Defines the wire contract shared by every `HorizonClient` implementation (MockClient now, HttpClient and the FastAPI backend later): shapes, error codes, events, method surface, and the machine-readable schema both languages validate against.

## Requirements

### Requirement: Contract revision 1.3 is additive
Every rev 1.3 change SHALL be additive, and `SCHEMA_VERSION` SHALL stay `1`. Two fields are required, because the server always fills them in: `AppSettings.models.embedding` and `AppSettings.energy.estReplyPoints`. Every other new field SHALL be optional, so that any non-settings fixture that was valid under rev 1.2 still validates.

#### Scenario: Existing entities validate unchanged
- **WHEN** a rev 1.2 character, session, message and knowledge source (from before this change's seed fixes) are validated against the rev 1.3 schemas
- **THEN** each one passes

#### Scenario: Legacy url source still reads
- **WHEN** a stored `KnowledgeSource` has `type: "url"`
- **THEN** it validates and renders as a read-only legacy source

### Requirement: Error codes for missing records, bad input and state conflicts
`ErrorCode` SHALL include `not_found`, `validation` and `conflict`, none of them retryable by default. A client SHALL reject a missing or other-world record with `not_found`, input that breaks a rule or limit with `validation`, and a forbidden state transition with `conflict`. It SHALL NOT use `network` or `provider_error` for these cases.

#### Scenario: Unknown session
- **WHEN** `sessions.get` is called with an ID that doesn't exist
- **THEN** the call rejects with `code: "not_found"` and `retryable: false`

#### Scenario: Sending into a seed recording
- **WHEN** `chat.send` targets a seed session, or a session that has ended
- **THEN** the call rejects with `code: "conflict"`

#### Scenario: Wrong cast size
- **WHEN** `sessions.create` is called with too many or too few characters for the mode
- **THEN** the call rejects with `code: "validation"`, and `details` names the limit that was broken

### Requirement: Errors carry optional machine-readable details
`HorizonErrorShape` SHALL have an optional `details` object. It SHALL survive serialisation (`toJSON`) unchanged.

#### Scenario: Conflict names the live session
- **WHEN** a second live session is refused with `conflict`
- **THEN** `details.activeSessionId` holds the ID of the session that is live

### Requirement: Rev 1.3 ID prefixes
IDs SHALL use the prefixes `kno_` (knowledge source), `kch_` (child chunk), `ksec_` (knowledge section) and `cmd_` (command receipt), in the existing `<prefix>_<alnum>` format.

#### Scenario: New knowledge IDs
- **WHEN** a knowledge source is added
- **THEN** its ID matches `^kno_[0-9A-Za-z]{1,40}$`, and each of its chunk IDs matches `^kch_[0-9A-Za-z]{1,40}$`

### Requirement: Embedding model and ledger category
`AppSettings.models` SHALL include `embedding`. `settings.testModel` SHALL accept the role `"embedding"`. `UsageRecord.category` SHALL include `"embedding"`, and the usage summary SHALL report an `embedding` total.

#### Scenario: Usage summary has an embedding bucket
- **WHEN** `usage.summary()` is called
- **THEN** `byCategory.embedding` is present (0 when nothing was embedded)

### Requirement: Read-only energy threshold in settings
`AppSettings.energy.estReplyPoints` SHALL be `{ off_peak, peak }`, taken from config. `settings.update` SHALL NOT change it.

#### Scenario: Patch is ignored
- **WHEN** `settings.update({ energy: { estReplyPoints: { off_peak: 1, peak: 1 } } })` is called
- **THEN** the returned settings still have `estReplyPoints` `{ off_peak: 4, peak: 8 }`

### Requirement: Turn trace lists its paid calls
`TurnTrace.calls` SHALL be an optional list of `{ purpose, model, costUsd, latencyMs, fallback? }`, one entry per paid call behind the turn. For a reply turn it SHALL include the reply call.

#### Scenario: Live reply trace
- **WHEN** a live 1:1 reply completes and its `insight` arrives
- **THEN** `trace.calls` has an entry with `purpose: "reply"` whose `costUsd` equals the message's `usage.costUsd`

### Requirement: Global stream carries knowledge progress, task updates and resets
`entity.changed` SHALL accept an optional `progress: { stage, pct }`. The global stream SHALL carry `task.update` for every job task change. After a demo-data reset, it SHALL emit `mock.reset` from any client.

#### Scenario: Task update mirrored globally
- **WHEN** a generation job's task changes status
- **THEN** `onGlobal` subscribers receive `{ type: "task.update", jobId, task }`, with no `jobs.subscribe` call needed

### Requirement: Stream event contract matches the reducer
The documented stream contract SHALL include:
- `turn.start.message?`;
- `energy.spent?`;
- `error.messageId?`;
- the rule that a later `insight` for the same `messageId` replaces the earlier trace.

#### Scenario: Second insight replaces the first
- **WHEN** two `insight` events with the same `messageId` are reduced in order
- **THEN** the message's trace equals the second event's trace

### Requirement: Machine-readable schema export
The contract SHALL be exportable as JSON Schema to `backend/horizon/contract/schema.json`. The export SHALL be deterministic, with LF line endings and stable key order, so repeated runs produce byte-identical files.

#### Scenario: Two exports are identical
- **WHEN** the export runs twice in a row on Windows
- **THEN** both outputs are byte-identical, and every entity and event in the contract appears in them

### Requirement: Portable contract suite
The contract test suite SHALL be split into two parts:
- **Portable:** depends only on the `HorizonClient` interface and a test harness (clock, scenario, reset), so that it can run against any client.
- **Mock-only:** covers mock internals.

#### Scenario: Portable suite runs on the MockClient
- **WHEN** the portable suite runs with the MockClient harness
- **THEN** every test passes, and no portable test touches `_db`, `dev` or mock-only modules
