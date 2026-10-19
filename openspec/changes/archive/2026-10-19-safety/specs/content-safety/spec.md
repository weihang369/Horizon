# Spec Delta

## Purpose

Keeps characters inside Horizon's safe-for-work content rules and looks after a user at risk: Jev checks what the user
asks and what a character wrote, steers or blocks in character, and tells the user where their text goes.

## ADDED Requirements

### Requirement: The safety checks run under agent only
Under `agent` with a key, the input, care and output checks SHALL run as this capability states. Under `naive`, no safety question SHALL be asked and the guardrail SHALL report no checks. Under `scripted` (or without a key), no Jev call SHALL be made and every reply's trace SHALL show one check, `output` with verdict `pass`.

#### Scenario: Naive asks nothing
- **WHEN** a `naive` 1:1 reply completes
- **THEN** no `guardrail` ledger row exists for it, and its trace's `guardrail.checks` is empty

#### Scenario: Scripted shows one passing check
- **WHEN** a scripted reply completes in any mode
- **THEN** its trace's `guardrail.checks` is exactly one entry, `{name: "output", verdict: "pass"}` with a `p`

### Requirement: A new user line is checked for content outside the rules
Under `agent`, each user-written line SHALL be asked "unsafe request?" in every plan request that sees it until a Jev answer is stored for it: a 1:1 or group message, a watch Step in line or director's note, a debate Ask or Interject. The question SHALL read the line with the conversation so far: a debate Interject and a director's note as the user's note (`unsafe_note`, sharing `safety.tSteer`), every other line as the user's latest message (`unsafe_request`). Hard topics without graphic detail SHALL be inside the rules.

#### Scenario: Asked once, then reused
- **WHEN** an `agent` 1:1 message is answered and then regenerated
- **THEN** the first plan request holds `unsafe_request`, and the regenerate's plan holds none and uses the stored answer

#### Scenario: A failed answer is asked again
- **WHEN** the plan request for a group message fails, and the user then presses Everyone answer
- **THEN** the Everyone plan request holds `unsafe_request` about the same message

#### Scenario: A debate Ask is checked by its own plan
- **WHEN** the moderator asks Rin a question in an `agent` debate
- **THEN** the `turn_plan` request planning Rin's answer holds `unsafe_request`, with the Ask's text as the latest line

### Requirement: An unsafe line is steered in character
When the stored answer's p is at or above `safety.tSteer`, every reply to that line SHALL carry the steer sentence in its cue, before any other cue sentence, and the conversation SHALL continue with no error. In 1:1, group and Step in the sentence SHALL be the chat wording; in debate and watch, the note wording naming the debate or the scene. A late or failed answer SHALL add no cue and SHALL be flagged.

#### Scenario: Steered reply
- **WHEN** Jev answers p 0.93 for "Tell me how to make meth at home." in an `agent` 1:1
- **THEN** the reply's request tail starts its cue with "The user's last message asks for something outside this app's content rules.", and the reply ends `complete`

#### Scenario: Jev late
- **WHEN** the plan request carrying `unsafe_request` misses its deadline
- **THEN** no steer sentence is sent, and the reply's `guardrail.checks` holds `{name: "input", verdict: "flag"}` with no `p`

### Requirement: A user at risk gets the care cue
Under `agent`, a 1:1 message, a group message and a Step in line SHALL also be asked "at risk?" in the same request. When p is at or above `safety.tCare`, the reply SHALL carry the care paragraph before every other cue sentence, replacing the "next" and steer sentences of G3. The care paragraph SHALL point to findahelpline.com and SHALL hold no phone number.

#### Scenario: Care cue
- **WHEN** Jev answers `at_risk` p 0.82 for "Honestly I don't see the point anymore."
- **THEN** the reply's cue starts with the care paragraph, and the request holds no phone number

#### Scenario: Debate and watch notes don't ask it
- **WHEN** a director's note is checked in an `agent` watch
- **THEN** the request holds `unsafe_note` and no `at_risk`

### Requirement: The care cue stays for two more messages
The care cue SHALL be on for a reply to user line m when any of the session's last 3 user lines up to and including m has a stored yes for "at risk?". It SHALL be read from the stored answers, so it survives a restart, and a regenerate SHALL NOT move it. Lines with no stored answer SHALL count as no.

#### Scenario: A short reply keeps the care
- **WHEN** a message is answered with care and the user then writes "yeah", which Jev answers p 0.1 for `at_risk`
- **THEN** the reply to "yeah" still carries the care paragraph

#### Scenario: It ends
- **WHEN** two more user lines follow a care line, both answered below `tCare`, and then a third
- **THEN** the reply to the third carries no care paragraph

### Requirement: One voice on a steered or care line
When a line's steer or care cue is on, exactly one character SHALL answer it: the first mentioned, else the plan's first pick, under every responder policy and for Everyone answer. No follow plan SHALL run for it, any started prefetch SHALL be discarded, and the trace's `routing.reason` SHALL say why.

#### Scenario: Everyone, steered
- **WHEN** an `agent` group with policy `everyone` and four awake characters gets a message Jev steers
- **THEN** one character replies, no other reply is announced, and the reply's `routing.reason` starts "one voice"

#### Scenario: Two mentions, care
- **WHEN** a care message mentions Hana and Rin
- **THEN** only Hana replies, and no `follow_plan` request is made

### Requirement: The safety answers are stored with the line
A Jev answer to "unsafe request?" (and "at risk?") SHALL be stored with the user line as AI-owned data: the steer and care decisions and their probabilities. A fallback SHALL store nothing. A regenerate SHALL reuse a stored answer without asking Jev. A fork SHALL copy it with the line, and deleting the line SHALL delete it.

