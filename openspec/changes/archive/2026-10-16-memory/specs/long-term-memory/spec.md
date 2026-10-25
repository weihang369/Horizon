# Spec Delta

## ADDED Requirements

### Requirement: Memories are written when a session pauses
Memories SHALL be written by a pause run over a session's new messages, never after each reply. A run SHALL be requested when the last stream subscriber has been gone for 30 s (any status), on `leave`, on `end`, after a debate's verdict, at watch's turn cap, when a reply kept at one of these reaches `turn.end`, at start-up for every non-seed session with unread lines, and on idle release.

#### Scenario: Tab closed on a paused chat
- **WHEN** the user closes the tab of a user-paused 1:1 session with unread lines, and nobody reopens it for 30 s
- **THEN** one run starts for that session

#### Scenario: Reload within the grace
- **WHEN** the session's stream closes and reopens within 30 s
- **THEN** no run starts from that close

#### Scenario: Nothing written mid-chat
- **WHEN** ten replies complete in a session that stays open
- **THEN** no memory call is recorded for that session

### Requirement: A session opening runs the other session's memories first
When a session is created, or its actor starts for a resume, the backend SHALL request at high priority the runs of other non-seed sessions in the world that share a participant and have unread lines, ahead of normal requests.

#### Scenario: New chat two minutes later
- **WHEN** a 1:1 session with Amara is left with unread lines and a new 1:1 with Amara opens before its grace ends
- **THEN** the old session's run starts at once, ahead of queued start-up runs

### Requirement: Pause runs are bounded and independent of sessions
At most two runs SHALL run at once and at most one per session; a request during a run SHALL queue one more run after it. Runs SHALL NOT take reply slots, delay replies or keep a session's actor from going idle. Deleting a session, character or world, Reset demo and factory reset SHALL cancel the affected runs, which SHALL write nothing.

#### Scenario: Delete during a run
- **WHEN** a session is deleted while its run's rewrite call is in flight
- **THEN** no memory is written from it, and the call is recorded `cancelled`

#### Scenario: Three sessions pause at once
- **WHEN** three sessions request runs at the same moment
- **THEN** two run and the third starts when one ends

### Requirement: A run reads only settled lines once
A run SHALL read the messages after the session's memory checkpoint up to the last settled one, so a reply still streaming is never passed: user and character lines, active variant, complete, with debate moderator lines labelled as the moderator. It SHALL skip notes, narration, direction notes and interrupted, failed or blocked replies, and advance the checkpoint in the same transaction as its memories.

#### Scenario: User sends during a stream
- **WHEN** a run starts while a reply streams after messages 1–8, and the user's message 10 arrives behind it
- **THEN** the run reads messages up to 8 and the checkpoint stops at 8

#### Scenario: Director's note
- **WHEN** a watch stretch holds a director's note
- **THEN** the note is not in the run's input

### Requirement: Old history and forked history are never mined
On upgrade, every existing session's checkpoint SHALL start at its highest message number. A fork, including "Continue live", SHALL start at the highest message number it copied. A new session SHALL start at zero.

#### Scenario: Upgrade
- **WHEN** the backend upgrades with a session of 200 messages
- **THEN** its next run reads only messages after the 200th

#### Scenario: Fork after a Forget
- **WHEN** the user forgot a memory and then forks the session it came from
- **THEN** no run of the fork reads the copied messages, and the memory does not return

### Requirement: Below the minimum nothing moves
A run SHALL make no call and leave the checkpoint unmoved unless its new lines include at least one user line said in the scene or at least 4 character lines. An ended session SHALL advance its checkpoint anyway.

#### Scenario: Two character lines
- **WHEN** a watch session pauses after 2 new character lines
- **THEN** no memory call is made and the next run reads those lines again with the rest

### Requirement: Runs wait for a usable key
Without a usable key, including a profile that falls back to scripted only for lack of one, a run SHALL be deferred: no call, no checkpoint move, no try counted. An explicitly scripted profile SHALL advance the checkpoint with no call. Seed sessions SHALL never run.

#### Scenario: Key added later
- **WHEN** a session pauses with no key, and a key is added before its next pause
- **THEN** the next run reads every line since the first pause

### Requirement: One call writes every present character's memories
A run SHALL send one JSON-mode `memory` call per piece of at most 8,000 tokens, holding each present character's current list and the numbered new lines, and SHALL apply only the changes it returns: add, rewrite (keeping every still-true part) or confirm. Code SHALL check every change and drop invalid ones, with at most 5 adds and rewrites per character per piece.

#### Scenario: Two characters, one call
- **WHEN** a group run with Amara and Mei covers one piece
- **THEN** exactly one `memory` call is recorded for it, and each character's changes are written from their own point of view

#### Scenario: Answer cut short
- **WHEN** the call ends with `finish_reason` `length`
- **THEN** it is not counted as a try, and the characters are split into two calls over the same lines

