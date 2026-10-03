# Spec Delta: demo-data

## Purpose

Defines the shipped seed dataset (its models, prices, sources and identifiers) and what "Reset demo data" restores, so the demo is reproducible without destroying user work.

## ADDED Requirements

### Requirement: Seed models and prices match the decision log
The seed SHALL record the following:
- **Image model:** `bytedance-seed/seedream-5-0-flash` at $0.018 per image, for every image generation price (D-61).
- **Decision model:** `typesafe/jev-1.13` at $0.042 per million input tokens, $0 output.
- **Embedding model:** a model with its price per million tokens.

#### Scenario: Pricing file
- **WHEN** `seed/pricing.json` is read
- **THEN** `decision.inputPerM` is `0.042`, `decision.outputPerM` is `0`, each image price is `0.018`, and an `embedding` entry exists

#### Scenario: Settings models
- **WHEN** `seed/settings.json` is read
- **THEN** `models.image` is `bytedance-seed/seedream-5-0-flash` and `models.embedding` is set

### Requirement: Seed knowledge uses supported types only
Seed knowledge sources SHALL be `file` or `text` only:
- Amara's "ED triage guidelines" is a `file` source;
- the seed SHALL contain no CSV source.

#### Scenario: No url or csv in the seed
- **WHEN** all seed knowledge sources are listed
- **THEN** none has `type: "url"`, and none has a title ending in `.csv`

### Requirement: Seed IDs are globally unique
Every ID in the seed SHALL be unique across the whole dataset, including portrait candidate IDs.

#### Scenario: Candidate IDs
- **WHEN** every `appearance.candidates[].id` in the seed is collected
- **THEN** no ID appears twice, and each one matches the contract ID format

### Requirement: Seed check guards the generated files
`seed:check` SHALL fail whenever the committed `seed/` differs from what the seed build generates.

#### Scenario: Stale seed
- **WHEN** a seed-build source changes and `seed:build` is not run
- **THEN** `seed:check` exits non-zero and lists the differing files

### Requirement: Reset demo data restores seed records only
Reset SHALL do the following:
- restore every seed world, character, session, memory, knowledge source and seed ledger row to its shipped state;
- keep user-created worlds, characters, sessions (including forks of seed sessions), memories and ledger rows;
- emit `mock.reset` afterwards.

#### Scenario: Fork survives reset
- **WHEN** the user forks a seed session, edits a seed character, then resets demo data
- **THEN** the fork still exists and opens, the seed character is back to its shipped profile, and `mock.reset` is emitted

#### Scenario: User world survives reset
- **WHEN** the user creates a world with a character, then resets demo data
- **THEN** that world and character are unchanged
