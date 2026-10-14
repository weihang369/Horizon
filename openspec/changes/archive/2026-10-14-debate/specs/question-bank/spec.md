# Spec Delta

## ADDED Requirements

### Requirement: Instructions can name a debate side
An entry's instructions MAY hold `{side}` and `{other}` placeholders, filled when the question is compiled. Each value SHALL be one of "Proposition" or "Opposition", and any other value, or a missing one, SHALL fail compiling. A score entry MAY hold `{n}`, a position number checked to be a whole number from 1 to 6. Entries without these placeholders SHALL compile exactly as before.

#### Scenario: A side is named
- **WHEN** `member_rebuttal` is compiled for the Proposition
- **THEN** its instructions read "The Opposition has just made the argument in quoted_arguments.last_opposing. Which of these Proposition speakers is best placed to answer it?" followed by the quoted-text sentence

#### Scenario: User text can't enter
- **WHEN** a caller passes "Team Blue" as the side
- **THEN** compiling raises a bank error and nothing is sent

#### Scenario: Older entries unchanged
- **WHEN** every entry from before this change is compiled
- **THEN** their compiled questions and lock hashes are unchanged

### Requirement: The debate entries
The bank SHALL hold, each at version 1 with the wording recorded in the change's design:
- `member_rebuttal`, `member_closing` and `member_panel` (dynamic choices over the eligible members, no `none`, purpose `debate_plan`);
- `emotion_debate_opening` (a static choice with the emotion options);
- `rubric_evidence`, `rubric_rebuttal`, `rubric_clarity`, `rubric_persuasion` and `rubric_generic` (5-level scores, purpose `rubric`).

#### Scenario: Lock check
- **WHEN** the bank lock is checked after this change
- **THEN** it lists the nine new debate entries at version 1 and reports no problem

### Requirement: Shared knobs stay equal
`floor.member` SHALL be the `floor` of each member entry, and `verdict.margin` the `margin` threshold of each rubric entry. The loader SHALL refuse a bank where the three member floors, or the five rubric margins, differ.

#### Scenario: A drifted floor
- **WHEN** `member_closing`'s floor is set to 0.3 while the other member entries have 0.2
- **THEN** loading the bank fails, naming `floor.member`

### Requirement: The who-speaks entries without last_spoke
`who_scene` and `who_next` SHALL move to version 3, with a state whose cast entries carry no `last_spoke` label. Their instructions, options and floors SHALL be unchanged until re-measured.

#### Scenario: The scene state
- **WHEN** a watch turn's `who_scene` state is built after this change
- **THEN** no `quoted_cast` entry has a `last_spoke` field, and the lock lists `who_scene` and `who_next` at version 3

### Requirement: The judges added in M11
The bank SHALL hold `judge_keeps_side`, `judge_engages` and `judge_starts_new` (nouls, purpose `eval_judge`) at version 1, and `judge_summary_unsupported` at version 2 with an optional `quoted_premise` state field, each with the wording recorded in the change's design.

#### Scenario: The recap judge sees the premise
- **WHEN** a recap is judged with `judge_summary_unsupported` v2
- **THEN** the state holds `quoted_premise`, and the instructions name it
