# debate-host Specification

## Purpose
The Auto host's lines in a debate: a welcome, round bridges, the Extend and Skip lines and the verdict lead-in, written
by DeepSeek ahead of time, shown whole, and replaced by a fixed sentence when they aren't ready.

## Requirements

### Requirement: Which host lines exist
With `moderator: auto_host`, a debate SHALL show one host line, a `note` with author `host` and kind `narration`, for: the welcome (after ROUND 1's banner), the bridge into each later round (after its banner), an extended round (after its banner), Skip to closing (after the CLOSING banner), and the verdict lead-in (after the VERDICT banner). With moderator "You" no host line SHALL show.

#### Scenario: A Standard debate's lines
- **WHEN** a Standard `naive` debate with Auto host runs to an Arbiter verdict
- **THEN** it shows a welcome, a bridge before the rebuttal, a bridge before the closing and a lead-in, each one `narration` note

#### Scenario: No host
- **WHEN** a debate runs with moderator "You"
- **THEN** only the round banners show

### Requirement: Host lines are written ahead and wait a bounded time
Each line SHALL be requested ahead: the welcome at Start, a bridge at its round's last `turn.end`, the Extend and Skip lines when their round begins, and the lead-in at the last closing's `turn.end`. The welcome SHALL wait at most until Start + `debate.hostWelcomeWaitMs` (3,000), and every other line at most `debate.hostBannerWaitMs` (1,500) after its banner. A line not ready by then SHALL be replaced by the fixed line, and its late answer dropped.

#### Scenario: A late bridge
- **WHEN** the bridge to the rebuttal is still being written 1.5 s after the REBUTTAL banner
- **THEN** "Thank you. Rebuttals now: engage with what you actually heard." shows, the round's first argument starts, and the late line never shows

#### Scenario: A bridge made for something else
- **WHEN** a bridge to the closing is being written and the user extends the rebuttal round
- **THEN** that bridge is dropped, and the extended round's line is requested

### Requirement: The host call
A host line SHALL be one DeepSeek call with the `host` settings (thinking off, temperature 1.0, text, 120 tokens) and purpose `host`, charged to the daily cap and never to energy. It SHALL be told to stay neutral, add no argument, use at most 40 words, and write in the motion's language, named explicitly, and it SHALL be given the arguments as quoted transcript.

#### Scenario: The ledger
- **WHEN** a host line is written
- **THEN** one ledger row has purpose `host` and category `chat`, and no character's energy moves

### Requirement: Host line fallbacks
An error, a refusal, an empty answer, an answer over 60 words or a late answer SHALL show the fixed line for that moment. The lead-in's fixed lines SHALL be "Thank you all. The arbiter is weighing the arguments.", "Thank you all. Now it's your call." and "Thank you all. Here is the summary.", by verdict mode. A cap refusal SHALL also pause the session through the existing path.

#### Scenario: Too long
- **WHEN** the welcome comes back at 75 words
- **THEN** the fixed welcome shows instead

### Requirement: Host lines per profile
`naive` and `agent` SHALL share the DeepSeek host. `scripted` SHALL keep its fixed lines with no call, plus the fixed lead-in. Host lines SHALL carry no Insight trace.

#### Scenario: Scripted stays free
- **WHEN** a `scripted` debate with Auto host runs to a verdict
- **THEN** its host lines are the fixed sentences, and no `host` ledger row exists
