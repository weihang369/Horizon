# event-streams Specification

## Purpose

Defines the backend's two Server-Sent Event streams: the global stream that announces changes, resets and job progress, and the per-session stream that replays a session's stored events and resumes without gaps or duplicates.

## Requirements

### Requirement: Global stream
`GET /api/v1/events` SHALL be an SSE stream of `GlobalEvent` payloads, one JSON object per `data:` line. It SHALL send a keepalive comment at least every 15 seconds. Responses SHALL carry `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Global events SHALL NOT be stored or replayed.

#### Scenario: Keepalive
- **WHEN** a client holds the global stream open for 20 seconds with no activity
- **THEN** it receives at least one keepalive comment, and the connection stays open

### Requirement: Changes are announced
After a write commits, the backend SHALL publish:
- `entity.changed { kind: "world", id, worldId }` when a world is created, renamed, deleted or gets a new cover;
- `entity.changed { kind: "settings" }` when settings or the key are changed, or when the key status changes;
- `entity.changed { kind: "character", id, worldId }` when a character is created, edited, approved, archived, restored or deleted, when its portrait is locked or an asset version is accepted, when a job changes its profile, assets, song or `activeJobId`, and when its energy is written (top-up, set-max, a reply drain or an energy correction);
- `entity.changed { kind: "job", id }` when a job is created or changes;
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

#### Scenario: Character deleted
- **WHEN** a global subscriber is connected and `chr_seedVictor` is deleted
- **THEN** the subscriber receives `entity.changed` with `kind: "character"` and `id: "chr_seedVictor"`

### Requirement: Slow subscribers are dropped
Each subscriber SHALL have a bounded queue of 1,000 events. A subscriber whose queue overflows SHALL have its stream closed, and other subscribers SHALL be unaffected.

#### Scenario: Stalled reader
- **WHEN** one subscriber stops reading while more than 1,000 events are published
- **THEN** that subscriber's stream is closed, and another subscriber receives every event

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

### Requirement: Budget events on the global stream
The global stream SHALL carry `budget.warning { scope, spentUsd, capUsd }` when spend crosses a warning line, and `budget.reached { scope, spentUsd, capUsd, sessionId?, jobId? }` when a paid call is refused by a cap (see `budget-caps`). Each SHALL validate as a `GlobalEvent`.

#### Scenario: Warning delivered
- **WHEN** a recorded call moves daily spend across 80 % of the cap while a global subscriber is connected
- **THEN** the subscriber receives one `budget.warning` with `scope: "daily"`

### Requirement: Budget warning reaches the live session
When a recorded call crosses the daily warning line, the backend SHALL also emit a stored `budget.warning` event on the stream of the session that made the call, besides the global event.

#### Scenario: Warning inside a session
- **WHEN** a live reply's ledger row moves daily spend across 80 % of the cap
- **THEN** that session's stream carries a `budget.warning` event with `scope: "daily"`, and the global stream carries one too

### Requirement: Job events are mirrored on the global stream
`job.progress`, `task.update` (with `previewUrl` when a preview exists) and `job.done` SHALL be published on the global stream. A job subscription SHALL be served as a snapshot of the job followed by the global stream filtered by its `jobId`, so the browser keeps at most two event streams open.

#### Scenario: Task update over the global stream
- **WHEN** a global subscriber is connected and a portrait job runs
- **THEN** it receives `task.update` events carrying that job's ID, each valid against the contract schema
