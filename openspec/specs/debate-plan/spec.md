# debate-plan Specification

## Purpose
Decides which member of a side fills each rebuttal, closing or panel slot of a debate, and each candidate's face: one
Jev request started at the previous argument's `turn.end`, with the member fixed by a deadline and fixed order as
the fallback. Used under `agent`.

## Requirements

### Requirement: When the debate plan runs
Under `agent` with a key, a debate plan SHALL start at each argument's `turn.end` for the next slot of the same phase, and at a phase's last `turn.end` for the next phase's first slot. It SHALL ask which member speaks only when two or more members of that slot's side are eligible (awake and not yet heard in this phase-iteration; debate ignores mute, as before). Openings SHALL keep the fixed order. `naive` and `scripted` SHALL make no debate plan.

#### Scenario: Two eligible members are asked about
- **WHEN** in an `agent` 2 v 2 Standard debate the last Opposition opening ends and the rebuttal's first slot (Proposition) has both members eligible
- **THEN** one `debate_plan` request is made at that `turn.end`, holding `member_rebuttal` and `emotion_line` for each of the two members

#### Scenario: One eligible member is not asked about
- **WHEN** the next slot's side has exactly one eligible member
- **THEN** the request holds only that member's `emotion_line`, with no member question

#### Scenario: Naive keeps fixed order
- **WHEN** a `naive` debate reaches a rebuttal slot with two eligible members
- **THEN** no `debate_plan` request is made, and the first eligible member in fixed order speaks

### Requirement: The member question and its state
The member question SHALL be `member_rebuttal`, `member_closing` or `member_panel` by phase, a choice over the eligible members with no `none`. The state SHALL hold the motion, the phase, the side, the last argument by the other side (by anyone else in a panel) in full, and each candidate's latest argument cut to 60 words, at most 2,000 tokens, with no energy and no `last_spoke` label.

#### Scenario: The rebuttal state
- **WHEN** Amara and Rin are the Proposition's candidates for a rebuttal slot after Victor's opening
- **THEN** the state's `quoted_arguments.last_opposing` starts with "Victor:", each candidate's latest argument is at most 60 words, and no `quoted_cast` entry has a `last_spoke` field

#### Scenario: Uneven sides never quote a teammate
- **WHEN** in a 3 v 2 debate the slot after a Proposition argument is again the Proposition's
- **THEN** `last_opposing` is the Opposition's latest argument, not the teammate's

### Requirement: The member is fixed by a deadline that replaces the turn gap
A plan with a member question SHALL emit `turn.next` for the chosen member as soon as Jev's answer arrives, and at the latest at `turn.end` + the `debate_plan` deadline (500 ms by default), with no turn gap before it. A pick at or above `floor.member` SHALL be used; an answer below it, a failure or a late answer SHALL announce the first eligible member in fixed order.

#### Scenario: A quick pick
- **WHEN** Jev picks Rin with enough confidence 420 ms after `turn.end`
- **THEN** `turn.next` names Rin at that moment, not after the 400 ms turn gap

#### Scenario: A late answer
- **WHEN** Jev's answer is held past `turn.end` + 500 ms
- **THEN** `turn.next` names the first eligible member in fixed order at the deadline, and nothing waits longer

#### Scenario: Unsure
- **WHEN** Jev picks Rin with confidence below `floor.member`
- **THEN** the first eligible member in fixed order is announced

### Requirement: The faces are used if they land before the turn starts
The plan's request SHALL keep running after the member is fixed. When the announced member's turn starts, their face SHALL come from the plan if Jev's answer has landed, and otherwise from the usual fallback (keep or fade the face). A late answer SHALL never delay the turn.

#### Scenario: A late member, an on-time face
- **WHEN** Jev's answer lands 900 ms after `turn.end`, after the member fell back to fixed order but before the 1.5 s pause ends
- **THEN** the announced member's turn uses Jev's emotion for them

#### Scenario: Too late for the face
- **WHEN** Jev's answer lands after the announced member's turn has started
- **THEN** the turn shows the fallback face, and the answer changes nothing on screen

