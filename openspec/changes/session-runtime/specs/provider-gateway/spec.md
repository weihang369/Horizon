# Spec Delta

## ADDED Requirements

### Requirement: Scripted chat source
Paid calls made by scripted AI ports (replies, routing, verdicts, summaries) SHALL run through the same paid-call pipeline as real calls: preflight with caps and reservations, one ledger row, settle, drain only for `reply`, and emit. Their output SHALL come from an in-process source that never opens a network connection, paced on the backend clock, with usage priced from the committed price table. Their ledger rows SHALL carry `provider: "scripted"` and `cost_source: "provider"`.

#### Scenario: Scripted reply is billed and capped
- **WHEN** the scripted profile answers a 1:1 message with a key set
- **THEN** one ledger row with `category: "chat"`, `purpose: "reply"` and `provider: "scripted"` is written, the speaker's energy drops, and no network connection is opened

#### Scenario: Scripted reply refused at the cap
- **WHEN** today's spend has reached the daily cap and the scripted engine starts a reply
- **THEN** the reply is refused with `daily_budget_exceeded` before any token is produced, and `budget.reached` is published
