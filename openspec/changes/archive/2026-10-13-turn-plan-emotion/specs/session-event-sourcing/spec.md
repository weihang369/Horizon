## MODIFIED Requirements

### Requirement: One reducer in two languages
The backend SHALL derive messages, participant state and session state from session events using the same rules as the frontend reducer. For every case in `backend/tests/fixtures/reducer/`, both the TypeScript and the Python reducer SHALL produce exactly the case's expected session and messages. The cases SHALL include a reaction for the character who is streaming, before and after its first token, and the seed case `ses_seedDinner` seq 25.

#### Scenario: Shared fixture run
- **WHEN** the Python tests run the reducer fixtures
- **THEN** every case passes, and so does the TypeScript fixture test on the same files

#### Scenario: Divergence is caught
- **WHEN** one reducer's handling of a later `insight` is changed to keep the first trace
- **THEN** the `insight-replacement` case fails in that language

#### Scenario: Speaker's face kept against a reaction
- **WHEN** both reducers run the case where a reaction for Rin arrives 10 ms after Rin's own `turn.start`
- **THEN** both keep Rin's face unchanged, and both record the reaction on the message it reacts to

#### Scenario: Seed sessions still reduce
- **WHEN** every seed session is re-reduced after the speaker-face rule
- **THEN** each reduces to its shipped messages
