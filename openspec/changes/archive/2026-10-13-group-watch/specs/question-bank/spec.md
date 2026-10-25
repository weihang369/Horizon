# Spec Delta

## ADDED Requirements

### Requirement: A dynamic choice can leave out none
Compiling a dynamic choice SHALL accept a switch that leaves out its `none` option. Without the switch, every entry SHALL compile exactly as before, so no existing lock hash changes. Static options SHALL be unaffected.

#### Scenario: Route without a mention
- **WHEN** `route` is compiled with the switch off for a message that mentions nobody
- **THEN** its options are the eligible characters only, and its instructions don't mention `none`

#### Scenario: Older entries unchanged
- **WHEN** every entry is compiled without the switch after this change
- **THEN** each compiles to the same text as before, and `questions.lock.json` needs no change for them

### Requirement: Dynamic options hold only short labels
Every value filled into a dynamic option's template SHALL pass the bank's label rule (one line, at most 40 characters); a longer value SHALL be cut by the shared helper before compiling, never sent whole. User-written text longer than a label SHALL appear only in `quoted_*` state fields.

#### Scenario: A long role
- **WHEN** a character's role is 70 characters and `who_first` is compiled
- **THEN** that option shows the role cut to at most 40 characters, and the full role is only in `quoted_cast`

### Requirement: The group and watch entries
The bank SHALL hold `who_first`, `who_second`, `who_next`, `who_scene` (dynamic choices over the cast; only `who_second` offers `none`), `talk_finished` (a noul with threshold `t_end`), and `emotion_line` and `emotion_opening` (static choices with the emotion options), each at version 1 with the wording recorded in the change's design. `route` SHALL move to version 3.

#### Scenario: Lock check
- **WHEN** the bank lock is checked after this change
- **THEN** it lists the seven new entries at version 1 and `route` at version 3, and reports no problem
