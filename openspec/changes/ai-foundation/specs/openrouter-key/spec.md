## MODIFIED Requirements

### Requirement: Model probe
`POST /api/v1/settings/test-model` with `{ role }` SHALL run the cheapest probe for that role and return `{ ok: true, latencyMs, model }`, where `model` is the model the app actually uses for that role (chat and decision from the price table, the others from the settings defaults). Stored model overrides SHALL be ignored. The probes SHALL be:
- chat: a 1-token completion with reasoning off;
- decision: a one-question Jev call;
- embedding: a one-word embedding;
- image and music: a metadata check only, never a paid generation.

Paid probes SHALL pass the cap preflight and be recorded in the ledger with `purpose: "probe"`.

#### Scenario: Embedding probe
- **WHEN** a key is set and `testModel` is called with role `embedding`
- **THEN** the response's `model` equals `settings.models.embedding`, and one `embedding` ledger row with `purpose: "probe"` is written

#### Scenario: Override ignored
- **WHEN** a stored override sets the chat model to `other/model`, and `testModel` is called with role `chat`
- **THEN** the probe uses the price table's chat model, and the response names it

#### Scenario: Chat probe without thinking
- **WHEN** `testModel` is called with role `chat`
- **THEN** the request carries `reasoning: {enabled: false}`

#### Scenario: Image probe is free
- **WHEN** `testModel` is called with role `image`
- **THEN** no image is generated, and no ledger row is written

#### Scenario: Probe without a key
- **WHEN** no key is set and `testModel` is called
- **THEN** it rejects with `missing_key`
