# llm-parameters Specification

## Purpose

LLM parameters fix how every DeepSeek call is configured (thinking, temperature, length, stop strings, JSON handling) from one committed table, and pin the one model set Horizon v1 is tuned for.

## Requirements

### Requirement: One settings row per call type
Every DeepSeek call SHALL take its thinking setting, temperature and output kind from its row in the committed `runtime.llm.calls` table:

| Key | Thinking | Temperature | Output |
|---|---|---|---|
| `reply.chat` | off | 1.3 | stream |
| `reply.debate` | off | 1.0 | stream |
| `host` | off | 1.0 | text |
| `verdict` | off | 0.7 | JSON |
| `summary` | off | 0.7 | text |
| `episode` | off | 0.7 | text |
| `memory` | off | 0.7 | JSON |
| `query_rewrite` | off | 0.0 | text |
| `profile` | off | 1.0 | JSON |
| `probe` | off | none | text |

`top_p`, penalties, `seed` and `logprobs` SHALL NOT be sent.

#### Scenario: Chat reply parameters
- **WHEN** a naive 1:1 reply request is sent
- **THEN** its body has `temperature: 1.3` and `reasoning: {enabled: false}`, and no `top_p`, `presence_penalty` or `frequency_penalty`

### Requirement: Thinking off behind a switch
A row with thinking `off` SHALL send `reasoning: {enabled: false}`, and `low` or `high` SHALL send that effort. Reasoning text SHALL never be shown or stored. A call made with thinking off that reports reasoning tokens SHALL be logged as a warning.

#### Scenario: Unexpected reasoning tokens
- **WHEN** a reply sent with thinking off reports 20 reasoning tokens
- **THEN** its ledger row records 20 in `tokens_reasoning`, and a warning is logged

### Requirement: Length target in the prompt, cap as a safety net
Reply caps SHALL be:

| Mode | `max_tokens` |
|---|---|
| 1:1 quick | 200 |
| 1:1 deep | 300 |
| group | 150 |
| watch | 150 |
| debate short / medium / long | 200 / 320 / 480 |

The cap SHALL be chosen after the turn's plan is known. The naive prompt SHALL state the mode's length target and one message per line (debate: one paragraph).

#### Scenario: Group cap
- **WHEN** a naive group reply is requested
- **THEN** its `max_tokens` is 150, and its system prompt says "Write 1–2 short messages, each on its own line, about 50 words in all."

#### Scenario: Naive is never deep
- **WHEN** a naive 1:1 turn retrieves passages
- **THEN** its `max_tokens` is 200

### Requirement: Stop sequences keep the speaker to their own lines
Every reply request SHALL send, as `stop`:
- `"\n<Name>:"` for every other participant;
- `"\n<You name>:"`;
- `"\n[<kind>]"` for each non-character line kind in the history.

It SHALL never send a bare `"\n["`, and never more than 16 strings. A leading `<own name>:` SHALL be removed from the reply before or after the emotion tag, before any text is shown.

#### Scenario: Own name stripped
- **WHEN** Takeshi's reply streams `Takeshi: <e:happy>Morning!`
- **THEN** the face is `happy`, and the shown text is `Morning!`

#### Scenario: Group stop list
- **WHEN** Mei replies in a group with Hana and Rin, and the user is named Kai
- **THEN** the request's `stop` contains `"\nHana:"`, `"\nRin:"` and `"\nKai:"`, and not `"\nMei:"`

### Requirement: A history never ends on the speaker's own line without a cue
When the rendered history's last line is the speaker's own, and no other turn cue applies, the reply request SHALL end with a cue asking for the speaker's next message.

#### Scenario: Speaker spoke last
- **WHEN** a group reply is requested for Hana, and the last history line is Hana's
- **THEN** the request's last message is a system cue asking for her next message

### Requirement: An empty reply is retried once before anything shows
When a reply stream ends normally with no visible text, the engine SHALL send the same request once more, with the trailing cue added if it was missing, before any event of that turn is emitted. If the second reply is also empty, the turn SHALL end with a retryable `provider_error` and no message. Both calls SHALL keep their ledger rows.

#### Scenario: First reply empty
- **WHEN** the first stream ends with `finish_reason: stop` and no content, and the second streams `<e:happy>Hi`
- **THEN** one message `Hi` with emotion `happy` exists, and two `reply` ledger rows carry its message ID

#### Scenario: Both empty
- **WHEN** both streams end with no content
- **THEN** no message is created, an `error` event with `provider_error` is emitted, and two ledger rows exist

### Requirement: JSON calls repair locally, then retry once
Every DeepSeek call that returns JSON SHALL:
1. send JSON mode, with a prompt line asking for single quotes inside text values;
2. validate the result;
3. on failure, apply a free local repair of unescaped inner quotes, and validate again;
4. on failure, retry once, with the validation error appended;
5. on a second failure, use the port's existing failure path.

Only parse or validation failures SHALL retry. A creation task's `cost_usd` SHALL be the sum of its calls.

#### Scenario: Nickname in double quotes
- **WHEN** the drafter's answer contains `"name": "Loretta "Rhett" Kowalski"`
- **THEN** the local repair makes it valid, no second call is sent, and the draft's name is `Loretta "Rhett" Kowalski`

#### Scenario: Retry costs add up
- **WHEN** a draft's first answer is unrepairable and the retry is valid, costing $0.0009 and $0.0010
- **THEN** two `profile` ledger rows exist, and the task's `cost_usd` is $0.0019

### Requirement: Tuned for one model set
Every chat call SHALL use the pinned chat model from the price table, and no fallback model SHALL be sent. Settings → Models SHALL be a read-only "Models in use" panel. Each role row SHALL show its model, its purpose, its price from the bundled price table, and a Test button, with the line "Tuned for these models. Custom models are planned for v2." Stored model overrides SHALL be ignored.

#### Scenario: No model list
- **WHEN** any chat request is sent
- **THEN** its body has no `models` field

#### Scenario: Read-only panel
- **WHEN** the user opens Settings → Models
- **THEN** no model ID is editable, and each role shows its price and a Test button
