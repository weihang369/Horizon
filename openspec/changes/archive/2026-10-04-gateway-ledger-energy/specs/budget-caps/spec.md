# Spec Delta

## Purpose

Keeps spending inside the user's caps (NFR-07, NFR-30). Before any spend, each paid call is checked against the daily cap and the per-character creation cap, counting calls still in flight. The user is warned as a cap is crossed, and spend is blocked once a cap is reached.

## ADDED Requirements

### Requirement: Calls in flight are reserved
Each paid call's preflight SHALL reserve its estimate in an in-memory reservation book, and settling the call SHALL release it, whether the call succeeded or failed. A multi-step job SHALL be able to reserve its whole remaining estimate up front and release it step by step. The reservation book SHALL be empty after a restart.

#### Scenario: Two calls in flight
- **WHEN** two calls with $0.30 estimates are in flight under a $1.00 daily cap with $0.30 spent
- **THEN** a third call with a $0.30 estimate is refused with `daily_budget_exceeded`

#### Scenario: Job-wide reservation
- **WHEN** a job reserves $0.09 for five steps and completes two of them
- **THEN** the reservation still held for that job equals the estimate of the three remaining steps

### Requirement: Daily cap
A paid call SHALL be refused when `spentTodayUsd + reserved + estimate > dailyCapUsd`. The refusal SHALL be 402 `daily_budget_exceeded`, and `budget.reached { scope: "daily" }` SHALL be published on the global stream. "Today" SHALL be the local date in `HORIZON_TZ`.

#### Scenario: Cap reached
- **WHEN** $0.999 has been spent under a $1.00 cap and a call estimated at $0.002 is made
- **THEN** it rejects with `daily_budget_exceeded` before sending, and global subscribers receive `budget.reached` with `scope: "daily"`, `spentUsd: 0.999` and `capUsd: 1`

### Requirement: Creation cap
While a character is not approved, a call that counts toward its creation cap SHALL be refused when `creationSpent + reservedFor(character) + estimate > perCharacterCreationCapUsd`, with 402 `creation_budget_exceeded`. Calls for approved characters SHALL NOT count toward the creation cap.

#### Scenario: Draft over its creation cap
- **WHEN** a draft character has spent $0.59 of a $0.60 creation cap and an $0.018 image is requested
- **THEN** it rejects with `creation_budget_exceeded`, and nothing is sent

### Requirement: Warning on crossing
After a call is recorded, `budget.warning` SHALL be published exactly when that call moves spend across the warning line: `before < warnAt ≤ after`, where `warnAt = cap × warnAtPct / 100`, for the daily scope or a character's creation scope. No flag SHALL be stored.

#### Scenario: Crossing 80 %
- **WHEN** under a $1.00 cap with `warnAtPct` 80, spend moves from $0.79 to $0.81
- **THEN** one `budget.warning` with `scope: "daily"` is published, and a later call from $0.81 to $0.83 publishes none

### Requirement: Bounded overrun
A cap SHALL be exceeded only by the sum of (actual − estimate) of the calls that were in flight when it was reached. An overrun SHALL be recorded in the ledger and shown in spend totals, never hidden. A reply already streaming SHALL NOT be cut off because of a cap.

#### Scenario: Concurrent preflights
- **WHEN** twenty calls whose recorded actual costs exceed their estimates race through preflight under a $0.05 cap
- **THEN** total recorded spend is at most $0.05 plus the sum of (actual − estimate) of the admitted calls

### Requirement: Cost estimates per category
Before a paid call, the backend SHALL estimate its cost from the committed price table:
- **chat:** the stable prefix at the cached rate when the prefix is warm, otherwise at the input rate; other input at the input rate; and expected output at the output rate. Expected output is `min(max_tokens, p75 of the character's last 10 replies)`, with 220 standing in for the p75 when the character has no replies yet.
- **decision:** input tokens × the decision input rate, with output free.
- **image:** the per-image generation price.
- **embedding:** tokens × the embedding rate.

At peak, chat estimates SHALL be multiplied by the configured peak multiplier (2). Actual costs SHALL always come from the provider.

#### Scenario: Peak chat estimate
- **WHEN** the same chat request is estimated off-peak and at peak
- **THEN** the peak estimate is twice the off-peak estimate

#### Scenario: Decision estimate
- **WHEN** a decision with 10,000 input tokens is estimated
- **THEN** the estimate is $0.00042

### Requirement: Peak window
The pricing period SHALL be `peak` Monday–Friday 09:00–12:00 and 14:00–18:00 Malaysia time, and `off_peak` otherwise. `AppSettings.pricing` and the ledger's `price_period` SHALL both use this period.

#### Scenario: Tuesday morning
- **WHEN** the clock reads Tuesday 10:30 Malaysia time
- **THEN** `pricing.period` is `peak`, and a chat row recorded then has `price_period: "peak"`
