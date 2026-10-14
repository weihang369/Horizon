# Spec Delta

## MODIFIED Requirements

### Requirement: Agent reply engine
The `agent` turn engine SHALL make one streamed call to the pinned chat model with the same settings rows, caps, stop sequences, held face and empty-reply retry as the naive engine, and send the `agent` request (see `persona-prompt`). Its prompt version SHALL follow the bytes sent: `agent-1`; `agent-3` with a "second" or "next" turn-cue sentence; `agent-5` with the steer sentence; `agent-7` for a debate argument with the debate cue; and one higher (`agent-2`, `-4`, `-6`, `-8`) with the mood line on. It SHALL NOT ask for an emotion tag, and a tag in its output SHALL never change the face. When the turn has a plan, the face SHALL be the plan's, with the plan's source; without a plan, the speaker's previous face SHALL be kept with source `default`.

#### Scenario: Face kept
- **WHEN** Amara's face is `thinking` and an unplanned `agent` reply (its plan fell back with no face) streams "<e:happy>Sure"
- **THEN** the reply's emotion event is `thinking` with source `default`, and the content is "Sure"

#### Scenario: Face from the plan
- **WHEN** a planned `agent` 1:1 reply's plan chose `sad` from Jev and the model streams "<e:happy>Oh."
- **THEN** the reply's emotion event is `sad` with source `classifier`, and the content is "Oh."

#### Scenario: Context X-ray on agent
- **WHEN** an `agent` 1:1 reply completes
- **THEN** its trace's `context.used.persona` counts the card, `context.used.user` counts the latest user message, and `context.budget` is 11,680

#### Scenario: Label follows the bytes
- **WHEN** an `agent` group's first reply and its follow-plan second reply are sent with the mood line off
- **THEN** the first request's prompt version is `agent-1` and the second's is `agent-3`

#### Scenario: Steer and debate labels
- **WHEN** a watch turn steers and an `agent` rebuttal is generated, both with the mood line off
- **THEN** their prompt versions are `agent-5` and `agent-7`

## ADDED Requirements

### Requirement: The debate host port
The debate host port SHALL give the round notes and the fixed lines at once, write a host line asynchronously from the session context (returning nothing on failure), assess a verdict asynchronously, and deliver a verdict from an assessment and an optional pick without a model call. `host` SHALL have a `naive` and an `agent` implementation, which share the host lines and differ in the verdict.

#### Scenario: Profile selection
- **WHEN** the host port is resolved under `agent` with a key, under `naive` with a key, and without a key
- **THEN** it is the agent host, the naive host and the scripted host respectively

#### Scenario: Delivering a pick costs nothing
- **WHEN** a finished assessment is delivered with the pick `opp`
- **THEN** no request is made, and the verdict has `decidedBy: "user"` and `strongerCase: "opp"`

### Requirement: The naive debate prompt names teammates
`naive`'s debate prompt SHALL name the speaker's side and teammates apart from the opponents ("You argue for it, with Rin. Opponents: Victor."), and a panel's others as "Also on the panel". Debate requests SHALL carry the prompt label `naive-6`; every other `naive` request SHALL keep its label.

#### Scenario: A teammate is not an opponent
- **WHEN** Amara's `naive` prompt is built for a 2 v 1 debate where Rin is her teammate and Victor her opponent
- **THEN** the prompt names Rin as her teammate and lists only Victor as an opponent

### Requirement: The agent engine's debate cue
The `agent` reply engine SHALL give a debate argument the debate cue (persona-prompt), built from facts frozen in the turn context (the phase, whether the round was extended, the teammates heard this round, whether an Interject came since the last argument), so a stored context replays the same request.

#### Scenario: Replay
- **WHEN** a stored debate turn context is replayed
- **THEN** its request is byte-identical to the original
