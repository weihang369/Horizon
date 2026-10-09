## Purpose

Defines how knowledge passages, memories and queries become vectors, which model and dimensions a vector space uses, and how the backend switches to a new space without mixing models or losing search (D-64).

## ADDED Requirements

### Requirement: The active space decides the embedding model
Every vector SHALL be computed with the active embedding space's model and dimensions. Changing `models.embedding` in settings SHALL NOT change the model used for an existing space. Vectors from different models SHALL never share a space.

#### Scenario: Edited embedding model
- **WHEN** the user sets `models.embedding` to another model and adds a source with a key set
- **THEN** the source's embedding ledger row names the active space's model, not the edited value

### Requirement: Queries and documents are embedded differently
A query SHALL be embedded with the active space's query instruction. A passage or memory SHALL be embedded as its plain text. The same text embedded as a query and as a document SHALL be treated as two different inputs.

#### Scenario: Query instruction
- **WHEN** a user message is embedded for retrieval
- **THEN** the request text starts with the space's instruction and contains the message after it, while passage requests carry the passage text alone

### Requirement: Vectors match the space's dimensions
The request SHALL ask for the space's dimensions. A longer returned vector SHALL be cut to the space's dimensions and rescaled to unit length. A shorter or non-numeric vector SHALL fail that request as malformed.

#### Scenario: Provider ignores the dimensions
- **WHEN** the provider returns 4,096-dimension vectors for a 1,024-dimension space
- **THEN** 1,024-dimension unit-length vectors are stored

#### Scenario: Short vector
- **WHEN** the provider returns 512-dimension vectors for a 1,024-dimension space
- **THEN** that batch fails as `malformed`, and nothing is stored for it

### Requirement: Repeated text is not embedded twice
Within one backend run, a text already embedded in the same space and form SHALL be served from a cache, with no provider request and no ledger row.

#### Scenario: Same question twice
- **WHEN** the same user message text is embedded for retrieval twice in one run
- **THEN** one embedding request and one ledger row exist for it

### Requirement: Embedding needs a key
Without a valid key, nothing SHALL be embedded and no embedding ledger row SHALL be written. Text stays searchable by keyword.

#### Scenario: Demo mode
- **WHEN** no key is set and a source is added
- **THEN** no embedding request is made, no `embedding` ledger row exists, and keyword search finds the source's passages

### Requirement: Embedding spend is labelled and capped
Each embedding request of at most 32 texts SHALL write one ledger row with category `embedding`, purpose `embed_doc` (passages and memories) or `query_embed` (queries), and the character it is for. Embedding SHALL count toward the daily cap, and SHALL NOT drain energy or count toward a creation cap.

#### Scenario: Seventy passages
- **WHEN** a source with 70 passages is embedded
- **THEN** three `embedding` rows with purpose `embed_doc` are written, and no character's energy changes

### Requirement: Switching spaces never mixes or drops vectors
A new space SHALL be built beside the active one. While it is building, every new vector SHALL be written to both spaces. A final pass SHALL fill whatever the build missed. The new space SHALL become active and the old one retired in one transaction. Retired vector tables SHALL be removed at the next start. Search SHALL use only the active space throughout.

#### Scenario: Source added during a build
- **WHEN** a second space is building and a source is added and embedded
- **THEN** its passages have vectors in both spaces, and after the switch it is still `indexed`

#### Scenario: Atomic switch
- **WHEN** the switch commits
- **THEN** exactly one space is active, the previous one is retired, and vector search returns results from the new space only

#### Scenario: Retired tables removed
- **WHEN** the backend restarts after a switch
- **THEN** the retired space's vector tables no longer exist
