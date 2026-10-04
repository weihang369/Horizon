# spend-ledger Specification

## Purpose

The spend ledger is the single record of what Horizon spent. It holds one row per paid call (actual cost, or an estimate that is corrected later) and one row per energy top-up, and it feeds `spentTodayUsd`, the Usage screen, `Message.usage` and `TurnTrace.calls[]`.

## Requirements

### Requirement: One row per paid call
Every paid call SHALL write exactly one ledger row. The row SHALL carry the contract `category`, the internal `purpose`, the model, the serving provider, the pricing period, the generation ID, the token counts (in, cached, out), `cost_usd`, `estimated_cost_usd`, `latency_ms`, whether it counts toward a creation cap, and the session, character, job and message references. These columns are already in the storage schema.

#### Scenario: Completed chat call
- **WHEN** a recorded chat completion returns `usage.cost: 0.00042` from provider DeepSeek off-peak
- **THEN** one row is written with `category: "chat"`, `cost_usd: 0.00042`, `cost_source: "provider"`, `provider: "DeepSeek"`, `price_period: "off_peak"` and a non-null `estimated_cost_usd`

### Requirement: Estimate rows for calls that may have been charged
A call that was sent and then cancelled or broken, before the provider reported its cost, SHALL be recorded at its estimate, with `cost_source: "estimate"` and the generation ID if one is known. Examples are a stopped stream, and a decision or embedding request cancelled after sending. A call refused before sending SHALL write no row.

#### Scenario: Stopped stream
- **WHEN** a chat stream is cancelled after three chunks, with no usage received
- **THEN** one row is written with `cost_source: "estimate"`, `cost_usd` equal to the estimate, and the stream's generation ID

### Requirement: Estimates are corrected exactly once
For each estimate row that has a generation ID, the backend SHALL look up the actual cost in the background, retrying with backoff. When the actual cost arrives, it SHALL update that row once: `cost_usd` becomes the actual cost and `cost_source` becomes `provider`. When the row's purpose is `reply`, any difference SHALL be applied to the character's energy, and `entity.changed` SHALL be published for that character. No ledger row SHALL be updated in any other way.

#### Scenario: Correction after cancel
- **WHEN** a stopped stream's estimate row holds $0.00060 and the generation lookup later reports $0.00041
- **THEN** the row reads `cost_usd: 0.00041`, `cost_source: "provider"`, and `estimated_cost_usd: 0.00060`

#### Scenario: Correction is not repeated
- **WHEN** the lookup for an already-corrected row succeeds a second time
- **THEN** the row is not changed again

### Requirement: Corrections survive a restart
At startup, the backend SHALL resume corrections for estimate rows that have a generation ID and are no older than 24 hours. Older uncorrected rows SHALL keep their estimate.

#### Scenario: Restart mid-correction
- **WHEN** the backend stops while an estimate row from 10 minutes ago awaits correction, and then starts again
- **THEN** the lookup resumes, and the row is corrected once

### Requirement: Top-up rows cost nothing
An energy top-up SHALL write one row with `category: "energy_topup"`, `energy_points` equal to the points, and `cost_usd: 0`. It SHALL NOT count toward `spentTodayUsd` or any cap.

#### Scenario: Top-up row
- **WHEN** a +500 top-up succeeds for a character
- **THEN** a row with `category: "energy_topup"`, `energy_points: 500`, `cost_usd: 0` and that character's ID is written

### Requirement: Ledger rows hold no secrets
No ledger column SHALL contain the API key. Any request or error text the ledger writer stores SHALL pass through the shared redaction first.

#### Scenario: Error text with a key
- **WHEN** a provider error message echoes `sk-or-v1-abcdef1234567890`
- **THEN** no ledger row contains that string
