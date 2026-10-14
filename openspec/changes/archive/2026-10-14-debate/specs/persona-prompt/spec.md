# Spec Delta

## MODIFIED Requirements

### Requirement: The turn cue's sentence in group and watch
An `agent` reply's cue SHALL add one English sentence: for a follow-plan second reply, "{first} has just answered. Don't repeat them; add your own angle, or answer {first} directly."; for a group Next speaker, "Nobody asked you directly; say something that moves the talk on. You may answer anyone."; for a steered watch turn, "This thread has run its course. Bring in something new that fits the premise: an event, a discovery or a change of plan. Don't wrap up, say goodbye or wait for {user} to decide." It SHALL follow any director's note and never touch the cached prefix.

#### Scenario: Same table in both languages
- **WHEN** the shared turn-cue fixtures are compiled in Python and in TypeScript
- **THEN** each produces the same sentence

#### Scenario: Prefix unchanged
- **WHEN** a group first reply and a second reply are built for the same session
- **THEN** their system message and summary message are byte-identical, and the requests differ only in the tail's cue line

#### Scenario: After the director's note
- **WHEN** a steered watch turn has an active director's note "Rin is hiding something"
- **THEN** its cue reads "Continue the scene in character. Director: Rin is hiding something" and then the steer sentence

#### Scenario: The steer names the watcher
- **WHEN** a watch turn steers in a world whose You card is Kai
- **THEN** the steer sentence ends "Don't wrap up, say goodbye or wait for Kai to decide."

## ADDED Requirements

### Requirement: The debate cue
An `agent` debate argument's cue SHALL be its phase's line: opening "Give your opening statement: your case in two or three reasons."; rebuttal "Give your rebuttal: name the strongest point the other side has made so far and answer it, then strengthen your own case." (panel: "the strongest point you disagree with"); closing "Give your closing statement: why your side's case is the stronger one. Answer what is still open, and add no new arguments.". Optional sentences SHALL follow on their own lines.

#### Scenario: A rebuttal after a teammate
- **WHEN** Rin's rebuttal follows Amara's in the same round, with no Interject
- **THEN** the cue is the rebuttal line, then "Amara has already spoken for your side this round: add to it, don't repeat it."

#### Scenario: Same table in both languages
- **WHEN** the shared debate-cue fixtures are compiled in Python and in TypeScript
- **THEN** each produces the same cue

### Requirement: The debate cue's optional sentences
After the phase line, in this order: in an extended round, "The round was extended: make a point not yet made."; when teammates were heard this round, "{teammates} has already spoken for your side this round: add to it, don't repeat it." ("have" for two or more); when an Interject came after the last argument, "Take the moderator's last note into account." An Ask answer SHALL keep "Answer the moderator's question directly: …".

#### Scenario: An extended rebuttal after an Interject
- **WHEN** the first argument of an extended rebuttal round follows an Interject
- **THEN** its cue is the rebuttal line, the extended-round line, then the moderator sentence

### Requirement: The debate prompt's prefix is stable
Within one debate, an `agent` speaker's system message SHALL be byte-identical on every turn. A debate argument's request SHALL differ from the same turn without the debate cue only in the tail's cue line.

#### Scenario: Two rounds, one prefix
- **WHEN** Amara's opening and rebuttal requests are built
- **THEN** their system messages are byte-identical

### Requirement: The preview's debate note
"View as prompt" SHALL show, under system message 1, one fixed note built from the debate cue table: "In a debate, each argument's cue names its round, e.g. “Give your rebuttal: …”".

#### Scenario: The note is the table's
- **WHEN** the preview is opened
- **THEN** the note quotes the rebuttal line from the TS debate cue table