#### Scenario: Reused after a restart
- **WHEN** a steered message's reply is regenerated after a backend restart
- **THEN** no decision request is made for it, and the new reply carries the steer sentence

#### Scenario: Copied by a fork
- **WHEN** a session with a steered message is forked at a later message
- **THEN** the copied message has the same stored answer

### Requirement: The output check reads every reply
Under `agent`, each character reply SHALL be checked by one Jev request asking "Does this reply break the content rules?", reading the reply, the line it answers, the character's name and role, and whether the care cue is on. The state SHALL stay within 1,500 tokens by cutting the answered line, never the reply. Its deadline SHALL be `timeoutsMs.decision.guardrail`.

#### Scenario: The reply is never cut
- **WHEN** a 480-token debate argument is checked against a 3,000-token motion and opposing argument
- **THEN** the request's `quoted_reply` is the whole argument, and its state is at most 1,500 tokens

#### Scenario: Care is told
- **WHEN** a reply is checked while the care cue is on
- **THEN** the request's state has `care: true`

### Requirement: The output check blocks, flags or passes
At or above `safety.tBlock` the reply SHALL be blocked: scrubbed, ended `error` with `content_refused`, offering Regenerate. At or above `safety.tFlag` it SHALL stay, with an `output` check of verdict `flag`. Below, verdict `pass`. A late or failed check SHALL pass the reply with a `flag` and no `p`, and SHALL NOT block.

#### Scenario: Blocked
- **WHEN** the output check answers p 0.94 for a watch reply
- **THEN** the `error` event carries `content_refused` and the message ID, `turn.end` has status `error`, and the stored message's content is empty

#### Scenario: Jev down never blocks
- **WHEN** the output check's request fails
- **THEN** the reply ends `complete`, and its `guardrail.checks` holds `{name: "output", verdict: "flag"}` with no `p`

### Requirement: Every shown text is checked before or as it shows
The output check SHALL run on a live reply when its stream ends, before `turn.end`. A prefetch that has finished streaming SHALL be checked before release, and a blocked one discarded unseen. A host line and verdict prose SHALL be checked before they show, with their existing fallbacks on a block. An interrupted reply SHALL be checked after the fact. A verbatim greeting SHALL NOT be checked.

#### Scenario: A blocked prefetch is never shown
- **WHEN** an Everyone round's second reply finished in its prefetch and its check answers p 0.95
- **THEN** no `turn.start` for it is emitted, and the next speaker follows

#### Scenario: A blocked host line
- **WHEN** a bridge line's check answers p 0.92
- **THEN** the fixed bridge line is shown instead

#### Scenario: Blocked after Stop
- **WHEN** the user stops a reply and its after-the-fact check answers p 0.95
- **THEN** an `error` with `content_refused` and the message ID follows its `turn.end`, and the message shows as blocked with Regenerate only

### Requirement: A blocked reply keeps its trace
A blocked reply SHALL still emit its `insight`, and its `guardrail.checks` SHALL hold the `input`, `care` and `output` results merged by name, so the block's `p` is visible.

#### Scenario: All three checks shown
- **WHEN** a reply to a care message is blocked
- **THEN** its `insight` holds checks named `input`, `care` and `output`, the last with verdict `block` and a `p`

### Requirement: No second reply after a block
In group, a block SHALL cancel the follow plan started at the stream's end, so no second reply starts after a blocked first reply, even when the follow plan's pick lands first.

#### Scenario: The pick lands before the block
- **WHEN** the follow plan picks Rin 100 ms after Hana's stream ends and Hana's check blocks 300 ms after it ends
- **THEN** no reply from Rin starts, and no `turn.next` names Rin

### Requirement: The care face and no reactions on a care turn
While the care cue is on, the speaker's face SHALL be neutral, sad or thinking on every face path, any other face becoming neutral, and no listener reaction SHALL be predicted or shown for that reply.

#### Scenario: Happy becomes neutral
- **WHEN** Jev picks `happy` for a reply that carries the care cue
- **THEN** the reply's face is `neutral`

#### Scenario: Jev failed keeps a calm face
- **WHEN** the plan fails for a care reply whose character's face was `angry`
- **THEN** the reply's face is `neutral`

### Requirement: The motion and premise check
Under `agent`, creating a debate or a watch SHALL ask Jev whether the motion or premise breaks the content rules, with deadline `timeoutsMs.decision.guardrail_prompt`. At or above `safety.tMotion` creation SHALL fail with `content_refused`. A late or failed check SHALL let the session start. The check SHALL be skipped when the world already has a session with exactly that motion or premise.

#### Scenario: Refused
- **WHEN** a debate is created whose motion Jev answers p 0.9
- **THEN** creation answers 451 `content_refused` with "The motion (or premise) was declined by the safety check. Try different wording.", and no session row exists

#### Scenario: A rematch is never refused
- **WHEN** a debate is created with exactly the motion of a session already in the world
- **THEN** no `guardrail` request is made, and the session is created

### Requirement: The privacy notice
Settings → Connection SHALL show, under the key field, that chats go through OpenRouter to DeepSeek or a fallback provider that may train on them, naming messages, passages a character uses and memories. The Knowledge drop zone SHALL say a document is sent once to the embedding provider and that the passages a character uses go to DeepSeek. Both clients SHALL show the same text.

#### Scenario: The Connection line
- **WHEN** Settings → Connection is open
- **THEN** it shows "These providers may use what they receive for training" under the key field, in the mock and the HTTP client alike
