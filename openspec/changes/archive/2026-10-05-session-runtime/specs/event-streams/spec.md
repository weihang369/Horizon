# Spec Delta

## MODIFIED Requirements

### Requirement: Changes are announced
After a write commits, the backend SHALL publish:
- `entity.changed { kind: "world", id, worldId }` when a world is created, renamed or deleted;
- `entity.changed { kind: "settings" }` when settings or the key are changed, or when the key status changes;
- `entity.changed { kind: "character", id, worldId }` when a character's energy is written (top-up, set-max, a reply drain or an energy correction);
- `entity.changed { kind: "session", id, worldId }` when a session is created, forked, renamed, deleted, paused, resumed or ended, or gains a message;
- `entity.changed { kind: "usage" }` when a ledger row is written;
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

### Requirement: Session stream replay and resume
`GET /api/v1/sessions/{id}/stream` SHALL be an SSE stream:
- each event has `id:` set to the event `seq`, `event:` set to its type, and `data:` set to the whole `SessionEvent` (`{ id, sessionId, seq, at, type, payload }`);
- the stream starts after `max(sinceSeq, Last-Event-ID)`;
- it delivers stored events above that point in `seq` order with no gaps or duplicates;
- it then stays open and delivers every live event in `seq` order, with none lost or repeated, including events committed while the stored ones were being replayed.

An unknown session SHALL be rejected with 404 before the stream opens.

#### Scenario: Resume from a query parameter
- **WHEN** a seed session's stream is opened with `sinceSeq=3`
- **THEN** exactly the stored events with `seq > 3` arrive, in order

#### Scenario: Last-Event-ID wins when higher
- **WHEN** the stream is reopened with `sinceSeq=3` and `Last-Event-ID: 40`
- **THEN** the first event delivered has `seq 41`

#### Scenario: Unknown session
- **WHEN** `GET /sessions/ses_nope/stream` is requested
- **THEN** the response is 404 with the error envelope, not an event stream

#### Scenario: Live events during replay
- **WHEN** a client opens the stream of a live session with `sinceSeq=0` while a reply is streaming
- **THEN** it receives every stored and live event exactly once, with consecutive `seq` values

#### Scenario: Reconnect mid-reply
- **WHEN** a client's stream drops after `seq` 30 during a streaming reply and reconnects with `Last-Event-ID: 30`
- **THEN** the next event it receives has `seq` 31, and the reply's text it assembles equals the stored message's content

## ADDED Requirements

### Requirement: Budget warning reaches the live session
When a recorded call crosses the daily warning line, the backend SHALL also emit a stored `budget.warning` event on the stream of the session that made the call, besides the global event.

#### Scenario: Warning inside a session
- **WHEN** a live reply's ledger row moves daily spend across 80 % of the cap
- **THEN** that session's stream carries a `budget.warning` event with `scope: "daily"`, and the global stream carries one too
