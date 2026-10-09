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

### Requirement: Demo-data reset on every client
`HorizonClient` SHALL expose `admin.resetDemo(): Promise<void>` (rev 1.3 addendum, additive; `schemaVersion` stays `1`). It SHALL resolve once the reset described in `demo-data` has completed. Every client SHALL emit `mock.reset` on the global stream afterwards. The app's "Reset demo data" actions SHALL call it, not a mock-only API.

#### Scenario: Reset through the interface
- **WHEN** `client.admin.resetDemo()` resolves on either client
- **THEN** seed records are back to their shipped state, and `onGlobal` subscribers have received `mock.reset`

#### Scenario: Settings button on the HttpClient
- **WHEN** the app runs on the `HttpClient` and the user confirms "Reset demo data" in Settings
- **THEN** `POST /api/v1/admin/reset-demo` is called, and the screen re-queries after `mock.reset`

### Requirement: Portable suite runs on every client
Each portable contract test SHALL declare the milestone whose backend routes it needs. A harness SHALL declare the milestone it supports:
- tests within that milestone SHALL run;
- every other test SHALL be reported as pending under a name that states its milestone, never skipped silently.

The suite SHALL run against the backend through an HTTP harness. From M2, the HTTP harness SHALL save an obviously fake key (`sk-or-test-…`) through `settings.setKey` as its `setKey`. From M4, it SHALL support M4. From M5, it SHALL support M5. From M6, it SHALL support M6, so no test is pending on either client. A portable assertion on events collected from a subscription SHALL wait, within a bounded time, for them to be delivered, because a remote client receives them asynchronously. A test whose behaviour depends on a later milestone's feature SHALL be tagged with that milestone. Live knowledge citations are tagged M5.

A harness scenario SHALL replace the previous one, as on the MockClient. On the HTTP harness, `network_down` SHALL make every client request fail before it reaches the server, so the `HttpClient` rejects with `network` exactly as the MockClient does. The harness's own control calls SHALL keep working while it is active.

#### Scenario: HTTP run in M1b
- **WHEN** an HTTP harness declares `supports: "M1b"`
- **THEN** every M1b test runs and passes, and every later test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M2
- **WHEN** the portable suite runs with the HTTP harness against a test-mode backend
- **THEN** every M1b and M2 test passes, and every later test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M3
- **WHEN** the portable suite runs with the HTTP harness declaring `supports: "M3"` against a test-mode backend
- **THEN** every M1b, M2 and M3 test passes, and every M4, M5 and M6 test, including live knowledge citations, is listed as pending with its milestone in the name

#### Scenario: HTTP run in M4
- **WHEN** the portable suite runs with the HTTP harness declaring `supports: "M4"` against a test-mode backend
- **THEN** every M1b to M4 test passes, including the creation pipeline, partial image failure, job mirroring, cover upload, tombstone and reset tests, and every M5 and M6 test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M5
- **WHEN** the portable suite runs with the HTTP harness declaring `supports: "M5"` against a test-mode backend
- **THEN** every M1b to M5 test passes, including knowledge add, limits, progress, keyword-only upgrade, delete, seed re-index, Forget and live knowledge citations, and every M6 test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M6
- **WHEN** the portable suite runs with the HTTP harness declaring `supports: "M6"` against a test-mode backend
- **THEN** every test runs and passes, including "network down rejects queries too; Reset demo data restores the shipped fixtures", and none is pending

#### Scenario: Mock run is complete
- **WHEN** the portable suite runs with the MockClient harness
- **THEN** every test runs and passes, and none is pending

#### Scenario: Pending list is explicit
- **WHEN** a test's milestone tag is removed or misspelled
- **THEN** the suite fails, rather than running or skipping that test

#### Scenario: Network down on HTTP
- **WHEN** the HTTP harness applies `network_down` and `worlds.list()` is called
- **THEN** it rejects with a `HorizonError` whose `code` is `network` and `retryable` is `true`, and the backend receives no request for it

#### Scenario: Next scenario lifts network down
- **WHEN** `network_down` is applied, then `no_worlds`
- **THEN** `worlds.list()` resolves with `[]` on either client

#### Scenario: World-name rules on both clients
- **WHEN** on either client a world is created with surrounding spaces, then another with the same name in different case, then one with a seed world's shipped name
- **THEN** the first is stored trimmed, and the second and third reject with `conflict` and `details.field: "name"`

### Requirement: Key validity is learned from the provider
The portable suite SHALL assert only the key behaviour both clients share: once a key is rejected, `testConnection` rejects with `invalid_key`, and settings then report `openRouterKeyStatus: "invalid"`. A key that is accepted reports `set`, with `demoMode: false`, and passes `testConnection`. The MockClient's immediate `invalid` on `setKey("sk-or-bad…")` SHALL be covered by a mock-only test.

#### Scenario: Bad key on either client
- **WHEN** `setKey("sk-or-bad-zzz")` is called, then `testConnection`
- **THEN** `testConnection` rejects with `invalid_key`, and `settings.get()` reports `openRouterKeyStatus: "invalid"` and `demoMode: true`

#### Scenario: Good key on either client
- **WHEN** `setKey("sk-or-good")` is called, then `testConnection`
- **THEN** `setKey` returns `openRouterKeyStatus: "set"` and `demoMode: false`, and `testConnection` resolves with `ok: true`
