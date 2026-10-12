## MODIFIED Requirements

### Requirement: Evaluation judges live in the same bank
Every Jev judge used by an evaluation suite SHALL be a bank entry with purpose `eval_judge`, one condition per question, its text in `quoted_*` fields and, for a noul, a threshold in the entry. A judge SHALL be type `noul`, except the pairwise judge, which SHALL be a `choice` between "reply A", "reply B" and "about the same". Each noul SHALL be worded so that "yes" is the failure, and its label SHALL be worded the same way. Judge entries SHALL never be asked during a live turn. A live question that an evaluation also reads (the face check) SHALL keep its live purpose and be the same entry in both.

#### Scenario: Polarity
- **WHEN** any `eval_judge` noul entry is loaded
- **THEN** its label names the failure (for example "flattery?"), and a high p means the reply failed

#### Scenario: Never live
- **WHEN** a live session runs under any profile
- **THEN** no decision request contains an `eval_judge` question

#### Scenario: Pairwise judge
- **WHEN** the `judge_pairwise` entry is loaded
- **THEN** it is a `choice` with the options `a`, `b` and `same`, purpose `eval_judge`, and shuffling off so the harness controls the order

#### Scenario: Shared face check
- **WHEN** the evaluation asks "face and words agree" about a `naive` reply
- **THEN** it compiles the `face_check` entry, the same id and version the live check uses

## ADDED Requirements

### Requirement: Instructions can name their subject
An entry's instructions MAY hold one `{name}` placeholder, filled when the question is compiled with the name of the character it is about. The value SHALL follow the bank's label rule (at most 40 characters, one line), and compiling an entry with a placeholder but no name SHALL fail. Entries without a placeholder SHALL compile exactly as before.

#### Scenario: Named question
- **WHEN** `emotion_reply` is compiled about Amara
- **THEN** its instructions read "Which face fits how Amara feels on reading quoted_latest?" followed by the quoted-text sentence

#### Scenario: Missing name
- **WHEN** `emotion_reply` is compiled with no name
- **THEN** compiling raises a bank error and nothing is sent

#### Scenario: Older entries unchanged
- **WHEN** the `route` entry and every judge entry are compiled after this change
- **THEN** their compiled questions and lock hashes are unchanged
