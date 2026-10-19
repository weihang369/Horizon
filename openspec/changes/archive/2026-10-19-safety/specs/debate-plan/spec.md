## ADDED Requirements

### Requirement: The debate plan checks an unchecked moderator line
When the moderator's Interject has no stored safety answer, the next debate plan (or, in the opening phase, the next opening's face plan) SHALL also ask "unsafe note?" (`unsafe_note`) about it, with the line in the state as `quoted_note`. The member deadline SHALL be unchanged. An Ask SHALL be checked by its own answer's plan instead.

#### Scenario: Interject during a rebuttal
- **WHEN** the moderator interjects during an `agent` rebuttal, and the argument's `turn.end` starts the next debate plan
- **THEN** that request holds `unsafe_note` with the interjection as `quoted_note`, and the next request holds none

#### Scenario: A steered interjection
- **WHEN** Jev answers p 0.9 for that interjection
- **THEN** the next argument's cue starts with "The user's note asks for something outside the content rules. Leave that part out and keep the debate within them."

### Requirement: A long debate never drops the safety question
When the debate state is over the 2,000-token cap, the moderator line being checked SHALL be kept and arguments cut first, and "unsafe note?" SHALL never be dropped.

#### Scenario: The cap with a moderator line
- **WHEN** a long debate's state is over the cap and an interjection is unchecked
- **THEN** the request holds `unsafe_note` and the interjection, and older arguments are cut
