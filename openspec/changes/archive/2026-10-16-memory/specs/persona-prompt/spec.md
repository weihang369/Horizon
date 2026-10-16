# Spec Delta

## MODIFIED Requirements

### Requirement: Four fixed blocks in one cached system message
The `agent` system message SHALL hold, in order: "Who you are" (the card), "Your world and the user", "What you remember" (only when the speaker has current memories), "This session" (the mode block with its length line), and "How to reply" (the rules). It SHALL be built only from the profile, the appearance summary, the advisory flag, the world name, the You card, the session's mode data and the sitting's memory list, so it is identical on every turn of a sitting. Its prompt version SHALL be `agent-1`.

#### Scenario: Stable across turns
- **WHEN** two consecutive turns of the same speaker in a session are compiled with no profile, You-card or cast change between them
- **THEN** the two system messages are byte-identical

#### Scenario: Nothing per turn in the prefix
- **WHEN** the speaker's face, energy or the turn number changes between two turns
- **THEN** the system message is unchanged

#### Scenario: No memories, no block
- **WHEN** a speaker with no current memories is compiled
- **THEN** the system message is byte-identical to the one compiled before memories existed

## ADDED Requirements

### Requirement: The memory list
"What you remember" SHALL list the speaker's current memories ranked by importance × recency × mode weight, one per line, each newline-collapsed and cut at 40 words, added in rank order until 1,000 tokens. Its heading SHALL say the notes come from earlier conversations, to bring one up only when it fits, and never to list them. Every reply's trace SHALL list the block's memories in `memory.recalled` without a score.

#### Scenario: Ranking
- **WHEN** a speaker holds a watch memory and a 1:1 memory with equal importance and age
- **THEN** the 1:1 memory is listed first

#### Scenario: Over the budget
- **WHEN** a speaker holds 80 memories
- **THEN** the block holds the top-ranked ones up to 1,000 tokens, and the rest are left for recall

### Requirement: The memory list is frozen for a sitting
Within a sitting the memory list SHALL NOT change, even when memories are written, except when one of its memories is forgotten or a pause run commits memories for that speaker during the sitting.

#### Scenario: Forget during a chat
- **WHEN** the user forgets a memory shown in Amara's list while chatting with her
- **THEN** her next reply's system message lacks that line, and the reply after it sends the same system message as the one before

### Requirement: The greeting mentions last time
A generated 1:1 greeting SHALL add to its tail up to 2 of the newest memories from the last 1:1 session with the user, and its cue SHALL say that if something from last time fits, it may be mentioned in a short phrase. It SHALL NOT wait for a pending pause run. The first 1:1 chat SHALL keep the stored greeting word for word.

#### Scenario: Second chat
- **WHEN** a second 1:1 session with Amara opens and her last 1:1 session wrote 3 memories
- **THEN** the greeting request's tail holds the 2 newest of them and the cue sentence

### Requirement: The twin compiles the memory list
The TypeScript twin SHALL accept the same memory list and produce the same bytes as the backend on the committed fixtures, including an empty list, the 40-word cut and newline collapsing. The creation preview SHALL pass no memories.

#### Scenario: Shared fixture
- **WHEN** both compilers run the fixture with three memories, one holding a newline
- **THEN** their outputs are byte-identical and the newline is gone
