## MODIFIED Requirements

### Requirement: AI profile selection
`HORIZON_AI_PROFILE` SHALL select `scripted` or `naive` for every AI port. Without it, the profile SHALL be `naive` when a key is set and `scripted` otherwise. A per-port variable (`HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, `HORIZON_AI_DRAFTER`, `HORIZON_AI_IMAGE`, and the others for each port) SHALL override the profile for that port. The turn engine, the router, the profile drafter and the image generator have naive implementations; every other port SHALL use its scripted one in both profiles.

#### Scenario: Override one port
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_TURN=scripted`
- **THEN** replies come from the scripted turn engine, and group routing uses the Jev router

#### Scenario: Scripted images under a naive profile
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_IMAGE=scripted`
- **THEN** portrait jobs produce placeholder images with no provider image request, while profile drafts use the naive drafter

## ADDED Requirements

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
The song generator SHALL turn a brief into a theme song. While the provider lists no music model, it SHALL produce the free procedural theme from the brief, identical to the app's own mapping, in both profiles. The brief comes from the profile drafter's draft, or from the user's edit in the job input.

#### Scenario: Procedural theme matches the app
- **WHEN** the procedural theme is built for a brief in TypeScript and in Python
- **THEN** both equal the shared fixture
