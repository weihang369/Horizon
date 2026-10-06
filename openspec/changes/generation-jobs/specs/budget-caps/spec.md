## ADDED Requirements

### Requirement: Jobs are refused before they are queued
Starting or retrying a job SHALL check its whole remaining estimate against the daily cap and, for a character that is not approved, against its creation cap, including what is already reserved. If it doesn't fit, the call SHALL reject with 402 `daily_budget_exceeded` or `creation_budget_exceeded`, publish `budget.reached`, and store no job and send nothing. If it fits, the estimate SHALL stay reserved until each task settles or the job ends.

#### Scenario: Creation cap blocks a portrait job
- **WHEN** a draft has spent $0.59 of its $0.60 creation cap and a portrait job estimated at $0.018 is started
- **THEN** it rejects with `creation_budget_exceeded`, no job exists, and the provider receives no request

#### Scenario: Two jobs share the daily headroom
- **WHEN** $0.95 of a $1.00 daily cap is spent and two drafts each start a $0.036 job
- **THEN** the first is accepted, and the second is refused with `daily_budget_exceeded` because the first job's estimate is reserved

## MODIFIED Requirements

### Requirement: Cost estimates per category
Before a paid call, the backend SHALL estimate its cost from the committed price table:
- **chat:** the stable prefix at the cached rate when the prefix is warm, otherwise at the input rate; other input at the input rate; and expected output at the output rate. Expected output is `min(max_tokens, p75 of the character's last 10 replies)`, with 220 standing in for the p75 when the character has no replies yet.
- **decision:** input tokens × the decision input rate, with output free.
- **image:** the per-image generation price for its kind (portrait, tweak, emotion edit, blink frame or expression sheet).
- **profile:** the profile-draft price, split evenly across the draft's tasks.
- **music:** the song price when a music model is used, and zero for the procedural theme.
- **embedding:** tokens × the embedding rate.

At peak, chat estimates SHALL be multiplied by the configured peak multiplier (2). Actual costs SHALL always come from the provider.

#### Scenario: Peak chat estimate
- **WHEN** the same chat request is estimated off-peak and at peak
- **THEN** the peak estimate is twice the off-peak estimate

#### Scenario: Decision estimate
- **WHEN** a decision with 10,000 input tokens is estimated
- **THEN** the estimate is $0.00042

#### Scenario: Emotion edit estimate
- **WHEN** one emotion edit is estimated with the shipped price table
- **THEN** the estimate is $0.018
