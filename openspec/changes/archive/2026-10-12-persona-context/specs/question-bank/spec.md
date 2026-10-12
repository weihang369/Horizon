# Spec Delta

## ADDED Requirements

### Requirement: Evaluation judges live in the same bank
Every Jev judge used by an evaluation suite SHALL be a bank entry with purpose `eval_judge`, type `noul`, one condition per question, its text in `quoted_*` fields and a threshold in the entry. Each SHALL be worded so that "yes" is the failure, and its label SHALL be worded the same way. Judge entries SHALL never be asked during a live turn.

#### Scenario: Polarity
- **WHEN** any `eval_judge` entry is loaded
- **THEN** its label names the failure (for example "flattery?"), and a high p means the reply failed

#### Scenario: Never live
- **WHEN** a live session runs under any profile
- **THEN** no decision request contains an `eval_judge` question
