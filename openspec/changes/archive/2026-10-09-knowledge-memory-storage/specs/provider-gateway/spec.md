## ADDED Requirements

### Requirement: Scripted embedding source
Embedding requests made by the scripted embedder SHALL run through the same paid-call pipeline as real ones: key check, preflight with caps and reservations, and one ledger row per batch of at most 32 texts. The rows SHALL have category `embedding`, `provider: "scripted"`, the active space's model, input tokens counted from the texts, and a cost priced from the committed price table. The scripted embedder SHALL never open a network connection, and SHALL return deterministic unit vectors of the space's dimensions.

#### Scenario: Scripted source indexed with a key
- **WHEN** with the scripted profile and a key set a three-paragraph Markdown source is added
- **THEN** exactly one `embedding` ledger row with `provider: "scripted"`, `tokensIn > 0` and the embedding model is written, and no network connection is opened

#### Scenario: Same text, same vector
- **WHEN** the scripted embedder embeds the same passage text twice in different runs
- **THEN** both vectors are identical and have unit length
