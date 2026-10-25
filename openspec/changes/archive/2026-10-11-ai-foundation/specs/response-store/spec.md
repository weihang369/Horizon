## Purpose

The response store saves paid provider outputs on the user's machine so checks, the evaluation and seed indexing never pay twice for the same result, without ever making the live app repeat a reply or holding the user's private text.

## ADDED Requirements

### Requirement: Entry format and key
Each entry SHALL be one file `data/cache/<key>.json` holding `{request, response, usage, savedAt}`. The key SHALL be the SHA-256 of the canonical JSON (sorted keys, no spaces, non-ASCII kept) of `{model, provider, parameters, body}`. For Jev entries, the accepted canary fingerprint SHALL be added to the key. Entries SHALL be written atomically, and the first entry for a key SHALL be kept.

#### Scenario: Same request, same key
- **WHEN** the same chat request is stored from a group A script and looked up by an eval run
- **THEN** both compute the same key

#### Scenario: Drift makes Jev entries stale
- **WHEN** a new canary baseline with a different fingerprint is accepted
- **THEN** no earlier Jev entry is found for any request

### Requirement: A hit costs nothing
A request served from the store SHALL send nothing to the provider, reserve nothing, and write no ledger row. The run report SHALL count hits.

#### Scenario: Re-index after Reset demo
- **WHEN** seed knowledge is indexed, Reset demo runs, and seed knowledge is indexed again
- **THEN** the second indexing sends no embedding request and writes no embedding ledger row

### Requirement: Who may use the store
Only evaluation runs SHALL use the store for replies and Jev answers. The live app SHALL use it only for embeddings of seed knowledge, seed memories and evaluation corpus pieces. The user's documents, memories and messages SHALL never be stored or served from it, and live replies and Jev answers SHALL never be served from it.

#### Scenario: Regenerate stays new
- **WHEN** the user regenerates a live reply twice
- **THEN** both requests reach the provider

#### Scenario: User document
- **WHEN** a user-added document is embedded
- **THEN** no store entry is written for it

### Requirement: What bypasses the store
The drift canary, latency and repeatability runs, captured and imported cases, and private safety items SHALL never read from or write to the store. Timeout and fallback rates SHALL be computed only from calls that were not served from the store.

#### Scenario: Canary bypass
- **WHEN** the canary runs twice
- **THEN** both runs send all 20 requests to Jev