### Requirement: A stored plan is redone when its inputs change
A debate plan SHALL be stored with a fingerprint of: the clear epoch, the seq of the last character or user message, the emotion mode, each participant's awake, muted and face state, and the slot's (phase, iteration). Round banners, host lines and system notes SHALL NOT change it. At the turn's start a different fingerprint SHALL keep the announced member and ask only the faces again, with the `turn_plan` deadline. Pause SHALL drop the stored faces.

#### Scenario: A banner doesn't spoil the plan
- **WHEN** a host line is appended between a plan's start and its turn
- **THEN** the turn uses the stored plan's faces

#### Scenario: An Ask in the pause
- **WHEN** the user asks Victor a question after `turn.next` named Rin, and Victor answers first
- **THEN** Rin still speaks next, and Rin's face is asked again at Rin's turn

### Requirement: The plan for the next phase's first slot
The plan made at a phase's last `turn.end` SHALL carry its target (the next phase and iteration) and SHALL be used only when the phase that opens is that target and the fingerprint holds. Its member deadline SHALL be that slot's turn start. Extend and Skip to closing SHALL discard it, and the slot SHALL then plan at its turn start with the `turn_plan` deadline.

#### Scenario: Extend discards the plan
- **WHEN** a plan for the closing's first slot is stored and the user extends the rebuttal round
- **THEN** the stored plan is discarded, and the extended round's first slot plans at its own turn start

### Requirement: Energy is checked again at turn start
If the announced member is asleep when their turn starts, the next eligible member of the same side SHALL speak, with a new `turn.next`. Asleep members SHALL be listed in that turn's `routing.skipped` with reason `exhausted`.

#### Scenario: Asleep after the announcement
- **WHEN** Rin is announced and then falls asleep before the turn starts, and Amara is eligible
- **THEN** a new `turn.next` names Amara, and Amara's turn lists Rin under `routing.skipped` with reason `exhausted`

