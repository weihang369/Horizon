# ai-ports Specification

## Purpose

Defines the seams between the session runtime and the AI layer: which AI implementations run (scripted, or naive real), what each one receives and may change, the naive DeepSeek reply engine and Jev router shipped in the backend stage, and the at-least-once purge hooks the AI layer can rely on.

## Requirements

### Requirement: AI profile selection
`HORIZON_AI_PROFILE` SHALL select `scripted` or `naive` for every AI port. Without it, the profile SHALL be `naive` when a key is set and `scripted` otherwise. A per-port variable (`HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, and the others for each port) SHALL override the profile for that port. In this milestone, only the turn engine and the router have naive implementations; every other port SHALL use its scripted one in both profiles.

#### Scenario: Override one port
- **WHEN** the backend starts with `HORIZON_AI_PROFILE=naive` and `HORIZON_AI_TURN=scripted`
- **THEN** replies come from the scripted turn engine, and group routing uses the Jev router

### Requirement: Ports see frozen, scoped context
Every AI port SHALL receive an immutable, JSON-serialisable context: the session, its participants with their energy, recent messages (active variants only), the latest rolling summary, mode config and state, and the world and character scope. A port SHALL reach the provider only through the gateway, with calls labelled by purpose. A port SHALL NOT read or write session rows directly.

#### Scenario: Context round-trips through JSON
- **WHEN** a turn context is serialised to JSON and parsed back
- **THEN** the result equals the original, so an evaluation harness can build contexts from fixtures

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
After a session, character, world or message deletion commits, the backend SHALL queue a purge entry naming the scope and IDs. A worker SHALL call the AI layer's purge hook for each entry until it succeeds, and SHALL retry pending entries at startup. The default hook SHALL do nothing and succeed.

#### Scenario: Retried after a crash
- **WHEN** a session is deleted and the backend stops before the purge hook runs
- **THEN** after restart, the hook is called with scope `session` and the session's ID, and the entry is marked done
