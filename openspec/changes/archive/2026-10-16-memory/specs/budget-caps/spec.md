# Spec Delta

## ADDED Requirements

### Requirement: Memory work counts against the cap but never pauses
The `memory`, `importance` and `memory_guard` calls and their embeddings SHALL count against the daily cap, SHALL NOT drain energy, and SHALL NOT pause live sessions when they reach or are refused by the cap. A refused run SHALL wait for its next trigger.

#### Scenario: Cap reached by a run
- **WHEN** a pause run's spend crosses the daily cap
- **THEN** no session pauses, and the next reply in any session is refused by the cap

#### Scenario: No energy drained
- **WHEN** a pause run writes memories for Amara
- **THEN** Amara's energy is unchanged
