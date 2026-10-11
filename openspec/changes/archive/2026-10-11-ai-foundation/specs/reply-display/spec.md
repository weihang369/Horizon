## Purpose

Reply display shows one character message the way people text: up to four bubbles in chat modes and script lines in watch mode, without changing the message model (one message, one emotion, one trace).

## ADDED Requirements

### Requirement: Chat replies show as up to four bubbles
In 1:1 and group sessions, a character message SHALL be displayed as one bubble per line of its text. Blank lines SHALL collapse. Lines past the fourth SHALL join the fourth. The text SHALL NOT be split inside a fenced code block, or between consecutive list lines. Citation chips SHALL sit under the last bubble. The message SHALL stay one message with one emotion, trace, energy charge, regenerate and copy.

#### Scenario: Three lines
- **WHEN** a 1:1 reply's content is `Haha. Yeah, I know.\n\nLong shift.\nYou?`
- **THEN** three bubbles show: `Haha. Yeah, I know.`, `Long shift.` and `You?`

#### Scenario: Six lines
- **WHEN** a group reply has six non-blank lines
- **THEN** four bubbles show, and the fourth holds lines 4–6

#### Scenario: Bubble opens while streaming
- **WHEN** a streaming reply receives a line break and then more text
- **THEN** a second bubble opens with the new text

### Requirement: Watch replies show as script lines
In watch sessions, each line of a character message SHALL be its own script line under one name tape, with the same splitting rules.

#### Scenario: Two script lines
- **WHEN** a watch reply's content has two lines
- **THEN** two script lines show under one name tape

### Requirement: Some text is never split
Debate arguments, host lines and the user's own messages SHALL never be split.

#### Scenario: Debate argument
- **WHEN** a debate argument's content contains a line break
- **THEN** it shows as one block

### Requirement: Readable applies per bubble
The automatic switch to the Readable panel SHALL apply in bubble modes only when a single bubble is over 600 characters. When the user turns Readable on, the message SHALL show unsplit.

#### Scenario: Long reply of short bubbles
- **WHEN** a 1:1 reply of 700 characters has three lines, each under 600 characters
- **THEN** it shows as bubbles, not the Readable panel

### Requirement: The demo shows bubbles
The shipped seed transcripts, the mock reply banks and the scripted engine's lines SHALL contain line breaks in 1:1, group and watch character replies, so a session with no key shows bubbles.

#### Scenario: Seed 1:1 transcript
- **WHEN** the seed 1:1 session with Amara is opened in demo mode
- **THEN** at least one of her replies shows as two or more bubbles
