# ai-ports Specification

## Purpose

Defines the seams between the session runtime and the AI layer: which AI implementations run (scripted, or naive real), what each one receives and may change, the naive DeepSeek reply engine and Jev router shipped in the backend stage, and the at-least-once purge hooks the AI layer can rely on.

## Requirements

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

### Requirement: Scripted placeholders are deterministic
Each port SHALL have a scripted implementation that never calls the network. Given the same session state and seed, it SHALL produce the same output. The scripted turn engine SHALL emit its emotion before its tokens, and stream at the shared timing table's pace. Its spend SHALL be simulated and recorded through the gateway (see `provider-gateway`).

#### Scenario: Same input, same reply
- **WHEN** the same 1:1 exchange is run twice from a factory reset with the clock frozen at the same instant
- **THEN** both runs produce identical message contents and emotions

### Requirement: Naive reply engine
The naive turn engine SHALL make one streamed call to the pinned chat model, with reasoning off and `max_tokens` from the per-mode reply caps. It SHALL order the prompt as:
1. static persona and system prompt (with the You card);
2. the rolling session summary;
3. the history window.

The history window SHALL grow until full, then drop its oldest half in one step, refreshing the summary at that boundary.

#### Scenario: Window drops half at once
- **WHEN** the history window is full and one more message arrives
- **THEN** the next request's history starts from the middle of the previous window, and the rolling summary covers everything before it

#### Scenario: Prefix stays stable between drops
- **WHEN** two consecutive turns happen without a window drop
- **THEN** the second request's messages begin with exactly the first request's messages

### Requirement: Inline emotion tag
The naive engine SHALL ask the model to begin with `<e:label>`. The tag parser SHALL:
- buffer up to 32 characters or until `>`, across chunk boundaries;
- accept only the 7 contract emotions;
- release the text with a `default` emotion (previous face kept) when no valid tag appears;
- strip stray tags anywhere before yielding tokens.

The same rules SHALL pass the shared fixtures in both languages.

#### Scenario: Tag split across chunks
- **WHEN** the stream yields `<e:ha`, then `ppy>Hello`
- **THEN** the engine emits `emotion: happy` and the token text `Hello`, with no tag characters in the content

#### Scenario: Invalid label
- **WHEN** the stream begins `<e:furious>Hi`
- **THEN** the engine emits a `default` emotion, and no tag text reaches the content

### Requirement: Jev router
The naive router SHALL ask one Jev choice question over the eligible cast plus `none`, with the route timeout (400 ms). For a group in `auto`, it SHALL return the selected speaker and a queue of at most 2. On timeout or failure, it SHALL use @mentions, then least-recently-spoken round-robin, mark the fallback, and return no candidates.

#### Scenario: Router timeout
- **WHEN** the Jev call does not answer within 400 ms
- **THEN** the turn proceeds with a round-robin speaker, its trace marks the routing fallback, and the late answer is still recorded in the ledger

### Requirement: Purge hooks are delivered at least once
After a session, character, world or message deletion, or a memory Forget, commits, the backend SHALL queue a purge entry naming the scope and IDs. A worker SHALL call the AI layer's matching hook (the delete hook, or the forget hook for memories) for each entry until it succeeds, and SHALL retry pending entries at startup. The default hooks SHALL do nothing and succeed.

#### Scenario: Retried after a crash
- **WHEN** a session is deleted and the backend stops before the purge hook runs
- **THEN** after restart, the hook is called with scope `session` and the session's ID, and the entry is marked done

#### Scenario: Forget reaches the forget hook
- **WHEN** a memory is forgotten
- **THEN** the forget hook is called with the forgotten memory IDs, their character, and the messages whose traces recalled them

### Requirement: Profile drafter
The profile drafter SHALL turn a seed prompt and intent into a full profile (name, role, adult age, tagline, personality, backstory, speaking style, expertise, boundaries, greeting), appearance attributes and summary, a palette from the shipped palettes, an advisory flag and a song brief, all valid against the contract schema. It SHALL also regenerate one named profile field. The naive drafter SHALL make one structured-output call, labelled `profile`.

#### Scenario: Scripted draft keeps the name
- **WHEN** the scripted drafter drafts "Sarah, a doctor"
- **THEN** the profile name is "Sarah", the role is not empty, the age is at least 18, and the result equals the MockClient's draft for the same seed

#### Scenario: Naive draft is schema-valid
- **WHEN** the naive drafter's provider answer is missing a field or holds an age under 18
- **THEN** the job task fails with a retryable `provider_error`, and the character's profile is unchanged

### Requirement: Image prompt compiler
The image prompt compiler SHALL be the same deterministic code in both profiles. It SHALL build the base-portrait prompt from the style preset, the adult clause and the appearance (with the v2 fixes: the baseline expression, and the base hair colour first); the emotion-edit instruction from the fixed emotion table (no blush on angry); and a tweak edit. It SHALL return no prompt, with a refusal warning, when the character is under 18.

#### Scenario: Golden prompts
- **WHEN** the base prompt and the seven edit instructions are compiled for Hana's appearance
- **THEN** each equals its committed golden fixture, which is the TESTING.md template with the v2 fixes applied

#### Scenario: Angry has no blush
- **WHEN** the angry emotion edit is compiled
- **THEN** the instruction does not mention a flush or blush

### Requirement: Image generator
The image generator SHALL produce one image from a prompt and optional reference images, through the gateway, labelled with an `image_*` purpose. The naive generator SHALL call the configured image model (Seedream 5.0 Flash by default) at 3:4, sending the locked base portrait as the reference for emotion edits, blinks and tweaks. The scripted generator SHALL draw a deterministic placeholder image and never use the network.

#### Scenario: Emotion edit sends the base portrait
- **WHEN** the naive generator makes the happy emotion for a character with a locked base
- **THEN** the provider request carries the base portrait as its only reference image and the compiled edit instruction as its prompt

### Requirement: Song generator
The song generator SHALL turn a brief into a theme song. The brief comes from the profile drafter's draft, or from the user's edit in the job input. The scripted generator SHALL produce the free procedural theme from the brief, identical to the app's own mapping. The naive generator SHALL make one music call to the configured music model (`models.music`, Lyria 3 Clip by default) with an instrumental prompt compiled from the brief, and SHALL return the audio.

#### Scenario: Procedural theme matches the app
- **WHEN** the procedural theme is built for a brief in TypeScript and in Python
- **THEN** both equal the shared fixture

#### Scenario: Naive song prompt comes from the brief
- **WHEN** the naive song generator runs for a brief with genres, moods, a BPM, instruments and a vibe
- **THEN** the provider request names the configured music model, and its prompt states each of those brief values and asks for an instrumental piece with no vocals
