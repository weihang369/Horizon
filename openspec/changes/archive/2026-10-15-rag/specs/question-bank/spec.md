# Spec Delta

## ADDED Requirements

### Requirement: The retrieval entries
The bank SHALL hold, at version 1:
- `docs` ("needs documents?"), a noul about one character, with `t_gate` and `t_confident`;
- `standalone` and `english`, nouls about the latest message, with `t_standalone` and the fixed 0.5;
- `passage` ("does this passage answer it?"), a score with three ordered, unshuffled levels (doesn't help, partly, answers it), with `t_keep` and `t_found`;
- `passage_set`, a noul over several passages, with `t_set`.

#### Scenario: Starting thresholds
- **WHEN** the bank is loaded before M12's evaluation has run
- **THEN** `docs` has `t_gate` 0.35 and `t_confident` 0.8, `standalone` has `t_standalone` 0.5, `passage` has `t_keep` 0.6 and `t_found` 0.6, and `passage_set` has `t_set` 0.5

#### Scenario: Passage levels keep their order
- **WHEN** a `passage` question is asked with two different seeds
- **THEN** its levels are sent in the same order both times

### Requirement: A gate entry declares every plan state it is asked in
An entry asked inside several plans SHALL declare every state field those plans send. "Needs documents?" SHALL be accepted in the 1:1, group, watch and debate plan states.

#### Scenario: Asked in a debate plan
- **WHEN** a debate plan's state holds `phase`, `side`, `quoted_motion`, `quoted_arguments` and `quoted_documents`, and asks `docs`
- **THEN** the request is sent, with no state-field refusal
