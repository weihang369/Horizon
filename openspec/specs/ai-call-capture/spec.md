# ai-call-capture Specification

## Purpose

AI call capture keeps the full requests and responses of AI calls on the user's machine for debugging and replay, off by default, without slowing any call, and without letting forgotten or deleted text survive.

## Requirements

### Requirement: Off unless switched on
Capture SHALL run only when `HORIZON_CAPTURE_AI_CALLS=1`. While it is on, the backend SHALL log one line at start-up saying so. While it is off, no request or response body SHALL be stored anywhere.

#### Scenario: Default
- **WHEN** a reply completes with capture off
- **THEN** the `ai_calls` table has no rows

### Requirement: One row per provider call and one per turn
With capture on, every call that reaches the provider, failures included, SHALL produce one row. The row SHALL hold:
- purpose, model, latency, cost and the ledger row ID;
- the world, session, character and message IDs;
- the redacted request (the messages, or Jev's state and questions);
- the response.

Each turn SHALL also produce one row holding its frozen context and its fallback flags. Embedding texts and vectors, and image and audio bytes, SHALL never be stored.

#### Scenario: Group turn captured
- **WHEN** a naive group reply completes with capture on
- **THEN** there is a row for the `route` call with Jev's state and answers, a row for the `reply` call with its messages and text, and one turn row, all with the message ID

#### Scenario: Embedding row has no text
- **WHEN** a query embedding is captured
- **THEN** its row has no input texts and no vector

### Requirement: Capture never delays a call
Capture SHALL only queue rows in memory during a call. A background writer SHALL store them in batches. Rows dropped because the queue was full SHALL be counted and logged.

#### Scenario: Full queue
- **WHEN** 2,500 calls are captured faster than the writer stores them
- **THEN** every call completes normally, and the number of dropped rows is logged and recorded on the next stored row

### Requirement: Retention
At start-up and every hour, rows older than 7 days SHALL be deleted, and then all but the newest 20,000 rows.

#### Scenario: Old rows
- **WHEN** the backend starts with rows from 8 days ago
- **THEN** those rows are deleted

### Requirement: Deletes follow the data
Deleting a session or world SHALL delete its rows in the same transaction. Deleting a character SHALL delete its rows through the purge hooks, and a repeat delivery SHALL be harmless. Factory reset SHALL delete every row.

#### Scenario: Character deleted
- **WHEN** a character with captured rows is deleted and the purge hook runs twice
- **THEN** none of that character's rows remain, and the second run succeeds

### Requirement: Replayable case from a captured turn
`horizon eval capture <messageId>` SHALL write that message's captured rows as one case file under `data/evals/cases/`. With no captured rows, it SHALL exit non-zero and say that capture was off for that message.

#### Scenario: Not captured
- **WHEN** `horizon eval capture` is run for a message produced with capture off
- **THEN** it exits non-zero, and no case file is written
