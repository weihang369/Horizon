## MODIFIED Requirements

### Requirement: When the follow plan runs
Under `agent` with a key, a follow plan SHALL start when a first reply's stream ends without an error, in group Auto with no mention or exactly one mention, and after Step in's first reply. It SHALL NOT run with two or more mentions, when every mentioned character is asleep, under policy `everyone` or `mentioned`, after a superseded send, when nobody is left to ask, when the message's steer or care cue is on, or under `naive` or `scripted`. A block of the first reply by the output check SHALL cancel it.

#### Scenario: One mention may add a voice
- **WHEN** an `agent` group message mentions Hana, who answers
- **THEN** one `follow_plan` request is made after Hana's stream ends, and it does not offer Hana as a candidate

#### Scenario: Two mentions add nobody
- **WHEN** an `agent` group message mentions Hana and Rin, and both answer
- **THEN** no `follow_plan` request is made

#### Scenario: Naive keeps its up-front pick
- **WHEN** a `naive` group message gets a reply
- **THEN** no `follow_plan` request is made

#### Scenario: A steered message gets one voice
- **WHEN** an `agent` group message with no mention is steered, and Hana answers
- **THEN** no `follow_plan` request is made

#### Scenario: A blocked first reply
- **WHEN** Hana's first reply is blocked by the output check after the follow plan has started
- **THEN** the follow plan is cancelled, and no second reply starts
