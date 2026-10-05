# Spec Delta

## Purpose

Defines how live sessions come into being and leave: creating one from a cast, forking a seed recording at a playhead, renaming, leaving, ending and deleting, and exporting a transcript as Markdown with citation footnotes.

## ADDED Requirements

### Requirement: Create a session
`sessions.create` SHALL need a usable key and SHALL validate:
- the cast size by mode (1:1 exactly 1; group, debate and watch 2–5);
- every participant `approved`;
- every participant in the session's world.

A cast-size violation SHALL reject with `validation` and `details { field: "characterIds", min, max, got }`. A character from another world SHALL reject with `not_found`. A non-approved character SHALL reject with `validation`.

#### Scenario: Wrong cast size
- **WHEN** a 1:1 session is created with two characters
- **THEN** it rejects with `validation` and `details` containing `min: 1` and `max: 1`

#### Scenario: Character from another world
- **WHEN** a session in `wld_seedMeridian` is created with `chr_seedHana` from `wld_seedSunnyHollow`
- **THEN** it rejects with `not_found`, and no session row is written

### Requirement: New session opening
A created session SHALL start `active`, with the MockClient's defaults for title, config, state and music policy per mode. Its first events SHALL be a `session.state` snapshot and one `energy` event per participant. A 1:1 session SHALL then greet, a debate SHALL start its first phase, and a watch SHALL post its premise and start playing, each after the shared timing table's delay.

#### Scenario: 1:1 greeting
- **WHEN** a 1:1 session with Amara is created and 6 seconds of clock time pass
- **THEN** the session holds exactly one character message, `complete`, and the snapshot returned by create already reflected the opening events

### Requirement: Fork a recording
`sessions.forkSeedSession(id, atSeq?)` SHALL need a usable key, and SHALL create a new non-seed session with `continuedFrom: id` from the source's events up to `atSeq`. If a turn was streaming at `atSeq`, the cut SHALL extend to that turn's `turn.end`. Event and message IDs SHALL be renamed deterministically and events renumbered from 1, as the MockClient does. The source session SHALL be unchanged.

#### Scenario: Fork a debate at a third of the way
- **WHEN** `ses_seedDebate4Day` is forked at the `seq` a third of the way through its events
- **THEN** the fork is non-seed, `continuedFrom` is `ses_seedDebate4Day`, no message is `streaming`, it has fewer messages than the source, and the source's event count is unchanged

### Requirement: Forked session state
A fork of a debate or watch session SHALL start `paused` with `pausedReason: "user"` (a watch's state also `paused`), and a fork of a 1:1 or group session SHALL start `active`, unless the source had ended, in which case the fork stays ended. A paused debate fork SHALL continue from its playhead when resumed.

#### Scenario: Resume a forked debate
- **WHEN** a debate fork is resumed and 30 seconds of clock time pass
- **THEN** the fork holds more messages than when it was created

### Requirement: Rename, leave and end
`sessions.rename` SHALL trim the title to at most 80 characters, set `titleIsCustom`, and emit a `session.state` settings event for a live session. `sessions.leave` SHALL pause an active non-seed session with `navigated_away`, and SHALL do nothing for others. `sessions.end` SHALL end the session (`status: "ended"`). After that, every command that would generate SHALL reject with `conflict`.

#### Scenario: Send after end
- **WHEN** a live 1:1 session is ended and a message is sent to it
- **THEN** the send rejects with `conflict`

### Requirement: Delete a session
`sessions.delete` SHALL stop the session's running work first, then delete the session and everything stored under it (events, messages, traces, citations, summaries) in one commit, then queue an AI purge for the session (see `ai-ports`) and announce `entity.changed { kind: "session" }`. Ledger rows SHALL keep their amounts.

#### Scenario: Delete a streaming session
- **WHEN** a session is deleted while a reply is streaming
- **THEN** the stream stops, `GET /sessions/{id}` returns `not_found`, the reply's ledger row remains, and one AI purge entry with scope `session` exists

### Requirement: Markdown export
`sessions.export` SHALL return `text/markdown` with:
- the title;
- mode, cast with sides, and the motion or premise;
- one line per message, with the author, an `[emotion]` tag and the content;
- the verdict, when there is one.

Citation markers `[n]` SHALL become footnotes `[^n]`, and a `## Sources` section SHALL list each one as `[^n]: {title}, {locator}. "{quote}"`. The export SHALL contain no API key.

#### Scenario: Seed debate export
- **WHEN** `ses_seedDebate4Day` is exported
- **THEN** the Markdown contains `[^1]` and `## Sources`, matches `[^1]: Meridian Shift Fatigue Review 2025.pdf, p. 4. "`, and contains no `[n]` marker directly after a word or punctuation
