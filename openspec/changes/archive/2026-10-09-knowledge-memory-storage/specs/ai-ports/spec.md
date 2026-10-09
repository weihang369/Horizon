## MODIFIED Requirements

### Requirement: AI profile selection
`HORIZON_AI_PROFILE` SHALL select `scripted` or `naive` for every AI port. Without it, the profile SHALL be `naive` when a key is set and `scripted` otherwise. A per-port variable (`HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, `HORIZON_AI_DRAFTER`, `HORIZON_AI_IMAGE`, `HORIZON_AI_SONG`, `HORIZON_AI_EMBEDDER`, `HORIZON_AI_KNOWLEDGE_RETRIEVER`, `HORIZON_AI_MEMORY_RETRIEVER`, `HORIZON_AI_CONVERTER`, and the others for each port) SHALL override the profile for that port. The turn engine, the router, the profile drafter, the image generator, the song generator, the embedder and the memory and knowledge retrievers have naive implementations; every other port SHALL use its scripted one in both profiles. The memory writer SHALL write nothing in both profiles. The document converter SHALL NOT depend on the key: it SHALL convert real documents unless overridden, and in test mode it SHALL default to a deterministic converter that never starts a process.

#### Scenario: Override one port
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_TURN=scripted`
- **THEN** replies come from the scripted turn engine, and group routing uses the Jev router

#### Scenario: Scripted images under a naive profile
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_IMAGE=scripted`
- **THEN** portrait jobs produce placeholder images with no provider image request, while profile drafts use the naive drafter

#### Scenario: Procedural songs under a naive profile
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_SONG=scripted`
- **THEN** a `song` job produces the procedural theme with no provider music request and no music ledger row

#### Scenario: Real conversion without a key
- **WHEN** a normal (non-test) backend has no key and conversion is ready, and a PDF is added
- **THEN** the PDF's real text is extracted, and the source ends `keyword_only`

#### Scenario: Deterministic conversion in test mode
- **WHEN** a PDF is added in test mode
- **THEN** it gets placeholder passages without starting any process, as the MockClient does

### Requirement: Ports see frozen, scoped context
Every AI port SHALL receive an immutable, JSON-serialisable context: the session, its participants with their energy, recent messages (active variants only), the latest rolling summary, mode config and state, the world and character scope, and the memories and knowledge passages already retrieved for the speaker. A port SHALL reach the provider only through the gateway, with calls labelled by purpose. A port SHALL NOT read or write session, memory or knowledge rows directly.

#### Scenario: Context round-trips through JSON
- **WHEN** a turn context is serialised to JSON and parsed back
- **THEN** the result equals the original, so an evaluation harness can build contexts from fixtures

#### Scenario: Retrieved hits are in the context
- **WHEN** a reply turn starts for a character with matching knowledge
- **THEN** the engine's context already holds the retrieved passages, each with its source title, locator and text

### Requirement: Purge hooks are delivered at least once
After a session, character, world or message deletion, or a memory Forget, commits, the backend SHALL queue a purge entry naming the scope and IDs. A worker SHALL call the AI layer's matching hook (the delete hook, or the forget hook for memories) for each entry until it succeeds, and SHALL retry pending entries at startup. The default hooks SHALL do nothing and succeed.

#### Scenario: Retried after a crash
- **WHEN** a session is deleted and the backend stops before the purge hook runs
- **THEN** after restart, the hook is called with scope `session` and the session's ID, and the entry is marked done

#### Scenario: Forget reaches the forget hook
- **WHEN** a memory is forgotten
- **THEN** the forget hook is called with the forgotten memory IDs, their character, and the messages whose traces recalled them
