# system1-trace Specification

## Purpose

The System 1 trace records every Jev question behind a character turn (its answer, probability, the comparisons code made, and what code did) and shows it in Insight. It is the product's "see the AI think" view of System 1.

## Requirements

### Requirement: One row per question asked
A turn's trace SHALL carry an optional `system1` section: an optional `seed`, and at most 64 question rows. Each row SHALL hold:
- the purpose;
- the bank id, version and label;
- an optional `about` (an ID only, never text);
- the answer;
- an optional `p` and `confidence`;
- the comparisons made, each `{name, value, threshold}`;
- the result: `used`, `below_threshold`, `fallback`, `not_used` or `shown_only`;
- an optional `action`.

A fallback row SHALL have no `p`.

#### Scenario: Fallback row
- **WHEN** the route decision times out
- **THEN** the reply's `system1` has a `route` row with `result: "fallback"`, an answer naming what the fallback did, and no `p`

### Requirement: Only the runtime writes the section
The `system1` section SHALL be written only by the runtime. A trace patch from an AI port that sets it SHALL be dropped, and the rest of the patch kept.

#### Scenario: Engine patch rejected
- **WHEN** a turn engine emits a trace patch with `system1` and `context`
- **THEN** the stored trace keeps the runtime's `system1` and the engine's `context`

### Requirement: Rows appended after the turn
The runtime SHALL add rows to a finished message through one operation that runs inside the session's single writer. The operation SHALL:
- read the message's current trace;
- drop the rows if the message's active variant has changed;
- merge rows by `(purpose, id, about)`, so a later row replaces an earlier one;
- append the new paid calls;
- emit the full trace as `insight`, keeping the stored engine metadata and creation time.

#### Scenario: After Regenerate
- **WHEN** rows are appended for variant A after the user regenerated the message to variant B
- **THEN** nothing is written, and the stored trace is unchanged

#### Scenario: Merge by key
- **WHEN** a row `(face_check, face, —)` is appended twice with different answers
- **THEN** the trace holds one such row, with the second answer

#### Scenario: Engine metadata kept
- **WHEN** an `insight` is appended to a message whose trace was written by engine `naive` version 2
- **THEN** the stored trace row still names engine `naive` version 2 and its original creation time

### Requirement: Appends to a streaming reply wait for its end
When the target message is still streaming, appended rows SHALL be merged into its in-progress trace without emitting anything. The turn's final trace SHALL merge them by key rather than replace them.

#### Scenario: Rows land mid-stream
- **WHEN** rows are appended while their target reply is streaming
- **THEN** no `insight` is emitted before `turn.end`, and the final `insight` includes the rows

### Requirement: Appends never restore forgotten memories
In the same transaction as the append, any recalled-memory entry and any `system1` row whose `about` names a memory that no longer exists SHALL be removed from the trace before it is stored.

#### Scenario: Forget between queue and write
- **WHEN** a memory is forgotten after an append naming it was queued, but before the append is written
- **THEN** the stored trace has no row about that memory, and no recalled entry with its text

### Requirement: The row limit
A trace SHALL be cut to 64 rows before it is sent, removing `not_used` rows first.

#### Scenario: Too many rows
- **WHEN** a turn produces 70 rows, 10 of them `not_used`
- **THEN** the emitted trace has 64 rows, and 4 `not_used` rows remain

### Requirement: Route rows
Every reply started by a routing decision SHALL carry one `route` row. With Jev, the row SHALL hold the picked participant's ID (or `none`), its probability and the confidence, with result `used`. On a fallback, the result SHALL be `fallback`. The scripted profile and the MockClient SHALL take the row's fixed fields from the shared System 1 fixture, and fill the answer from the actual routing.

#### Scenario: Two replies from one decision
- **WHEN** a group message gets replies from Hana and then Rin under one routing decision
- **THEN** both replies' traces carry the same `route` row

#### Scenario: Scripted group turn
- **WHEN** a scripted group turn is answered by Mei
- **THEN** its trace's `route` row has the fixture's label and `p`, and the answer is Mei's ID

### Requirement: The Insight section
The Insight drawer SHALL show a "System 1 · Jev" section after Emotion:
- rows grouped by purpose, each group headed by its latency or "fallback";
- each row with its label, answer, `p` or confidence and its band, comparisons as "value ≥ threshold", and the action;
- `not_used` rows folded under "asked about the others (n)";
- IDs resolved to names or titles.

The section SHALL be hidden when there are no rows, and absent in Compact mode.

#### Scenario: No rows
- **WHEN** a 1:1 scripted reply's Insight is opened
- **THEN** no System 1 section shows

#### Scenario: Route row shown
- **WHEN** a naive group reply's Insight is opened
- **THEN** the System 1 section shows "who replies?" with the speaker's name and `p` with its band
