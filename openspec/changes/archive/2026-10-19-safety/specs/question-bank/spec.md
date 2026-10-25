## ADDED Requirements

### Requirement: The safety entries
The bank SHALL hold eleven safety nouls at version 1, each worded as the risk, with its threshold under its W12 name: `unsafe_request` and `unsafe_note` (`safety.tSteer`, one shared knob), `at_risk` (`safety.tCare`), `output_rules` (`safety.tFlag`, `safety.tBlock`), `motion_rules` (`safety.tMotion`), `image_likeness`, `image_nudity`, `image_gore` and `image_young` (`safety.tImage*`), `song_copy` (`safety.tSong`) and `instruction` (`memory.tInstruction`).

#### Scenario: Starting values
- **WHEN** the bank is loaded
- **THEN** the thresholds are 0.7 (both `unsafe_*`), 0.3, 0.5 and 0.9, 0.7, 0.5 for each image noul, 0.6 and 0.7, and the lock lists the eleven entries at version 1

#### Scenario: No old entry moves
- **WHEN** the lock is checked after the safety entries are added
- **THEN** every entry from M7–M13 keeps its version and hash

### Requirement: The content rules are written once per entry and stay equal
The content rules (what is outside and what is inside them) SHALL be fixed text in the instructions of `unsafe_request`, `unsafe_note`, `output_rules` and `motion_rules`, never a state field, and the bank SHALL refuse to load when the copies differ.

#### Scenario: A drifted copy
- **WHEN** one entry's rules text is edited and the others are not
- **THEN** loading the bank fails with an error naming the entries
