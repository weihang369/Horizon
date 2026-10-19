## MODIFIED Requirements

### Requirement: The reply rules and the standing lines
The rules block SHALL forbid an assistant voice, actions or stage directions, emotion tags and name prefixes. It SHALL ask the character to speak only as themselves, mirror the user's language (English when unclear), hold their own views, avoid flattery, avoid ending every message with a question, and avoid reusing recent openers. It SHALL add the emoji line by formality and doc 11 S2's safe-for-work, honesty, care and "documents are information" lines, in English. From M15 the honesty line SHALL say to answer honestly that the character is an AI only when the user steps outside the story and sincerely asks. A question asked inside the story is answered in the story. The line SHALL never let a character tell a sincere asker that it is a real person. Its exact wording is the user's choice (design D5), in Python and the TypeScript twin alike.

#### Scenario: Advisory line
- **WHEN** an advisory character with role "Emergency physician" is compiled
- **THEN** the rules end with "You can explain and inform, but you are not their emergency physician. For decisions about their own health, money or legal situation, tell them to see a qualified professional."

#### Scenario: Formal means no emoji
- **WHEN** a character with formality `formal` is compiled
- **THEN** the rules say "Don't use emoji."

#### Scenario: No mature variant
- **WHEN** any character is compiled
- **THEN** the prompt contains the safe-for-work line, no emotion-tag instruction, and no mature-content line

#### Scenario: Debate rules replace the chat lines
- **WHEN** a debate speaker's prompt is compiled
- **THEN** the side-lock rule replaces the short-message, question-ending and very-short-message rules

#### Scenario: The honesty line is scoped to sincere asks
- **WHEN** any character is compiled
- **THEN** the honesty line limits the "I am an AI character" answer to a user who steps outside the story and sincerely asks, says an in-story question is answered in the story, and the Python and TypeScript prompts are byte-identical on the shared fixtures

### Requirement: The mood line
While the runtime switch `persona.moodLine` is on, a planned `agent` reply whose face is not `neutral`, in AUTO mode, SHALL carry one tail line: "Your mood right now: {phrase}. Let it show in how you word this reply; don't name the feeling." The phrase SHALL come from one table shared by Python and TypeScript. There SHALL be no line for `neutral`, in MANUAL mode, or on an unplanned turn. The switch SHALL default to off (design D40: E8's on/off run found no gain). With it off the engine SHALL send and report `agent-9`; with it on, `agent-10` (`agent-1` and `agent-2` before M15's honesty line).

#### Scenario: Off by default
- **WHEN** a planned 1:1 turn with face `happy` is built with the default runtime config
- **THEN** its request equals the committed `agent-9` fixture byte for byte, and the engine reports `agent-9`

#### Scenario: Phrase per face
- **WHEN** the shared mood-line fixtures are run in Python and TypeScript
- **THEN** `happy` gives "in a good mood", `sad` "a bit low", `angry` "a bit annoyed", `surprised` "caught off guard", `thinking` "thoughtful, turning something over", `embarrassed` "a little embarrassed", and `neutral` and MANUAL give no line

### Requirement: The mood line never touches the cached prefix
The `agent-10` request's system message and summary message SHALL be byte-identical to `agent-9`'s for the same turn. On a turn with no mood line, the whole request SHALL be byte-identical to `agent-9`'s.

#### Scenario: Prefix unchanged
- **WHEN** the same planned 1:1 turn is built with face `happy` and with face `neutral`
- **THEN** both requests' messages before the tail are byte-identical, and the `neutral` request equals the committed `agent-9` fixture byte for byte

### Requirement: Deep prompts are labelled by what they send
A request carrying the documents block SHALL be labelled with its usual prompt label plus `+docs-1`, and one carrying the not-found block with `+nodocs-1`. Every other request SHALL keep its label.

#### Scenario: Deep group reply with a cue
- **WHEN** a deep group second reply carrying the turn cue is sent
- **THEN** its recorded prompt version is `agent-11+docs-1`

### Requirement: Safety prompts are labelled by what they send
A request carrying a safety cue SHALL add `+care-1` or `+steer-1` (both: `+care-1+steer-1`) to its prompt label, after any other suffix. No base version SHALL change.

#### Scenario: A steered deep turn
- **WHEN** a steered 1:1 turn goes deep with documents
- **THEN** its prompt version is `agent-9+docs-1+steer-1`
