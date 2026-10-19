## MODIFIED Requirements

### Requirement: AI profile selection
`HORIZON_AI_PROFILE` SHALL select `scripted`, `naive` or `agent` for every AI port. Without it, the profile SHALL be `agent` when a key is set and `scripted` otherwise (from M15; before M15 it was `naive`). A per-port variable (`HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, `HORIZON_AI_DRAFTER`, `HORIZON_AI_IMAGE`, `HORIZON_AI_SONG`, `HORIZON_AI_EMBEDDER`, `HORIZON_AI_KNOWLEDGE_RETRIEVER`, `HORIZON_AI_MEMORY_RETRIEVER`, `HORIZON_AI_CONVERTER`, `HORIZON_AI_SUMMARISER`, `HORIZON_AI_PLANNER`, `HORIZON_AI_FACE_CHECK`, `HORIZON_AI_GUARDRAIL`, and the others for each port) SHALL override the profile for that port. The turn engine, the router, the summariser, the profile drafter, the image generator, the song generator, the embedder and the memory and knowledge retrievers have naive implementations; the planner, the face check and the guardrail have a naive implementation that does nothing (the guardrail passes with no checks); every other port SHALL use its scripted one under `naive`. Under `agent`, each port SHALL use its agent implementation when one exists (from M8, the turn engine; from M9, the planner, the reaction predictor and the face check; from M14, the guardrail), else its naive one when one exists, else its scripted one; without a key every port SHALL be scripted. The scripted planner, face check and reaction predictor SHALL record simulated spend only when the profile is `scripted` or no key is set, never when they stand in for a missing naive implementation while a key is set. The memory writer SHALL follow `long-term-memory`'s writers per profile. The document converter SHALL NOT depend on the key: it SHALL convert real documents unless overridden, and in test mode it SHALL default to a deterministic converter that never starts a process. The start-up log SHALL name the profile in use and how to select the `naive` baseline.

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

#### Scenario: The default with a key is agent
- **WHEN** the backend starts with a key and no `HORIZON_AI_PROFILE` or per-port variable
- **THEN** every port resolves exactly as it does with `HORIZON_AI_PROFILE=agent`, and the start-up log says the profile is `agent` and that `HORIZON_AI_PROFILE=naive` selects the baseline

#### Scenario: The default without a key is scripted
- **WHEN** the backend starts with no key and no `HORIZON_AI_PROFILE`
- **THEN** every port except the converter resolves to `scripted`, and scripted ports may record simulated spend

#### Scenario: The memory writer follows the default
- **WHEN** a test-mode backend has a key and no profile variable
- **THEN** the memory writer is the `agent` writer, answered by the fake's canned Jev answers

#### Scenario: Real conversion without a key
- **WHEN** a normal (non-test) backend has no key and conversion is ready, and a PDF is added
- **THEN** the PDF's real text is extracted, and the source ends `keyword_only`

#### Scenario: Deterministic conversion in test mode
- **WHEN** a PDF is added in test mode
- **THEN** it gets placeholder passages without starting any process, as the MockClient does

### Requirement: Image prompt compiler
The image prompt compiler SHALL be the same deterministic code in both profiles, at prompt version v3 (doc 12 I1). It SHALL build the base-portrait prompt from the style preset, the adult clause and the appearance (with the v2 fixes: the baseline expression, and the base hair colour first); the emotion-edit instruction from the fixed emotion table (no blush on angry); a tweak edit; and the expression sheet. v3 adds, in exact wording: the original-character line and "Fully clothed in the outfit described." in the base and the sheet; "childlike or teenage features" in the sheet's Avoid line; and the apparent-age line in emotion edits and tweaks. It SHALL return no prompt, with a refusal warning, when the character is under 18.

#### Scenario: Golden prompts
- **WHEN** the base prompt, the seven edit instructions, the identity edit, the tweak and the sheet are compiled for each of the four fixture characters
- **THEN** each equals its committed golden fixture, which records version `v3`

#### Scenario: Angry has no blush
- **WHEN** the angry emotion edit is compiled
- **THEN** the instruction does not mention a flush or blush

#### Scenario: Original and clothed
- **WHEN** a base portrait or a sheet is compiled
- **THEN** the prompt contains "An original character design, not based on any real person or existing character." after the style and adult lines, and its Outfit line ends "Fully clothed in the outfit described."

#### Scenario: The sheet's Avoid line
- **WHEN** a sheet is compiled
- **THEN** its Avoid line contains "childlike or teenage features"

#### Scenario: Edits keep the apparent age
- **WHEN** an emotion edit or a tweak is compiled
- **THEN** its Keep line ends "Keep the character's apparent adult age exactly as in the original.", and a tweak has no originality line

#### Scenario: The name never appears
- **WHEN** every template is compiled for each seed character
- **THEN** no prompt contains the character's name or any word of it

#### Scenario: Positive wording only
- **WHEN** every template is compiled
- **THEN** no prompt contains "nudity", "underwear", "swimwear", "blood" or "weapon"

### Requirement: Song generator
The song generator SHALL turn a brief into a theme song. The brief comes from the profile drafter's draft, or from the user's edit in the job input. The scripted generator SHALL produce the free procedural theme from the brief, identical to the app's own mapping. The naive generator SHALL make one music call to the configured music model (`models.music`, Lyria 3 Clip by default) with an instrumental prompt compiled from the brief alone (doc 12 I2): it SHALL open "Instrumental theme music for a character.", state each set brief value, and say "An original piece: do not imitate any named artist, band or existing song." before "No vocals, no lyrics.". The prompt SHALL NOT contain the theme's title or the character's name. It SHALL return the audio.

#### Scenario: Procedural theme matches the app
- **WHEN** the procedural theme is built for a brief in TypeScript and in Python
- **THEN** both equal the shared fixture

#### Scenario: Naive song prompt comes from the brief
- **WHEN** the naive song generator runs for a brief with genres, moods, a BPM, instruments and a vibe
- **THEN** the provider request names the configured music model, and its prompt states each of those brief values and asks for an instrumental piece with no vocals

#### Scenario: No name in the song prompt
- **WHEN** a song job runs for "Taylor" with the stored title "Taylor's Theme"
- **THEN** the provider prompt contains neither "Taylor" nor the title, ends with the original-piece line followed by "No vocals, no lyrics. A 30-second piece that loops cleanly.", the song's provenance prompt equals the text sent, and the procedural theme is still built with the title

#### Scenario: The brief check reads what is sent
- **WHEN** an `agent` song task checks its brief before the music call
- **THEN** the text checked equals the prompt the provider receives

### Requirement: Agent reply engine
The `agent` turn engine SHALL make one streamed call to the pinned chat model with the same settings rows, caps, stop sequences, held face and empty-reply retry as the naive engine, and send the `agent` request (see `persona-prompt`). Its prompt version SHALL follow the bytes sent. From M15 (the reworded honesty line): `agent-9`; `agent-11` with a "second" or "next" turn-cue sentence; `agent-13` with the steer sentence; `agent-15` for a debate argument with the debate cue; and one higher (`agent-10`, `-12`, `-14`, `-16`) with the mood line on. Before M15 the same eight were `agent-1` to `agent-8`. It SHALL NOT ask for an emotion tag, and a tag in its output SHALL never change the face. When the turn has a plan, the face SHALL be the plan's, with the plan's source; without a plan, the speaker's previous face SHALL be kept with source `default`.

#### Scenario: Face kept
- **WHEN** Amara's face is `thinking` and an unplanned `agent` reply (its plan fell back with no face) streams "<e:happy>Sure"
- **THEN** the reply's emotion event is `thinking` with source `default`, and the content is "Sure"

#### Scenario: Face from the plan
- **WHEN** a planned `agent` 1:1 reply's plan chose `sad` from Jev and the model streams "<e:happy>Oh."
- **THEN** the reply's emotion event is `sad` with source `classifier`, and the content is "Oh."

#### Scenario: Context X-ray on agent
- **WHEN** an `agent` 1:1 reply completes
- **THEN** its trace's `context.used.persona` counts the card, `context.used.user` counts the latest user message, and `context.budget` is 11,680

#### Scenario: Label follows the bytes
- **WHEN** an `agent` group's first reply and its follow-plan second reply are sent with the mood line off
- **THEN** the first request's prompt version is `agent-9` and the second's is `agent-11`

#### Scenario: Steer and debate labels
- **WHEN** a watch turn steers and an `agent` rebuttal is generated, both with the mood line off
- **THEN** their prompt versions are `agent-13` and `agent-15`

## ADDED Requirements

### Requirement: A reply reads the key once
Every port a reply uses SHALL be resolved from the key status read once when the reply's turn starts. That covers its plan, reply engine, reactions, face check and output check, and the after-the-fact check of an interrupted reply. A key cleared during the turn SHALL make the turn's later provider calls fail on the existing missing-key path. It SHALL NOT switch any of them to another profile. Work outside the reply (the follow plan, the next turn, a prefetch, the debate plan, a pause run) SHALL read the key at its own start.

#### Scenario: Key cleared while the plan is in flight
- **WHEN** an `agent` 1:1 turn's Jev call 1 is held, the key is cleared, and the call is released
- **THEN** the reply ends `error` on the missing-key path, no scripted text is stored, and the trace holds no scripted guardrail row

#### Scenario: Key set during a keyless turn
- **WHEN** a turn starts with no key and the key is set before its reply streams
- **THEN** that reply stays scripted, and the next turn resolves to `agent`

### Requirement: The naive tag line allows no notes
The `naive` reply prompt SHALL tell the model to write the emotion tag on its own, like `<e:thinking>`, with nothing inside it and no closing tag. The line reaches every `naive` request, so each label moves by 4: `naive-9` (a reply), `naive-10` (a debate request), `naive-11` and `naive-12` (the same with sliced passages). The user chose the fix (design D14).

#### Scenario: The tag line
- **WHEN** a `naive` reply request is built
- **THEN** its system message says to write only the tag itself with nothing inside it and no closing tag, and its prompt version is `naive-9` (`naive-10` in a debate)
