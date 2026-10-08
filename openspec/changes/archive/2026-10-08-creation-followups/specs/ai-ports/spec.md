## MODIFIED Requirements

### Requirement: AI profile selection
`HORIZON_AI_PROFILE` SHALL select `scripted` or `naive` for every AI port. Without it, the profile SHALL be `naive` when a key is set and `scripted` otherwise. A per-port variable (`HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, `HORIZON_AI_DRAFTER`, `HORIZON_AI_IMAGE`, `HORIZON_AI_SONG`, and the others for each port) SHALL override the profile for that port. The turn engine, the router, the profile drafter, the image generator and the song generator have naive implementations; every other port SHALL use its scripted one in both profiles.

#### Scenario: Override one port
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_TURN=scripted`
- **THEN** replies come from the scripted turn engine, and group routing uses the Jev router

#### Scenario: Scripted images under a naive profile
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_IMAGE=scripted`
- **THEN** portrait jobs produce placeholder images with no provider image request, while profile drafts use the naive drafter

#### Scenario: Procedural songs under a naive profile
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_SONG=scripted`
- **THEN** a `song` job produces the procedural theme with no provider music request and no music ledger row

### Requirement: Song generator
The song generator SHALL turn a brief into a theme song. The brief comes from the profile drafter's draft, or from the user's edit in the job input. The scripted generator SHALL produce the free procedural theme from the brief, identical to the app's own mapping. The naive generator SHALL make one music call to the configured music model (`models.music`, Lyria 3 Clip by default) with an instrumental prompt compiled from the brief, and SHALL return the audio.

#### Scenario: Procedural theme matches the app
- **WHEN** the procedural theme is built for a brief in TypeScript and in Python
- **THEN** both equal the shared fixture

#### Scenario: Naive song prompt comes from the brief
- **WHEN** the naive song generator runs for a brief with genres, moods, a BPM, instruments and a vibe
- **THEN** the provider request names the configured music model, and its prompt states each of those brief values and asks for an instrumental piece with no vocals
