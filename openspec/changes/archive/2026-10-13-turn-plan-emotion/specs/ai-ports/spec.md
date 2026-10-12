## MODIFIED Requirements

### Requirement: AI profile selection
`HORIZON_AI_PROFILE` SHALL select `scripted`, `naive` or `agent` for every AI port. Without it, the profile SHALL be `naive` when a key is set and `scripted` otherwise. A per-port variable (`HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, `HORIZON_AI_DRAFTER`, `HORIZON_AI_IMAGE`, `HORIZON_AI_SONG`, `HORIZON_AI_EMBEDDER`, `HORIZON_AI_KNOWLEDGE_RETRIEVER`, `HORIZON_AI_MEMORY_RETRIEVER`, `HORIZON_AI_CONVERTER`, `HORIZON_AI_SUMMARISER`, `HORIZON_AI_PLANNER`, `HORIZON_AI_FACE_CHECK`, and the others for each port) SHALL override the profile for that port. The turn engine, the router, the summariser, the profile drafter, the image generator, the song generator, the embedder and the memory and knowledge retrievers have naive implementations; the planner and the face check have a naive implementation that does nothing; every other port SHALL use its scripted one under `naive`. Under `agent`, each port SHALL use its agent implementation when one exists (from M8, the turn engine; from M9, the planner, the reaction predictor and the face check), else its naive one when one exists, else its scripted one; without a key every port SHALL be scripted. The scripted planner, face check and reaction predictor SHALL record simulated spend only when the profile is `scripted` or no key is set, never when they stand in for a missing naive implementation while a key is set. The memory writer SHALL write nothing in every profile until an agent writer exists. The document converter SHALL NOT depend on the key: it SHALL convert real documents unless overridden, and in test mode it SHALL default to a deterministic converter that never starts a process.

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
- **THEN** the turn engine, the planner, the reaction predictor and the face check resolve to `agent`

#### Scenario: Naive gets no planner and no check
- **WHEN** the backend starts with a key and `HORIZON_AI_PROFILE=naive`
- **THEN** the planner and the face check resolve to `naive` (no-op), and the reaction predictor resolves to `scripted` without simulated spend

#### Scenario: Agent without a key
- **WHEN** the backend starts with no key and `HORIZON_AI_PROFILE=agent`
- **THEN** every port except the converter resolves to `scripted`

#### Scenario: Real conversion without a key
- **WHEN** a normal (non-test) backend has no key and conversion is ready, and a PDF is added
- **THEN** the PDF's real text is extracted, and the source ends `keyword_only`

#### Scenario: Deterministic conversion in test mode
- **WHEN** a PDF is added in test mode
- **THEN** it gets placeholder passages without starting any process, as the MockClient does

### Requirement: Scripted placeholders are deterministic
Each port SHALL have a scripted implementation that never calls the network. Given the same session state and seed, it SHALL produce the same output. The scripted turn engine SHALL emit its emotion before its tokens, and stream at the shared timing table's pace. Its spend SHALL be simulated and recorded through the gateway (see `provider-gateway`). The scripted reaction predictor SHALL be asynchronous and called inside the reactions task.

#### Scenario: Same input, same reply
- **WHEN** the same 1:1 exchange is run twice from a factory reset with the clock frozen at the same instant
- **THEN** both runs produce identical message contents and emotions

#### Scenario: Same reactions
- **WHEN** the same scripted group exchange is run twice from a factory reset with the clock frozen at the same instant
- **THEN** both runs emit the same reactions at the same clock times

### Requirement: Agent reply engine
The `agent` turn engine SHALL make one streamed call to the pinned chat model with the same settings rows, caps, stop sequences, held face and empty-reply retry as the naive engine, and send the `agent` request (see `persona-prompt`). Its prompt version SHALL be `agent-2`. It SHALL NOT ask for an emotion tag, and a tag in its output SHALL never change the face. When the turn has a plan, the face SHALL be the plan's, with the plan's source; without a plan (group, watch and debate in M9), the speaker's previous face SHALL be kept with source `default`.

#### Scenario: Face kept
- **WHEN** Amara's face is `thinking` and an unplanned `agent` group reply streams "<e:happy>Sure"
- **THEN** the reply's emotion event is `thinking` with source `default`, and the content is "Sure"

#### Scenario: Face from the plan
- **WHEN** a planned `agent` 1:1 reply's plan chose `sad` from Jev and the model streams "<e:happy>Oh."
- **THEN** the reply's emotion event is `sad` with source `classifier`, and the content is "Oh."

#### Scenario: Context X-ray on agent
- **WHEN** an `agent` 1:1 reply completes
- **THEN** its trace's `context.used.persona` counts the card, `context.used.user` counts the latest user message, and `context.budget` is 11,680
