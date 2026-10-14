# Spec Delta

## ADDED Requirements

### Requirement: The MockClient's debate follows the shared debate rules
The MockClient's debate engine SHALL fill phase slots by the same rule as the scripted backend (the first eligible member in fixed order, the skip note when the side has been heard), pause when a slot's side has nobody awake (keeping the slot), and show a fixed verdict lead-in with Auto host, matching the scripted backend on the shared portable contract tests.

#### Scenario: Asleep side in the mock
- **WHEN** the shared asleep-side contract test runs on the MockClient
- **THEN** its event types, notes, speakers and pause equal the scripted backend's

### Requirement: The mock verdict's charge
The MockClient's Arbiter verdict SHALL charge one simulated call with purpose `verdict` in category `chat`, matching the scripted backend. A pick SHALL charge nothing.

#### Scenario: Mock verdict
- **WHEN** a MockClient debate with Arbiter verdict ends
- **THEN** its ledger has one `verdict` charge in category `chat`, and no `decision` charge for the verdict
