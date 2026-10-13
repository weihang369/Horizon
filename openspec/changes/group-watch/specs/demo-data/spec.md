# Spec Delta

## ADDED Requirements

### Requirement: The MockClient's group follows the shared group rules
The MockClient's group engine SHALL answer an all-asleep mention with the asleep notes only, and SHALL drop replies to an earlier message that have not emitted `turn.next` when a new user message arrives, matching the scripted backend on the shared portable contract tests.

#### Scenario: Asleep mention in the mock
- **WHEN** a MockClient group message mentions only an asleep character
- **THEN** that character gets the asleep note, and no other character replies

#### Scenario: Supersede in the mock
- **WHEN** the shared supersede contract test runs on the MockClient
- **THEN** its event types and speakers equal the scripted backend's

### Requirement: The mock recap's charge
The MockClient's watch Summarise SHALL keep its canned recap and charge one simulated call with purpose `episode_summary`, matching the scripted backend.

#### Scenario: Mock recap
- **WHEN** a MockClient watch is summarised
- **THEN** its ledger has one `episode_summary` charge in category `summary`, and the canned recap is posted
