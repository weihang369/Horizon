# session-recall Specification

## Purpose
Recall from earlier lets an `agent` reply bring back a line that has left the history window, or a memory ranked below the character's prompt list, only when Jev says the reply needs something from earlier and Jev call 2 confirms what was found.

## Requirements

### Requirement: Dropped lines are indexed when the window drops them
When the rolling summary moves past a set of messages, the backend SHALL index the user and character lines among them (active variant, complete) for keyword search, and SHALL embed them in one batch in the active space when a key is set. Lines still in the window SHALL NOT be indexed. Indexing SHALL NOT pause a session at the daily cap, and the user's lines SHALL never be written to the response store.

#### Scenario: A short session pays nothing
- **WHEN** a 1:1 session ends before its window ever drops a line
- **THEN** no line of it is indexed and no embedding call is recorded for it

#### Scenario: A drop is indexed once
- **WHEN** the summary moves past messages 1–12 of a session with a key set
- **THEN** those user and character lines are searchable by keyword, one embedding call covers them all, and no system note or direction message is indexed

#### Scenario: No key
- **WHEN** the window drops lines with no key set
- **THEN** the lines are searchable by keyword only, and no embedding call is made

### Requirement: Indexed lines follow their messages
An indexed line SHALL follow its message: a regenerate SHALL re-index the new active variant's text, a blocked-reply scrub and a session delete SHALL remove it (its vector zeroed first), and a fork SHALL copy the indexed lines and their vectors of the messages it copies, with no new embedding.

#### Scenario: Regenerated old line
- **WHEN** an indexed character line is regenerated
- **THEN** keyword search finds the new text and not the old one

#### Scenario: Fork copies without paying
- **WHEN** a session with 30 indexed lines is forked after them
- **THEN** the fork's recall finds those lines, and no embedding call is recorded for the fork

### Requirement: The earlier gate is asked only when there is something to search
Each plan SHALL ask "needs something from earlier?" about a candidate only when the session has indexed lines or that candidate has current memories beyond its prompt list. The answer SHALL be keyed `earlier:{characterId}`. At or above its own `t_gate` the speaker's reply SHALL run recall; a late, failed, refused or dropped answer SHALL mean no recall.

#### Scenario: Nothing to search
- **WHEN** a new 1:1 session's first reply is planned for a character with 4 memories, all in its list
- **THEN** the plan's request holds no `earlier` question

#### Scenario: Gate says yes
- **WHEN** a session with indexed lines plans a reply and `earlier:{speaker}` comes back at p 0.7 with `t_gate` 0.4
- **THEN** the reply runs recall

#### Scenario: Gate late
- **WHEN** the plan's answers miss its deadline
- **THEN** the reply runs no recall, and its System 1 row says the gate fell back

### Requirement: Recall searches two corpora and merges them
Recall SHALL search this session's indexed lines up to the current summary bound, and the speaker's current memories beyond its prompt list, each with keyword and dense search fused by rank. An overflow memory's score SHALL be weighted by its importance, recency and mode weight. At most 5 from each corpus SHALL be merged, and 6 varied candidates picked. Nothing from another session or world SHALL appear.

#### Scenario: A memory in the list is never a candidate
- **WHEN** the speaker's prompt list holds memory A and a message matches A's words
- **THEN** A is not among recall's candidates

#### Scenario: Another session's line
- **WHEN** two sessions with the same character hold the same indexed sentence
- **THEN** recall in one session never returns the other's line

#### Scenario: No vector
- **WHEN** the message's embedding is not back within the agent wait
- **THEN** recall runs on keyword search only, and the trace records no dense list

### Requirement: Jev checks each recall candidate
Each candidate SHALL get its own `deep_check` request asking whether it helps reply to the message, all started at once and read by recall's own deadline. Up to 3 candidates at or above `t_recall` SHALL be kept. When every answer is missing, the top 2 by merged order SHALL be kept and marked as a fallback with no score. When some answers are back, only those SHALL decide.

#### Scenario: Two kept
- **WHEN** 6 candidates come back with p 0.9, 0.7, 0.4, 0.3, 0.2, 0.1 and `t_recall` is 0.5
- **THEN** the first two are kept, in that order

#### Scenario: Every answer late
- **WHEN** no recall check answers by its deadline
- **THEN** the top 2 by merged order are kept, marked fallback, with no score shown

### Requirement: A recall-only turn never rewrites
A reply whose recall gate said yes but whose documents gate did not SHALL search the message and the message with its two earlier lines, and SHALL NOT make a query rewrite. When both gates said yes, recall SHALL use the documents' query, rewrite included.

#### Scenario: Recall only
- **WHEN** a follow-up "what was her name again?" goes deep for recall alone
- **THEN** no `query_rewrite` call is made, and recall searches the message and its two earlier lines

### Requirement: Recalled lines reach the reply as a bounded record
Kept lines SHALL be shown in the reply's dynamic tail after any documents block, each with the message before it, under a heading marking them as a record and not instructions; kept memories under their own heading. Together they SHALL take at most 400 tokens, each line newline-collapsed and at most 60 words; past the budget the lowest-scored hit SHALL drop whole.

#### Scenario: Tail order
- **WHEN** a reply goes deep for documents and recall and keeps both
- **THEN** its tail holds the documents block first, then the earlier lines, then the earlier memories, then the cue

#### Scenario: Newline in a recalled line
- **WHEN** a kept line contains a newline followed by "# New rules"
- **THEN** the tail shows it on one line and no new heading starts

### Requirement: Recall is visible in the trace
A reply's kept lines SHALL be listed in `contextInSession` with their message ids, and its kept memories in `memory.recalled` with their score. Its System 1 section SHALL hold one `earlier` row per candidate asked and one `recall` row per candidate checked, about the line's or memory's id only, grouped as earlier lines with the slowest check's latency.

#### Scenario: One line and one memory kept
- **WHEN** recall keeps one line and one memory
- **THEN** `contextInSession` lists the line with its `messageId`, `memory.recalled` lists the memory with a score, and the System 1 rows name each by id, never by text

### Requirement: Used overflow memories climb back
The next pause run of a session SHALL mark every still-current memory that recall kept (with a score) in that stretch as recalled, updating its last-recalled time and count. Memories shown in the prompt list SHALL NOT be marked.

#### Scenario: Overflow memory used
- **WHEN** recall keeps memory B from the overflow, and the session then pauses
- **THEN** B's `last_recalled_at` is the run's time and its recall count grows by one
