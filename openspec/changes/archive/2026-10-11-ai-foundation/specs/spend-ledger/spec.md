## MODIFIED Requirements

### Requirement: One row per paid call
Every paid call SHALL write exactly one ledger row. The row SHALL carry:
- the contract `category` and the internal `purpose`;
- the model, the serving provider, the pricing period and the generation ID;
- the token counts (in, cached, out, and reasoning when reported);
- `cost_usd`, `estimated_cost_usd` and `latency_ms`;
- whether it counts toward a creation cap;
- the session, character, job and message references;
- how the call ended (`finish_reason`).

For a chat call, `finish_reason` SHALL be the provider's finish reason. For a decision call, it SHALL be:
- `on_time` when the answer arrived before any deadline it was read by;
- `late` when a deadline had already passed;
- `cancelled` when the decision was cancelled first;
- `final` when it was only read in full.

A call served from the response store SHALL write no row.

#### Scenario: Completed chat call
- **WHEN** a recorded chat completion returns `usage.cost: 0.00042` from provider DeepSeek off-peak with `finish_reason: "stop"`
- **THEN** one row is written with `category: "chat"`, `cost_usd: 0.00042`, `cost_source: "provider"`, `provider: "DeepSeek"`, `price_period: "off_peak"`, `finish_reason: "stop"` and a non-null `estimated_cost_usd`

#### Scenario: Late decision
- **WHEN** a decision's 400 ms deadline passes and its answer lands at 650 ms
- **THEN** its row has `finish_reason: "late"`

#### Scenario: Reasoning tokens
- **WHEN** a reply's usage reports `completion_tokens_details.reasoning_tokens: 0`
- **THEN** its row has `tokens_reasoning: 0`
