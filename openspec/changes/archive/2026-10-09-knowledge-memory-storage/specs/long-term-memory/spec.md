## Purpose

Defines how a character's long-term memories are written, how writes stay consistent per character, and how Forget removes a memory and every copy of its text from what the backend stores (D-70, D-71).

## ADDED Requirements

### Requirement: Memory writes are applied together
A batch of memory operations for one character (insert, supersede, reinforce, touch) SHALL be applied in one transaction, covering each item's row, its keyword index entry and its vectors. If any operation is invalid, nothing in the batch SHALL be written. An operation naming another character's or another world's memory SHALL be invalid.

#### Scenario: One bad operation
- **WHEN** a batch inserts a memory and reinforces an unknown memory ID
- **THEN** the batch fails, and no new memory is listed or found by keyword search

#### Scenario: Supersede
- **WHEN** a batch supersedes memory A with a new memory B
- **THEN** `characters.memory` lists B and not A, and both stay stored as one chain

#### Scenario: Another world's memory
- **WHEN** a batch for a character in world A reinforces a memory belonging to world B
- **THEN** the batch fails, and world B's memory is unchanged

### Requirement: Memory writes are serialised per character
Memory batches for the same character SHALL be applied one at a time, in the order they were queued, even when the character takes part in several sessions.

#### Scenario: Two sessions at once
- **WHEN** two batches for the same character are queued concurrently, each superseding the same memory
- **THEN** they apply one after the other, and the memory list shows exactly one current version

### Requirement: Replies feed the memory writer after they end
After a reply ends `complete`, the backend SHALL ask the memory writer for operations from the speaker's perspective and apply them. A reply that was interrupted, failed or blocked SHALL NOT be passed to the memory writer. A memory writer failure SHALL NOT affect the session. The default memory writer SHALL write nothing.

#### Scenario: Default writer
- **WHEN** a 1:1 reply completes with the default memory writer
- **THEN** the character's memory list is unchanged

#### Scenario: Failing writer
- **WHEN** an attached memory writer raises an error after a reply
- **THEN** the session continues normally, and the error is logged

### Requirement: Forget removes a memory and all its versions
`characters.forgetMemory(id)` SHALL delete that memory, every version it superseded and every version that superseded it, with their keyword and vector index entries. An unknown ID SHALL reject with `not_found`. Afterwards `entity.changed { kind: "memory", id: characterId, worldId }` SHALL be published.

#### Scenario: Forget the current version
- **WHEN** memory B superseded memory A and B is forgotten
- **THEN** neither A nor B is stored, keyword search finds neither, and a `memory` change is announced for the character

#### Scenario: Unknown memory
- **WHEN** `forgetMemory("mem_nope")` is called
- **THEN** it rejects with `not_found` on both clients

### Requirement: Forget scrubs the memory from past insights
Every stored turn trace and every stored `insight` event that recalled a forgotten memory SHALL have that memory's text replaced with `"(forgotten)"`, including traces copied into forked sessions. A session open at that moment SHALL also stop showing the text. Forget SHALL NOT edit message contents.

#### Scenario: Recalled in a seed debate and a fork
- **WHEN** a seed session's insight recalled a memory, the session was forked, and the memory is forgotten
- **THEN** both sessions' insights show the recall as `"(forgotten)"`, and their message contents are unchanged

#### Scenario: Open session
- **WHEN** a memory recalled earlier in a session that is open in the app is forgotten
- **THEN** re-reading that session's messages shows `"(forgotten)"` in the insight

### Requirement: Forgotten text leaves the database files
Once Forget has returned and no read is in progress, the forgotten memory's text SHALL appear nowhere in `data/horizon.db`, in its write-ahead log, or in `data/graph.db` if that file exists. This covers deleted rows, rewritten traces and events, keyword index data and vector storage.

#### Scenario: Byte-level check
- **WHEN** a memory whose text contains a word used nowhere else is recalled in a session and then forgotten
- **THEN** a byte search of `horizon.db`, `horizon.db-wal` and `graph.db` (if present) finds neither the text nor that word

### Requirement: Forget notifies the AI layer
After a Forget commits, the backend SHALL queue a purge entry naming the forgotten memory IDs, their character and the messages whose traces recalled them. It SHALL deliver that entry to the AI layer's forget hook at least once, retrying after a restart. The default hook SHALL do nothing and succeed.

#### Scenario: Retried after a crash
- **WHEN** a memory is forgotten and the backend stops before the hook runs
- **THEN** after restart, the forget hook is called with that memory's ID and character, and the entry is marked done