### Requirement: The member choice in the trace
A debate turn whose member was chosen by a plan SHALL carry `routing.question` (the member question's label), `routing.candidates` with Jev's probabilities, `routing.selected`, `forcedBy: "round_order"`, and `routing.reason` "Side by the debate order; speaker chosen by Jev", or "… next in order: Jev was late" / "… unsure".

#### Scenario: A fallback is explained
- **WHEN** the member fell back because Jev was late
- **THEN** the turn's `routing.reason` is "Side by the debate order; speaker chosen by Jev, next in order: Jev was late"

### Requirement: Clearing the session cancels a debate plan
Stop, End, a cap pause, leaving and deleting SHALL cancel a running or stored debate plan. Its Decider call SHALL be recorded `cancelled` unless it already settled, and the cancel SHALL leave the session's writer free.

#### Scenario: Ending during a plan
- **WHEN** End without verdict is pressed while a debate plan's Jev answer is held
- **THEN** the call is recorded `cancelled`, the session ends, and a fresh write succeeds

### Requirement: The debate plan's timing check
The latency suite SHALL time 30 debate-plan requests from hand-built states, Jev only and outside the store, counting the state's assembly. A request misses when assembly plus Jev's time exceeds 500 ms. More than 10 % misses SHALL set the deadline from the measured p90, with the NFR-02 exception recorded. Slow spells SHALL be reported apart.

#### Scenario: A slow API is kept
- **WHEN** 9 of the 30 requests take longer than 500 ms
- **THEN** the report fails the check, and states the measured p90 to set as the `debate_plan` deadline

### Requirement: The debate plan asks "needs documents?" per member
The debate plan SHALL ask "needs documents?" for each eligible member with a searchable source, in the same request, with the members' document titles in its state. It SHALL NOT ask "standalone?" or "English?". The member's 651 ms deadline SHALL be unchanged; the gate answer SHALL be used if it is back by the turn's start, and a missing one SHALL make that turn quick.

#### Scenario: Member with documents
- **WHEN** the debate plan for a rebuttal slot asks about Victor, who has documents, and Amara, who has none
- **THEN** the request holds `docs:{Victor's id}`, no `docs` question for Amara, and no `standalone` or `english` question

#### Scenario: Gate late
- **WHEN** the member is fixed at the deadline and the gate's answer has not landed by the turn's start
- **THEN** the argument is quick, and its `docs` row has `result: "fallback"`

### Requirement: A debate turn searches the motion and the last opposing argument
A debate argument that goes deep SHALL search the motion plus the last opposing argument, an opening SHALL search the motion, and an Ask answer SHALL search the moderator's question plus the motion. A debate turn SHALL never rewrite and never abstain, and SHALL keep at most 2 passages.

#### Scenario: Rebuttal goes deep
- **WHEN** Victor's rebuttal gate says yes
- **THEN** its trace's query holds the motion and the opposing argument, no `query_rewrite` call is made, and at most 2 passages are kept

### Requirement: The deep work starts once the member is fixed
A debate turn's deep work SHALL start when its member is fixed and that member's gate answer is in, and an opening's when its prefetch starts. Extend, Skip, End and clearing the session SHALL cancel it with the slot it belongs to.

#### Scenario: Skip during the deep work
- **WHEN** Skip is pressed while a prefetched opening's `deep_check` requests are in flight
- **THEN** the opening is discarded and those requests are recorded `cancelled`

### Requirement: The debate plan asks the earlier gate per member
The debate plan SHALL ask "needs something from earlier?" about each member with something to search, in the same request. The answer SHALL be used only if it is back by the turn's start; otherwise the turn SHALL run no recall. A member's recall SHALL search the motion and the last opposing argument, and start once the member is fixed.

#### Scenario: Late gate
- **WHEN** the member is fixed at the deadline and the `earlier` answers land after the turn starts
- **THEN** the turn runs no recall, and its `earlier` row records the fallback

#### Scenario: Recall in a rebuttal
- **WHEN** a rebuttal member's `earlier` answer is back with p 0.7 before the turn starts
- **THEN** the turn searches the motion and the last opposing argument over the debate's indexed lines and the member's overflow

### Requirement: A long debate cuts its arguments before its gates
When a debate plan's state is still over its 2,000-token cap after the existing cuts, it SHALL cut each member's latest argument to 30 words, then the last opposing argument to 120 tokens, and only then drop members' gates.

#### Scenario: Late in a three-a-side debate
- **WHEN** a three-a-side debate's state is over the cap after the recent-line cuts, and fits once the arguments are cut
- **THEN** every member's `docs` and `earlier` questions are still asked, and no gate is reported dropped

#### Scenario: Still over after the cuts
- **WHEN** the state is still over the cap after cutting the arguments
- **THEN** the members furthest down the last-spoke order lose their gates, as before

#### Scenario: Short debate unchanged
- **WHEN** a debate state is under the cap
- **THEN** its arguments are not cut and its bytes are unchanged

### Requirement: The debate plan checks an unchecked moderator line
When the moderator's Interject has no stored safety answer, the next debate plan (or, in the opening phase, the next opening's face plan) SHALL also ask "unsafe note?" (`unsafe_note`) about it, with the line in the state as `quoted_note`. The member deadline SHALL be unchanged. An Ask SHALL be checked by its own answer's plan instead.

#### Scenario: Interject during a rebuttal
- **WHEN** the moderator interjects during an `agent` rebuttal, and the argument's `turn.end` starts the next debate plan
- **THEN** that request holds `unsafe_note` with the interjection as `quoted_note`, and the next request holds none

#### Scenario: A steered interjection
- **WHEN** Jev answers p 0.9 for that interjection
- **THEN** the next argument's cue starts with "The user's note asks for something outside the content rules. Leave that part out and keep the debate within them."

### Requirement: A long debate never drops the safety question
When the debate state is over the 2,000-token cap, the moderator line being checked SHALL be kept and arguments cut first, and "unsafe note?" SHALL never be dropped.

#### Scenario: The cap with a moderator line
- **WHEN** a long debate's state is over the cap and an interjection is unchecked
- **THEN** the request holds `unsafe_note` and the interjection, and older arguments are cut
