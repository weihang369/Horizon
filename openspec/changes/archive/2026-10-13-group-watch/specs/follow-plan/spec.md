# Spec Delta

## Purpose

Decides, after a group's first reply, whether a second character speaks up: one short Jev request that sees the first
reply, with a deadline counted from `turn.end`, falling back to silence. Used by group Auto and Step in under `agent`.

## ADDED Requirements

### Requirement: When the follow plan runs
Under `agent` with a key, a follow plan SHALL start when a first reply's stream ends without an error, in group Auto with no mention or exactly one mention, and after Step in's first reply. It SHALL NOT run with two or more mentions, when every mentioned character is asleep, under policy `everyone` or `mentioned`, after a superseded send, when nobody is left to ask, or under `naive` or `scripted`.

#### Scenario: One mention may add a voice
- **WHEN** an `agent` group message mentions Hana, who answers
- **THEN** one `follow_plan` request is made after Hana's stream ends, and it does not offer Hana as a candidate

#### Scenario: Two mentions add nobody
- **WHEN** an `agent` group message mentions Hana and Rin, and both answer
- **THEN** no `follow_plan` request is made

#### Scenario: Naive keeps its up-front pick
- **WHEN** a `naive` group message gets a reply
- **THEN** no `follow_plan` request is made

### Requirement: The follow plan's question
The follow plan SHALL make one request with purpose `follow_plan`, holding the `who_second` question (a choice over the eligible cast minus everyone who already answered this message, plus `none`) and `emotion_reply` for each candidate. Its state SHALL hold the user's message, the first reply as the latest line, the 4 earlier lines and the candidates, at most 2,000 tokens, with no energy.

#### Scenario: The request's shape
- **WHEN** Hana answers a three-character `agent` group's message and the follow plan starts
- **THEN** the request has the keys `who_second`, `emotion_reply:{Rin's ID}` and `emotion_reply:{Kai's ID}`, its state's `quoted_latest` starts with "Hana:", and `quoted_message` holds the user's message

### Requirement: The deadline counts from turn.end and replaces the turn gap
The follow plan SHALL be answered by `turn.end` + the `follow_plan` deadline (400 ms by default). A second reply's `turn.next` SHALL be emitted as soon as the answer picks someone, with no turn gap before it. Without a pick, no further turn SHALL start before the turn gap after `turn.end` has passed.

#### Scenario: A quick pick
- **WHEN** Jev's follow-plan answer picks Rin with enough confidence 120 ms after the first reply's `turn.end`
- **THEN** Rin's `turn.next` is emitted at that moment, not after the 400 ms turn gap

#### Scenario: Nothing hangs on a slow Jev
- **WHEN** Jev's follow-plan answer is held for 30 seconds
- **THEN** no second reply starts, the job ends 400 ms after `turn.end`, and the late answer's ledger row has outcome `late`

### Requirement: Outcomes favour silence
A pick at or above `floor.second` SHALL give a second reply. `none`, a pick below `floor.second`, a failure, a refusal, an oversized request or a late answer SHALL give no second reply. A refused follow plan SHALL never pause the session. MULTI-03's cap of 2 replies per message SHALL hold.

#### Scenario: Unsure means silence
- **WHEN** Jev picks Rin with a confidence below `floor.second`
- **THEN** no second reply is made

#### Scenario: Never a third
- **WHEN** a follow plan's second reply completes
- **THEN** no further follow plan starts for that message

### Requirement: The second reply answers the first
A second reply SHALL use the follow plan's face for its speaker, and its turn cue SHALL carry the sentence naming the first replier. Its trace's routing SHALL hold the follow plan's question, candidates and selection, and its calls SHALL list the `follow_plan` call.

#### Scenario: The second reply's trace
- **WHEN** a follow plan picks Rin after Hana's reply
- **THEN** Rin's trace has `routing.question` "who speaks up now?", `routing.selected` Rin's ID, a `follow_plan` entry in `calls`, and its request's tail cue begins "Hana has just answered."

### Requirement: A follow plan with no pick writes to the first reply
When a follow plan picks nobody, for any reason, its System 1 rows and its call entry SHALL be appended to the first reply's trace with purpose `follow_plan`, the way after-turn rows are appended. A fallback's row SHALL say "no second reply" (with "(late)" when the deadline passed) and carry no `p`.

#### Scenario: Late follow plan in Insight
- **WHEN** a follow plan misses its deadline after Hana's reply
- **THEN** Hana's trace gains a `follow_plan` row with `result: "fallback"` and answer "no second reply (late)", and no second reply exists

### Requirement: A new user message cancels the follow plan
A user message arriving before the follow plan's answer is used SHALL cancel it: its request settles and is recorded with outcome `cancelled`, and no second reply starts for the older message.

#### Scenario: Superseded follow plan
- **WHEN** the user sends a new group message while the follow plan for the previous one is waiting for Jev
- **THEN** no second reply to the previous message appears, the follow-plan ledger row has outcome `cancelled`, and the new message is answered

### Requirement: The follow plan settles on the virtual clock
A follow plan whose answer is parked and later released SHALL let every virtual-clock advance settle, and repeated runs SHALL produce identical event logs.

#### Scenario: 100 sends settle
- **WHEN** 100 `agent` group sends run on the virtual clock with parked and released follow-plan answers
- **THEN** every advance settles without a timeout, and two runs give identical logs
