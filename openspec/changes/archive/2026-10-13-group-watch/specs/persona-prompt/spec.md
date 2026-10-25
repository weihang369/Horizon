# Spec Delta

## MODIFIED Requirements

### Requirement: The preview is the real prompt
The creation wizard's "View as prompt" SHALL show the `agent` system message for a 1:1 chat in the character's world, compiled by a TypeScript twin, with its shared token count labelled "≈". It SHALL update as the profile is edited. Both languages SHALL pass the same committed fixtures byte for byte. No client SHALL fill `systemPromptPreview`. Below the message, one fixed note SHALL say that in group and watch a reply's cue may add one sentence about whom the character is answering, with an example from the same sentence table the backend uses.

#### Scenario: Same text in both languages
- **WHEN** every shared persona fixture is compiled in Python and in TypeScript
- **THEN** each output equals the fixture's expected text and token counts

#### Scenario: Live cut in the preview
- **WHEN** the user pastes a backstory longer than 600 tokens in the wizard
- **THEN** the preview shows the cut backstory ending in "…" and the token count the backend would compute

#### Scenario: No mock label
- **WHEN** the Profile step's prompt view is open
- **THEN** it does not say "mock template"

#### Scenario: The cue note
- **WHEN** the Profile step's prompt view is open
- **THEN** below the system message it shows the note with the example "Hana has just answered. Don't repeat them; add your own angle, or answer Hana directly."

## ADDED Requirements

### Requirement: The turn cue's sentence in group and watch
An `agent` reply's cue SHALL add one English sentence: for a follow-plan second reply, "{first} has just answered. Don't repeat them; add your own angle, or answer {first} directly."; for a group Next speaker, "Nobody asked you directly; say something that moves the talk on. You may answer anyone."; for a steered watch turn, "This thread has run its course. Take the scene somewhere new that still fits the premise." It SHALL follow any director's note and never touch the cached prefix.

#### Scenario: Same table in both languages
- **WHEN** the shared turn-cue fixtures are compiled in Python and in TypeScript
- **THEN** each produces the same sentence

#### Scenario: Prefix unchanged
- **WHEN** a group first reply and a second reply are built for the same session
- **THEN** their system message and summary message are byte-identical, and the requests differ only in the tail's cue line

#### Scenario: After the director's note
- **WHEN** a steered watch turn has an active director's note "Rin is hiding something"
- **THEN** its cue reads "Continue the scene in character. Director: Rin is hiding something" and then the steer sentence
