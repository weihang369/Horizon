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
- `entity.changed { kind: "world", id, worldId }` when a world is created, renamed or deleted;
- `entity.changed { kind: "settings" }` when settings or the key are changed, or when the key status changes;
- `entity.changed { kind: "character", id, worldId }` when a character's energy is written (top-up, set-max, a reply drain or an energy correction);
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

### Requirement: Slow subscribers are dropped
Each subscriber SHALL have a bounded queue of 1,000 events. A subscriber whose queue overflows SHALL have its stream closed, and other subscribers SHALL be unaffected.

#### Scenario: Stalled reader
- **WHEN** one subscriber stops reading while more than 1,000 events are published
- **THEN** that subscriber's stream is closed, and another subscriber receives every event

### Requirement: Session stream replay and resume
`GET /api/v1/sessions/{id}/stream` SHALL be an SSE stream:
- each event has `id:` set to the event `seq`, `event:` set to its type, and `data:` set to the whole `SessionEvent` (`{ id, sessionId, seq, at, type, payload }`);
- the stream starts after `max(sinceSeq, Last-Event-ID)`;
- it delivers stored events above that point in `seq` order with no gaps or duplicates, then stays open for live events.

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

### Requirement: Budget events on the global stream
The global stream SHALL carry `budget.warning { scope, spentUsd, capUsd }` when spend crosses a warning line, and `budget.reached { scope, spentUsd, capUsd, sessionId?, jobId? }` when a paid call is refused by a cap (see `budget-caps`). Each SHALL validate as a `GlobalEvent`.

#### Scenario: Warning delivered
- **WHEN** a recorded call moves daily spend across 80 % of the cap while a global subscriber is connected
- **THEN** the subscriber receives one `budget.warning` with `scope: "daily"`
