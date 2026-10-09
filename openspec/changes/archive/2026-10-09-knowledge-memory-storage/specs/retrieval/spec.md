## Purpose

Defines how a turn finds the speaker's relevant memories and knowledge passages within the speaker's own scope, how a user message is embedded once for that, and how replies cite what they used (D-59, D-64, NFR-23).

## ADDED Requirements

### Requirement: One query embedding per user message, only when useful
When a 1:1 or group message is sent, the backend SHALL embed its text at most once, starting in parallel with routing, and reuse the result for every reply to that message. It SHALL do so only when knowledge retrieval uses vectors, a key is set, and at least one possible responder has vectors. Debate and watch turns SHALL NOT embed a query.

#### Scenario: Group message to three characters
- **WHEN** a group message gets three replies and two of the characters have indexed knowledge
- **THEN** exactly one `embedding` ledger row with purpose `query_embed` exists for that message

#### Scenario: Nobody has vectors
- **WHEN** a 1:1 message is sent to a character with only keyword-only sources and no memory vectors
- **THEN** no `query_embed` row is written

#### Scenario: Scripted profile
- **WHEN** the scripted profile answers a message to a character with indexed knowledge
- **THEN** no `query_embed` row is written

### Requirement: Retrieval never waits long for the query vector
A reply SHALL wait for the query vector at most a configured time (default 400 ms). If it isn't ready, the reply SHALL use keyword retrieval only. A query embedding refused by a cap or failed by the provider SHALL fall back the same way, without an error event.

#### Scenario: Slow embedding
- **WHEN** the query embedding takes longer than the wait limit
- **THEN** the reply starts with keyword-only retrieval, and the late embedding is still recorded in the ledger

#### Scenario: Cap reached
- **WHEN** today's cap refuses the query embedding
- **THEN** the reply still runs with keyword-only retrieval, and no `error` event is emitted for the embedding

### Requirement: Retrieval stays in the speaker's scope
Memory recall and knowledge retrieval for a reply SHALL be bound to the speaker's world and character by the backend, not by the AI engine. Every keyword and vector hit SHALL be re-checked against that world and character. No hit from another character or world SHALL reach the engine.

#### Scenario: Identical knowledge in two worlds
- **WHEN** two worlds hold characters with identical knowledge text and vectors, and one of them is asked about it
- **THEN** every retrieved passage belongs to that character in that world

### Requirement: User text cannot change the keyword query
Text taken from messages SHALL be turned into a keyword query that matches its words only. Quotes, operators, column names and unbalanced punctuation in the text SHALL NOT cause an error or change how the search works.

#### Scenario: Message full of syntax
- **WHEN** a user sends `"burnout" NEAR(review -triage) text: OR AND (`
- **THEN** the reply runs normally, and retrieval matches on the words burnout, review, triage and text

### Requirement: Knowledge retrieval
The scripted knowledge retriever SHALL rank passages by keyword relevance. The naive one SHALL fuse keyword and vector rankings, using vectors only from the active space. Both SHALL return at most a configured number of passages (default 5), each with a score between 0 and 1. Keyword-only sources SHALL take part through keyword ranking.

#### Scenario: Keyword-only seed knowledge is still found
- **WHEN** Amara's seed sources are keyword-only and a message asks about burnout
- **THEN** her passages mentioning burnout are retrieved

#### Scenario: Meaning match
- **WHEN** with the naive profile a message shares no words with a passage whose vector is its nearest neighbour
- **THEN** that passage is retrieved

### Requirement: Memory recall
The scripted memory retriever SHALL return the character's most recent current memories. The naive one SHALL return the current memories that best match the message by keyword. Both SHALL return at most a configured number (default 3), and never a superseded or forgotten memory.

#### Scenario: Superseded memory never recalled
- **WHEN** memory A was superseded by memory B and a message matches A's words
- **THEN** A is not recalled

### Requirement: Engines receive retrieved hits in the turn context
The turn context SHALL carry the retrieved passages (with source title, locator, passage text and section text) and recalled memories as plain data, so that it still round-trips through JSON. Engines SHALL NOT query storage themselves.

#### Scenario: Context with hits round-trips
- **WHEN** a turn context with retrieved passages and memories is serialised to JSON and parsed back
- **THEN** the result equals the original

### Requirement: Scripted replies cite knowledge like the mock
When passages are retrieved, about half of the scripted replies SHALL cite one or two of them with `[n]` markers in the streamed text. One more passage SHALL be listed as retrieved but not cited. Replies of characters without hits SHALL be unchanged from M4.

#### Scenario: Live citations
- **WHEN** with a key set Amara is asked "What does the review say about burnout?" up to eight times
- **THEN** at least one reply carries citations whose markers appear in its content, `trace.knowledge.retrieved` lists both cited and uncited passages, and `trace.context.used.knowledge` is above 0

#### Scenario: Unchanged without knowledge
- **WHEN** the same scripted 1:1 exchange runs with a character that has no knowledge or memories
- **THEN** its message contents and emotions equal those produced before this change

### Requirement: Naive replies can use and cite what was retrieved
When passages or memories are retrieved, the naive reply engine SHALL add them after the conversation history, numbered for citation, and SHALL report in the trace which passages its reply cited and which memories it was given. With nothing retrieved, its request SHALL be the same as before.

#### Scenario: Cited passage
- **WHEN** with the naive profile a reply uses passage 2 and writes `[2]`
- **THEN** `turn.end.citations` holds that passage, and `trace.knowledge.retrieved` marks it cited and the others not cited

#### Scenario: Recalled memory in the trace
- **WHEN** a naive reply is given two recalled memories
- **THEN** `trace.memory.recalled` lists both, and the stored trace references them for Forget
