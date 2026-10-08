## ADDED Requirements

### Requirement: Music request shape
A music request SHALL be a streamed chat completion to the music model with `modalities: ["text", "audio"]`, `stream: true` and usage included. It SHALL NOT carry the main LLM's pinned routing block or its fallback chat model. The audio SHALL be the concatenation of the base64 `choices[0].delta.audio.data` chunks, and the cost SHALL come from `usage.cost`.

#### Scenario: Streamed clip is assembled
- **WHEN** the provider streams a music response in three audio chunks followed by a usage chunk
- **THEN** the gateway returns the decoded bytes of all three chunks in order, and the ledger row carries the reported cost with `category: "music"` and `purpose: "song"`

#### Scenario: No main-LLM routing on a music call
- **WHEN** a music request is sent
- **THEN** its body has no `provider.order` pinned to the main LLM's provider and no `models` fallback list

#### Scenario: Stream without audio
- **WHEN** a music stream ends without any audio data
- **THEN** the call fails with `provider_error`, and it is recorded in the ledger at its estimate because it may have been charged
