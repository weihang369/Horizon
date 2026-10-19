## MODIFIED Requirements

### Requirement: The face rule
The face sent SHALL be Jev's pick when it is not `none` and Jev's confidence reaches the question's floor (0.6 to
start). Otherwise the base face SHALL be kept, except that a kept `surprised` or `embarrassed` face SHALL become
`neutral` (the `emotion.fade` set in the runtime config). While the reply's care cue is on, the face from any of these
paths SHALL be `neutral`, `sad` or `thinking`, and any other face SHALL become `neutral`.

#### Scenario: Confident pick
- **WHEN** Jev picks `sad` with confidence 0.74 for a character whose face is `happy`
- **THEN** the reply's face is `sad` with source `classifier`

#### Scenario: Unsure keeps the face
- **WHEN** Jev picks `angry` with confidence 0.41 for a character whose face is `thinking`
- **THEN** the reply's face is `thinking` with source `default`, and the emotion row's result is `below_threshold`

#### Scenario: A kept short face fades
- **WHEN** Jev answers `none` for a character whose face is `surprised`
- **THEN** the reply's face is `neutral` with source `default`, and the row's action says it faded

#### Scenario: Jev failed
- **WHEN** the `turn_plan` request fails for a character whose face is `embarrassed`
- **THEN** the reply's face is `neutral` with source `default`, and the row's result is `fallback`

#### Scenario: Care keeps the face calm
- **WHEN** Jev picks `happy` with confidence 0.9 for a reply whose care cue is on
- **THEN** the reply's face is `neutral`, and the emotion row's action says the care cue kept it calm

#### Scenario: Care keeps a sad pick
- **WHEN** Jev picks `sad` with confidence 0.8 for a reply whose care cue is on
- **THEN** the reply's face is `sad`
