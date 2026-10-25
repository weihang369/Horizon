## MODIFIED Requirements

### Requirement: Changes are announced
After a write commits, the backend SHALL publish:
- `entity.changed { kind: "world", id, worldId }` when a world is created, renamed, deleted or gets a new cover;
- `entity.changed { kind: "settings" }` when settings or the key are changed, or when the key status changes;
- `entity.changed { kind: "character", id, worldId }` when a character is created, edited, approved, archived, restored or deleted, when its portrait is locked or an asset version is accepted, when a job changes its profile, assets, song or `activeJobId`, and when its energy is written (top-up, set-max, a reply drain or an energy correction);
- `entity.changed { kind: "job", id }` when a job is created or changes;
- `entity.changed { kind: "session", id, worldId }` when a session is created, forked, renamed, deleted, paused, resumed or ended, or gains a message;
- `entity.changed { kind: "usage" }` when a ledger row is written;
- `entity.changed { kind: "knowledge", id, worldId }` when a knowledge source is added, deleted or re-indexed, at each indexing stage (with `progress`), and when it reaches its end status (without `progress`);
- `entity.changed { kind: "memory", id: characterId, worldId }` when a character's memories are written or forgotten;
- `mock.reset` after a demo-data reset.

An event SHALL NOT be published for a write that failed.

#### Scenario: World created
- **WHEN** a global subscriber is connected and a world is created
- **THEN** the subscriber receives `entity.changed` with `kind: "world"` and the new world's ID

#### Scenario: Reset announced
- **WHEN** demo data is reset
- **THEN** every connected global subscriber receives `{ "type": "mock.reset" }`

#### Scenario: Top-up announced
- **WHEN** a global subscriber is connected and a top-up succeeds for `chr_seedHana`
- **THEN** the subscriber receives `entity.changed` with `kind: "character"` and `id: "chr_seedHana"`

#### Scenario: Refused top-up is silent
- **WHEN** a top-up is refused by the gate
- **THEN** no `entity.changed` is published for it

#### Scenario: Session created
- **WHEN** a global subscriber is connected and a 1:1 session is created in `wld_seedMeridian`
- **THEN** the subscriber receives `entity.changed` with `kind: "session"`, the new session's ID and `worldId: "wld_seedMeridian"`

#### Scenario: Character deleted
- **WHEN** a global subscriber is connected and `chr_seedVictor` is deleted
- **THEN** the subscriber receives `entity.changed` with `kind: "character"` and `id: "chr_seedVictor"`

#### Scenario: Source indexed
- **WHEN** a global subscriber is connected and a source is added to `chr_seedHana`
- **THEN** the subscriber receives `entity.changed` with `kind: "knowledge"` and the source's ID, then progress events, then one final event without `progress`

#### Scenario: Memory forgotten
- **WHEN** a global subscriber is connected and one of Hana's memories is forgotten
- **THEN** the subscriber receives `entity.changed` with `kind: "memory"`, `id: "chr_seedHana"` and Hana's world

#### Scenario: Refused upload is silent
- **WHEN** a knowledge upload is rejected with `validation`
- **THEN** no `entity.changed` with `kind: "knowledge"` is published for it
