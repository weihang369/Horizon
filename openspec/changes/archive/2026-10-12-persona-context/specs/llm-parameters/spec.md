# Spec Delta

## MODIFIED Requirements

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

The `summary` row SHALL cap output at 600 tokens. `top_p`, penalties, `seed` and `logprobs` SHALL NOT be sent.

#### Scenario: Chat reply parameters
- **WHEN** a naive 1:1 reply request is sent
- **THEN** its body has `temperature: 1.3` and `reasoning: {enabled: false}`, and no `top_p`, `presence_penalty` or `frequency_penalty`

#### Scenario: Rolling summary parameters
- **WHEN** a rolling summary request is sent
- **THEN** its body has `temperature: 0.7`, `max_tokens: 600` and `reasoning: {enabled: false}`
