## MODIFIED Requirements

### Requirement: AI profile selection
`HORIZON_AI_PROFILE` SHALL select `scripted`, `naive` or `agent` for every AI port. Without it, the profile SHALL be `naive` when a key is set and `scripted` otherwise. A per-port variable (`HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, `HORIZON_AI_DRAFTER`, `HORIZON_AI_IMAGE`, `HORIZON_AI_SONG`, `HORIZON_AI_EMBEDDER`, `HORIZON_AI_KNOWLEDGE_RETRIEVER`, `HORIZON_AI_MEMORY_RETRIEVER`, `HORIZON_AI_CONVERTER`, `HORIZON_AI_SUMMARISER`, `HORIZON_AI_PLANNER`, `HORIZON_AI_FACE_CHECK`, `HORIZON_AI_GUARDRAIL`, and the others for each port) SHALL override the profile for that port. The turn engine, the router, the summariser, the profile drafter, the image generator, the song generator, the embedder and the memory and knowledge retrievers have naive implementations; the planner, the face check and the guardrail have a naive implementation that does nothing (the guardrail passes with no checks); every other port SHALL use its scripted one under `naive`. Under `agent`, each port SHALL use its agent implementation when one exists (from M8, the turn engine; from M9, the planner, the reaction predictor and the face check; from M14, the guardrail), else its naive one when one exists, else its scripted one; without a key every port SHALL be scripted. The scripted planner, face check and reaction predictor SHALL record simulated spend only when the profile is `scripted` or no key is set, never when they stand in for a missing naive implementation while a key is set. The memory writer SHALL follow `long-term-memory`'s writers per profile. The document converter SHALL NOT depend on the key: it SHALL convert real documents unless overridden, and in test mode it SHALL default to a deterministic converter that never starts a process.

#### Scenario: Override one port
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_TURN=scripted`
- **THEN** replies come from the scripted turn engine, and group routing uses the Jev router

#### Scenario: Scripted images under a naive profile
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_IMAGE=scripted`
- **THEN** portrait jobs produce placeholder images with no provider image request, while profile drafts use the naive drafter

#### Scenario: Procedural songs under a naive profile
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_SONG=scripted`
- **THEN** a `song` job produces the procedural theme with no provider music request and no music ledger row

#### Scenario: Agent falls back to naive
- **WHEN** the backend starts with a key and `HORIZON_AI_PROFILE=agent`
- **THEN** every port without an agent implementation (the router, the summariser, the drafter and the others) resolves to the implementation `naive` would use, and the start-up log lists the resolved implementations

#### Scenario: Agent uses its own turn engine
- **WHEN** the backend starts with a key and `HORIZON_AI_PROFILE=agent`
- **THEN** the turn engine, the planner, the reaction predictor, the face check and the guardrail resolve to `agent`

#### Scenario: Naive gets no planner and no check
- **WHEN** the backend starts with a key and `HORIZON_AI_PROFILE=naive`
- **THEN** the planner, the face check and the guardrail resolve to `naive` (no-op; the guardrail reports no checks), and the reaction predictor resolves to `scripted` without simulated spend

#### Scenario: Agent without a key
- **WHEN** the backend starts with no key and `HORIZON_AI_PROFILE=agent`
- **THEN** every port except the converter resolves to `scripted`

#### Scenario: Real conversion without a key
- **WHEN** a normal (non-test) backend has no key and conversion is ready, and a PDF is added
- **THEN** the PDF's real text is extracted, and the source ends `keyword_only`

#### Scenario: Deterministic conversion in test mode
- **WHEN** a PDF is added in test mode
- **THEN** it gets placeholder passages without starting any process, as the MockClient does

## ADDED Requirements

### Requirement: The guardrail checks prompt text
The guardrail port SHALL also check the text an image job or a song task will send, by kind (`image` or `song`). The `agent` guardrail SHALL ask Jev (four image questions in one request, or one song question) with deadline `timeoutsMs.decision.guardrail_prompt`, and SHALL keep Jev's answers in memory by the text's hash. `naive` and `scripted` SHALL pass with no checks.

#### Scenario: A repeat costs nothing
- **WHEN** the same portrait subject is checked twice in one backend run
- **THEN** one `guardrail` decision request is made

#### Scenario: A fail-open pass is not kept
- **WHEN** the first check of a text fails and the same text is checked again
- **THEN** a second decision request is made
