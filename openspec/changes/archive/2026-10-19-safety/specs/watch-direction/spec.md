## ADDED Requirements

### Requirement: A director's note is checked by the next plan
Under `agent`, a director's note with no stored safety answer SHALL be asked "unsafe note?" (`unsafe_note`, with the note as `quoted_note`; never "at risk?") by the next plan that sees it: the next scene plan, or a plan made ahead after the note made the earlier one stale. When the answer steers, the turns the note colours SHALL carry the scene steer sentence.

#### Scenario: The note is checked once
- **WHEN** the user sends a director's note in an `agent` watch and two turns follow
- **THEN** exactly one request holds `unsafe_note` about the note

#### Scenario: A steered note
- **WHEN** Jev answers p 0.9 for the note
- **THEN** both turns it colours carry "The user's note asks for something outside the content rules. Leave that part out and keep the scene within them." before the director's line

### Requirement: Step in is checked like a group message
Under `agent`, a Step in line SHALL be asked "unsafe request?" and "at risk?" in its cast plan, and a steer or care cue SHALL give it one voice.

#### Scenario: Step in at risk
- **WHEN** a Step in line's `at_risk` answer is p 0.8
- **THEN** one character answers with the care paragraph in its cue, and no follow plan runs
