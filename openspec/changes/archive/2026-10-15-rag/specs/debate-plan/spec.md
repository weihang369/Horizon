# Spec Delta

## ADDED Requirements

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
