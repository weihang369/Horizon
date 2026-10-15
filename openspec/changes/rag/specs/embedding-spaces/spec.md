# Spec Delta

## MODIFIED Requirements

### Requirement: Queries and documents are embedded differently
A query SHALL be embedded with the active space's query instruction. A passage or memory SHALL be embedded as its plain text. The same text embedded as a query and as a document SHALL be treated as two different inputs. From M12, a space MAY carry a document template: a knowledge passage in such a space SHALL be embedded with its source's title (without its file extension) and its heading path (left out when it equals the locator) before its text, while memories stay plain.

#### Scenario: Query instruction
- **WHEN** a user message is embedded for retrieval
- **THEN** the request text starts with the space's instruction and contains the message after it, while passage requests carry the passage text alone

#### Scenario: Header on a passage
- **WHEN** a passage under "Long shift blocks" from "Shift Fatigue Review.pdf" is embedded in a space with the header template
- **THEN** its request text is "Shift Fatigue Review", a newline, "Long shift blocks", a blank line, then the passage

#### Scenario: Seed passage without a heading line
- **WHEN** a seed passage whose heading equals its locator is embedded in that space
- **THEN** its request text is the title, a blank line, then the passage

#### Scenario: Memories stay plain
- **WHEN** a memory is embedded in a space with the header template
- **THEN** its request text is the memory text alone

### Requirement: Repeated text is not embedded twice
Within one backend run, a text already embedded in the same space and form SHALL be served from a cache, with no provider request and no ledger row. From M12, the cache SHALL key on the exact text sent (instruction or header included), and a second request for a text whose embedding is still in flight SHALL wait for that call instead of sending again.

#### Scenario: Same question twice
- **WHEN** the same user message text is embedded for retrieval twice in one run
- **THEN** one embedding request and one ledger row exist for it

#### Scenario: Two speakers at once
- **WHEN** two group repliers' deep turns ask for the same message's embedding at the same moment
- **THEN** one embedding request and one ledger row exist for it, and both get the vector

#### Scenario: Changed instruction
- **WHEN** the space's query instruction is changed and the same message is embedded again
- **THEN** a new embedding request is made

## ADDED Requirements

### Requirement: The default space for new installs
A fresh install SHALL start in the space `qwen3-emb-8b@1024+h`: Qwen3-Embedding-8B at 1,024 dimensions with the header template and the query instruction "Given a chat message, retrieve passages that help answer it". An existing install SHALL keep its active space until a build switches it.

#### Scenario: Fresh install
- **WHEN** the backend starts on an empty data directory
- **THEN** the active space is `qwen3-emb-8b@1024+h` with its template and instruction

#### Scenario: Existing install
- **WHEN** the backend starts on a database whose active space is `qwen3-emb-8b@1024`
- **THEN** that space stays active

### Requirement: A build copies vectors that would not change
When a space is built from the active one with the same model and dimensions, memory vectors SHALL be copied rather than embedded again, with no request and no ledger row. Knowledge vectors SHALL be copied only when the document template is also the same. Everything else SHALL be embedded as today.

#### Scenario: Switching to the header space
- **WHEN** the header space is built from `qwen3-emb-8b@1024` on a database with 40 memories and 300 indexed passages
- **THEN** the memories' vectors are copied with no ledger row, and the passages are embedded again with `embed_doc` rows

### Requirement: A space is embedded on its own provider
Every embedding request for a space SHALL pin that space's own provider, with no fallbacks; the configured embedding provider SHALL be used only when a caller names no space.

#### Scenario: A space on another provider
- **WHEN** `horizon space build` builds `bge-m3@1024+h`, whose provider is DeepInfra, while the configured provider is Nebius
- **THEN** its embedding requests pin DeepInfra, and the default space's requests still pin Nebius
