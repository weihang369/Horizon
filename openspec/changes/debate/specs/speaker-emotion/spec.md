# Spec Delta

## MODIFIED Requirements

### Requirement: Faces in group and watch come from the plan
Under `agent`, every planned group, watch and debate reply SHALL show its plan's face for its speaker, decided by the same face rule as 1:1 (the floor, keep, fade and the `neutral` + `none` merge). A second reply's face SHALL come from the follow plan, which saw the first reply. A debate rebuttal or closing SHALL take its face from the debate plan (`emotion_line` about the argument just made), an opening from its own plan (`emotion_debate_opening`), and an Ask answer from its plan (`emotion_reply`).

#### Scenario: Second replier reacts to the first
- **WHEN** a follow plan picks Rin and Jev's emotion answer for Rin is `surprised` with enough confidence
- **THEN** Rin's reply shows `surprised` with source `classifier`

#### Scenario: Everyone's prefetched replies
- **WHEN** an `agent` Everyone run prefetches its third reply
- **THEN** that reply's face is the one the run's single plan chose for that speaker

#### Scenario: A rebuttal reacts to the argument it answers
- **WHEN** the debate plan's `emotion_line` answer for Rin about Victor's argument is `angry` with enough confidence
- **THEN** Rin's rebuttal shows `angry` with source `classifier`

#### Scenario: A late face is a kept face
- **WHEN** the debate plan's answer lands after Rin's turn has started
- **THEN** Rin's rebuttal keeps her previous face (or fades it), with the fallback source
