## ADDED Requirements

### Requirement: The safety cue sentences
An `agent` reply's cue SHALL start, when its line's cue is on, with the care paragraph and then the steer sentence, before every other cue sentence (G3's, the debate cue, the Ask's cue, the scene and the director's note). Care SHALL replace G3's "next" and watch-steer sentences. The sentences SHALL be English, SHALL sit in the tail and SHALL never touch the cached prefix.

#### Scenario: Prefix unchanged
- **WHEN** a steered reply and an unsteered reply are built for the same 1:1 sitting
- **THEN** their system messages are byte-identical, and the requests differ only in the tail's cue line

#### Scenario: Care replaces the next sentence
- **WHEN** a group Next speaker turn answers a care message
- **THEN** its cue holds the care paragraph and not "Nobody asked you directly; say something that moves the talk on."

#### Scenario: Both cues
- **WHEN** a message is both steered and at risk
- **THEN** the cue holds the care paragraph first, then the chat steer sentence

### Requirement: Safety prompts are labelled by what they send
A request carrying a safety cue SHALL add `+care-1` or `+steer-1` (both: `+care-1+steer-1`) to its prompt label, after any other suffix. No base version SHALL change.

#### Scenario: A steered deep turn
- **WHEN** a steered 1:1 turn goes deep with documents
- **THEN** its prompt version is `agent-1+docs-1+steer-1`
