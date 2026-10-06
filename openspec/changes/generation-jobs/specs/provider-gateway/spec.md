## MODIFIED Requirements

### Requirement: Test mode never reaches the network
When `HORIZON_TEST=1`, the gateway SHALL use an in-process fake provider instead of the network. A key starting `sk-or-bad` SHALL get 401 on every call. Any other key SHALL get deterministic successful responses for key info, credits, chat, decisions, embeddings, images and model metadata. The fake SHALL count the requests it receives per endpoint, so tests can assert how many provider calls were made. Automated tests SHALL NOT make live network calls.

#### Scenario: Bad key in test mode
- **WHEN** in test mode the key is `sk-or-bad-zzz` and the connection is tested
- **THEN** it rejects with `invalid_key`, and no network socket is opened

#### Scenario: Live tests are opt-in
- **WHEN** the default backend test run executes
- **THEN** tests marked `live` are skipped

#### Scenario: Fake image
- **WHEN** in test mode a naive image generation is requested
- **THEN** the fake returns a decodable image with a cost, and its images request count goes up by one

## ADDED Requirements

### Requirement: Image request shape
An image request SHALL send `model`, `prompt`, `aspect_ratio`, `resolution` and `n: 1`, and SHALL pass reference images as `input_references: [{ type: "image_url", image_url: { url } }]`, where each URL is a data URL. The image SHALL be read from `data[].b64_json` (or a data URL), and the cost from `usage.cost`.

#### Scenario: Edit with a reference
- **WHEN** an emotion edit is requested with the base portrait as reference
- **THEN** the request body holds one `input_references` entry of type `image_url` whose URL starts with `data:image/`

### Requirement: Paid calls can mark and commit with their caller
A paid call SHALL let its caller run a step after the cap preflight passes and before the request is sent, and a step inside the same transaction that writes the call's ledger row. If the caller's post-response step fails after the provider has charged, the ledger row SHALL still be written. A preflight refusal SHALL run neither step.

#### Scenario: Refused job task is not marked as sent
- **WHEN** an image task's preflight is refused at the creation cap
- **THEN** the task is not marked as sent, and no ledger row is written

#### Scenario: Result and ledger row together
- **WHEN** an image call succeeds for a job task
- **THEN** the task's result and its ledger row become visible in the same commit

### Requirement: Scripted generation source
Paid generation calls made by scripted ports (profile drafts and images) SHALL run through the same paid-call pipeline as real calls, priced from the committed price table, with ledger rows carrying `provider: "scripted"`. They SHALL never open a network connection, and their duration SHALL follow the shared timing table on the backend clock.

#### Scenario: Scripted portrait is billed
- **WHEN** the scripted profile runs a one-candidate portrait job with a key set
- **THEN** one ledger row with `category: "image"`, `provider: "scripted"` and the job's `job_id` is written, and no network connection is opened