#### Scenario: Unknown target
- **WHEN** the answer rewrites `m40` for a character with 12 listed memories
- **THEN** that change is dropped and logged, and the other changes are applied

### Requirement: Jev scores importance and guards rewrites
Under `agent`, each added or rewritten line SHALL get a Jev importance score (5 levels, mapped to 0–1); an add under 0.25 SHALL be dropped; a confirm SHALL raise importance by 0.05 and refresh its last-recalled time. Each rewrite SHALL be applied as a replacement only when Jev's guard says every still-true part is kept (at or above `t_keep`); otherwise the new line SHALL be added beside the old one.

#### Scenario: Lossy rewrite
- **WHEN** a rewrite drops the sister's city and the guard answers p 0.2
- **THEN** both the old and the new line are current

#### Scenario: Jev down
- **WHEN** every importance request fails
- **THEN** importance comes from the writer's weight hint, or 0.5 without one, and the run is not failed

### Requirement: Duplicate adds reinforce instead
An added line equal (ignoring case) to a current memory, or whose vector's cosine with a current memory is at least the space's `dupCosine`, SHALL reinforce that memory instead of being inserted.

#### Scenario: Same fact again
- **WHEN** a run adds "Kai's favourite cake is yuzu." and that memory is current
- **THEN** no new memory is inserted and the existing one's importance rises by 0.05

### Requirement: A run commits its memories with its checkpoint
A run SHALL commit every character's memories, the checkpoint move (only if the checkpoint is still where the run started) and the re-read list's update in one transaction. A draft whose source variant is no longer active SHALL be dropped. A rewrite or confirm whose target was forgotten during the run SHALL be dropped, not fail the batch.

#### Scenario: Forget during a run
- **WHEN** the user forgets memory A while a run that rewrites A is in flight
- **THEN** the run commits its other changes and A does not come back

#### Scenario: Two runs race
- **WHEN** two runs started from the same checkpoint reach their commit
- **THEN** one commits and the other writes nothing

### Requirement: Failed runs retry, then skip
A failed call (after its one retry) SHALL write nothing, keep the checkpoint and count a try; after 3 tries on the same checkpoint the piece SHALL be skipped with the checkpoint advanced and a warning logged. A daily-cap refusal SHALL NOT count as a try.

#### Scenario: Poison stretch
- **WHEN** the same piece fails three runs in a row
- **THEN** the third failure advances the checkpoint past it with no memories written

### Requirement: Runs on one character never overlap
A run SHALL hold every present character's memory lock, taken in a fixed order, from reading their lists until its commit, so no two runs rewrite one list from stale copies.

#### Scenario: Two sessions share a character
- **WHEN** two sessions with Amara pause at once
- **THEN** the second run reads Amara's list only after the first commits

### Requirement: A changed read message is undone and read again
Before a Regenerate or Continue on an already-read message streams, the memories still current that came from that message SHALL be removed through the Forget path, the lines they replaced SHALL become current again, and the message SHALL be queued to be read again by the next run without moving the checkpoint.

#### Scenario: Regenerated fact
- **WHEN** a read reply produced memory B replacing A, and the user regenerates that reply
- **THEN** B is gone, A is current again, and the next run reads the new variant

### Requirement: Forget clears stored query rewrites
Removing a memory through the Forget path (a user Forget, the undo, a blocked reply) SHALL also delete that character's stored query rewrites in that world in the same transaction.

#### Scenario: Regenerate after a Forget
- **WHEN** a character's rewrite for a message is stored, the user forgets one of its memories, then regenerates that reply
- **THEN** a new rewrite call is made instead of reusing the stored one

### Requirement: Writers per profile
`agent` SHALL write with Jev importance, the guard and the duplicate check; `naive` SHALL make the same call with importance from the writer's hint, rewrites applied as replacements and only exact duplicates skipped; `scripted` SHALL write nothing. Test mode SHALL use the `agent` writer with canned answers unless the profile is scripted.

#### Scenario: Scripted demo
- **WHEN** the scripted profile's session pauses
- **THEN** no memory call is made and the checkpoint advances

### Requirement: The Memory tab shows memories in pages
The Memory tab SHALL show the newest 50 memories and a "Show more (n)" button that adds 50 at a time, and SHALL show no "Preview" ribbon. A memory whose source session no longer exists SHALL show no "View source".

#### Scenario: 120 memories
- **WHEN** a character has 120 memories
- **THEN** the tab shows 50 and "Show more (70)"

## REMOVED Requirements

### Requirement: Replies feed the memory writer after they end
**Reason**: Doc 09 M1 (the user's decision): memories are written at session pauses over the whole sitting, never after each reply, and from every present character's point of view.
**Migration**: The per-reply queue is removed; see "Memories are written when a session pauses" and "One call writes every present character's memories".
