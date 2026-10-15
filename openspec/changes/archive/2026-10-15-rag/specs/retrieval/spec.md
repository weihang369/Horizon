# Spec Delta

## MODIFIED Requirements

### Requirement: One query embedding per user message, only when useful
When a 1:1 or group message is sent, the backend SHALL embed its text at most once, starting in parallel with routing, and reuse the result for every reply to that message. It SHALL do so only when knowledge retrieval uses vectors, a key is set, and at least one possible responder has vectors. Debate and watch turns SHALL NOT embed a query. From M12 this applies to the `naive` and `scripted` profiles only: under `agent`, a message SHALL be embedded only after a gate says a speaker needs documents (see `deep-turn`), at most once per message text for all speakers.

#### Scenario: Group message to three characters
- **WHEN** a group message gets three replies and two of the characters have indexed knowledge
- **THEN** exactly one `embedding` ledger row with purpose `query_embed` exists for that message

#### Scenario: Nobody has vectors
- **WHEN** a 1:1 message is sent to a character with only keyword-only sources and no memory vectors
- **THEN** no `query_embed` row is written

#### Scenario: Scripted profile
- **WHEN** the scripted profile answers a message to a character with indexed knowledge
- **THEN** no `query_embed` row is written

#### Scenario: Agent embeds at the gate only
- **WHEN** an `agent` 1:1 message is sent to a character with indexed knowledge and the gate says no
- **THEN** no `query_embed` row is written for it

### Requirement: Naive replies can use and cite what was retrieved
When passages or memories are retrieved, the naive reply engine SHALL add them after the conversation history, numbered for citation, and SHALL report in the trace which passages its reply cited and which memories it was given. With nothing retrieved, its request SHALL be the same as before. From M12, the text it reads for each passage SHALL be a slice of at most 1,200 characters of the passage's section, centred on the passage and cut to whole sentences.

#### Scenario: Cited passage
- **WHEN** with the naive profile a reply uses passage 2 and writes `[2]`
- **THEN** `turn.end.citations` holds that passage, and `trace.knowledge.retrieved` marks it cited and the others not cited

#### Scenario: Recalled memory in the trace
- **WHEN** a naive reply is given two recalled memories
- **THEN** `trace.memory.recalled` lists both, and the stored trace references them for Forget

#### Scenario: A hit deep in a long section
- **WHEN** a naive reply retrieves a passage that starts 4,000 characters into its section
- **THEN** the request's text for it contains the whole passage

## ADDED Requirements

### Requirement: The agent search pipeline
An `agent` search SHALL rank the speaker's passages by keyword (top 20) and by meaning (top 20 per query text with a vector), fuse the meaning lists first and then keyword and meaning by reciprocal rank, normalise the fused scores to 0–1 within the pool, and pick 8 candidates from the top 20 so that near-copies don't fill the slots. Recall (M13) SHALL use the same pipeline with its own numbers.

#### Scenario: Near-copies spread out
- **WHEN** a speaker's top 3 fused passages are near-identical copies, and at least 7 other passages of similar relevance and different content are in the pool
- **THEN** at most one of the copies is among the 8 candidates

#### Scenario: Keyword-only pieces still diversify
- **WHEN** a search runs with no vectors at all and its top passages are word-for-word copies
- **THEN** it still returns at most 8 candidates, and a different passage comes before the second copy

### Requirement: Agent keyword terms
An `agent` search's keyword terms SHALL drop common English stop words, be ordered rarest first within the speaker's searchable passages, and number at most 16, or 24 when the query was rewritten (the rewrite's terms first, then the message's). User text SHALL still be unable to change how the search works.

#### Scenario: Rare terms first
- **WHEN** a message reads "what does the review say about the night shift premium"
- **THEN** "the", "does" and "about" are not searched, and "premium" comes before "review" when fewer of the speaker's passages contain it

### Requirement: A search stays on its space
A search SHALL use one embedding space from start to end. An embedding space switch that commits while a search runs SHALL NOT change the space that search reads.

#### Scenario: Switch during a search
- **WHEN** a space build's switch commits while a deep turn is searching
- **THEN** the turn's candidates all come from the space it started with, and the next turn uses the new one
