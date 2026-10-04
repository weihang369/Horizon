# openrouter-key Specification

## Purpose

Covers how the backend obtains, stores, reports and checks the user's OpenRouter key: where the key comes from, what `openRouterKeyStatus` and `demoMode` mean, and the connection and model probes in Settings.

## Requirements

### Requirement: Key sources
The backend SHALL read the key from `OPENROUTER_API_KEY` (the environment, then `.env`) and otherwise from `data/secrets.local.json`. The first source that has a key wins. The key SHALL be held in memory as a secret value, so that converting it to a string or a representation never reveals it.

#### Scenario: Environment key wins
- **WHEN** `OPENROUTER_API_KEY` is set in `.env` and `data/secrets.local.json` holds a different key
- **THEN** calls use the `.env` key

#### Scenario: Secret value never prints
- **WHEN** the in-memory key object is formatted into a log message
- **THEN** the message shows a masked placeholder, not the key

### Requirement: Test mode ignores real keys
When `HORIZON_TEST=1`, the backend SHALL ignore `OPENROUTER_API_KEY` from the environment and `.env`. It SHALL start every test run with no key unless a test sets one through `PUT /settings/key`.

#### Scenario: Developer key present during tests
- **WHEN** a developer's `.env` holds a real key and the HTTP contract suite starts a test-mode backend
- **THEN** settings report `openRouterKeyStatus: "missing"` until the harness sets a key

### Requirement: Setting the key
`PUT /api/v1/settings/key` with `{ "key": string }` SHALL accept a key matching `sk-or-` followed by one or more of `[A-Za-z0-9_-]`, after trimming. It SHALL write the key to `data/secrets.local.json` and return `AppSettings`, without any network call. A key that doesn't match SHALL reject with `validation` and change nothing. `{ "key": null }` SHALL delete the secrets file.

#### Scenario: Save a key
- **WHEN** `PUT /settings/key` is sent with `{ "key": "sk-or-test-0001" }`
- **THEN** the response has `openRouterKeyStatus: "set"` and `demoMode: false`, and no outbound request was made

#### Scenario: Malformed key
- **WHEN** `PUT /settings/key` is sent with `{ "key": "hello" }`
- **THEN** it rejects with `validation`, and the stored key is unchanged

#### Scenario: Clear the key
- **WHEN** `PUT /settings/key` is sent with `{ "key": null }` and no environment key is set
- **THEN** `data/secrets.local.json` no longer exists, and settings report `openRouterKeyStatus: "missing"` and `demoMode: true`

### Requirement: Environment key cannot be overridden from the UI
While the effective key comes from the environment or `.env`, `PUT /settings/key` SHALL reject with `conflict` and `details: { field: "key", source: "env" }`, and SHALL write nothing.

#### Scenario: Env key present
- **WHEN** `OPENROUTER_API_KEY` is set and the UI saves a different key
- **THEN** the request rejects with `conflict`, `details.source: "env"`, and `data/secrets.local.json` is not written

### Requirement: Key status and demo mode
`openRouterKeyStatus` SHALL be:
- `missing` when there is no key;
- `invalid` once OpenRouter has answered any call with 401 for the current key;
- `set` otherwise.

`invalid` SHALL last until the key changes or the backend restarts. `demoMode` SHALL be true exactly when the status is not `set`.

#### Scenario: A 401 flips the status
- **WHEN** a key is set and OpenRouter answers a call with 401
- **THEN** the call rejects with `invalid_key`, and the next `GET /settings` reports `openRouterKeyStatus: "invalid"` and `demoMode: true`

#### Scenario: New key clears invalid
- **WHEN** the status is `invalid` and a different well-formed key is saved
- **THEN** the status is `set`

### Requirement: Connection test
`POST /api/v1/settings/test-connection` SHALL query OpenRouter's key-info endpoint, and its credits endpoint where available. It SHALL return `{ ok: true, latencyMs, creditsUsd? }`. With no key it SHALL reject with `missing_key`, and with a rejected key with `invalid_key`. The test SHALL be free and write no ledger row.

#### Scenario: Good key
- **WHEN** a key is set and the recorded key-info and credits responses succeed with $4.21 remaining
- **THEN** the response is `{ ok: true, latencyMs: <number>, creditsUsd: 4.21 }`, and no ledger row is written

#### Scenario: No key
- **WHEN** no key is set and the connection is tested
- **THEN** it rejects with `missing_key`

### Requirement: Model probe
`POST /api/v1/settings/test-model` with `{ role }` SHALL run the cheapest probe for that role and return `{ ok: true, latencyMs, model }`, where `model` is the role's override if set, else its configured model. The probes SHALL be:
- chat: a 1-token completion;
- decision: a one-question Jev call;
- embedding: a one-word embedding;
- image and music: a metadata check only, never a paid generation.

Paid probes SHALL pass the cap preflight and be recorded in the ledger with `purpose: "probe"`.

#### Scenario: Embedding probe
- **WHEN** a key is set and `testModel` is called with role `embedding`
- **THEN** the response's `model` equals `settings.models.embedding`, and one `embedding` ledger row with `purpose: "probe"` is written

#### Scenario: Image probe is free
- **WHEN** `testModel` is called with role `image`
- **THEN** no image is generated, and no ledger row is written

#### Scenario: Probe without a key
- **WHEN** no key is set and `testModel` is called
- **THEN** it rejects with `missing_key`
