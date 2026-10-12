## MODIFIED Requirements

### Requirement: Decision calls are decision spend
Every decision call SHALL be recorded in the ledger with `category: "decision"` and the caller's purpose. It SHALL NOT drain any character's energy. The decision purposes SHALL include `turn_plan`, `reaction` and `face_check`.

#### Scenario: Route decision
- **WHEN** a `route` decision completes for a session
- **THEN** a `decision` row with `purpose: "route"` exists, and no character's energy changes

#### Scenario: Turn plan and face check
- **WHEN** an `agent` 1:1 reply with a non-neutral face completes and its face check answers
- **THEN** one `decision` row with `purpose: "turn_plan"` and one with `purpose: "face_check"` exist, and the character's energy changed only by the reply's drain
