## MODIFIED Requirements

### Requirement: 1:1 conversation
In a 1:1 session, `chat.send` SHALL post the user's message and queue one reply from the single participant. `chat.regenerate(messageId)` SHALL stream a new variant into the same message, keeping earlier variants (D-58: "Continue" means regenerate). Sending to a paused 1:1 session SHALL resume it first (`session.resumed`), unless it is paused by the daily cap and the cap is still reached. Under the `agent` profile in M9, a 1:1 turn SHALL retrieve no knowledge and no memories, and a sent message SHALL start no query embedding, until the plan's gates exist.

#### Scenario: Regenerate keeps the original
- **WHEN** a completed reply is regenerated
- **THEN** the message has two variants, the new one is active, and the first variant's text is unchanged

#### Scenario: Paused 1:1 auto-resumes
- **WHEN** a 1:1 session was left (`navigated_away`) and a message is sent to it
- **THEN** a `session.resumed` event precedes the user's message, and a reply follows

#### Scenario: Agent 1:1 is quick
- **WHEN** a message is sent to an `agent` 1:1 session whose character has indexed knowledge
- **THEN** no `query_embed` ledger row is written, and the reply's trace has no `knowledge` section

### Requirement: Session settings commands
`chat.setEmotionMode`, `chat.setResponderPolicy`, `chat.setMusicPolicy` and `chat.setReadableMode` SHALL each emit one `session.state` event carrying only the changed settings. Switching the emotion mode to MANUAL SHALL drop every pending listener reaction. `chat.setEmotion` SHALL emit an `emotion` event with no `messageId` and `source: "user"`.

#### Scenario: Readable mode on
- **WHEN** `chat.setReadableMode(sid, true)` is sent
- **THEN** one `session.state` event with `settings: { readableMode: true }` is emitted, and the session reads `readableMode: true`

#### Scenario: MANUAL drops reactions
- **WHEN** `chat.setEmotionMode(sid, "user")` is sent while two reactions are pending
- **THEN** neither reaction is emitted
