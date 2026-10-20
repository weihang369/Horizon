# response-store Specification

## Purpose

The response store saves paid provider outputs on the user's machine so checks, the evaluation and seed indexing never pay twice for the same result, without ever making the live app repeat a reply or holding the user's private text.

## Requirements

### Requirement: Entry format and key
Each entry SHALL be one file `data/cache/<key>.json` holding `{request, response, usage, savedAt}`. The key SHALL be the SHA-256 of the canonical JSON (sorted keys, no spaces, non-ASCII kept) of `{model, provider, parameters, body}`. For Jev entries, the fingerprint of the accepted canary baseline of the entry's own decision model SHALL be added to the key; for the pinned `typesafe/jev-1.13` that is the fingerprint of `evals/canary.json`, so every key stored before the Jev comparison is unchanged. When a Jev request lists a question's options in an order other than the bank's declared order, that order SHALL be added to the key as well. A request in declared order SHALL keep exactly the key it had before. Entries SHALL be written atomically, and the first entry for a key SHALL be kept.

#### Scenario: Same request, same key
- **WHEN** the same chat request is stored from a group A script and looked up by an eval run
- **THEN** both compute the same key

#### Scenario: Drift makes Jev entries stale
- **WHEN** a new canary baseline with a different fingerprint is accepted for a model
- **THEN** no earlier Jev entry of that model is found for any request, and the other models' entries are still found

#### Scenario: Both orders are asked
- **WHEN** the decisions suite asks an item's choice in declared order and then with its options reversed
- **THEN** the two requests have different keys, the reversed one is sent to Jev, and both answers are stored

#### Scenario: Old entries still hit
- **WHEN** a request in declared order that was stored before M15 is looked up
- **THEN** it is found under its old key, and nothing is sent

#### Scenario: A switch keeps the candidate's answers
- **WHEN** a candidate model's answers were stored during the comparison, and that model then becomes the pinned one with its comparison baseline as its accepted canary
- **THEN** an eval run on it finds those answers, and sends nothing for them

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

### Requirement: A probe never sends
A run in probe mode SHALL serve hits from the store as usual. On a miss it SHALL reserve nothing, send nothing, record the request with the gateway's estimate, and answer empty: no Jev answers, an empty reply, or a failed embedding batch. The caller's usual missing-answer path then runs. A probe SHALL reach no network, and SHALL write no ledger row, spend-log row or store entry.

#### Scenario: A miss in a probe
- **WHEN** a probe run reaches a Jev request with no stored entry
- **THEN** no request is sent, the request is recorded with its estimate, the caller gets no answers, and the ledger and the store are unchanged

#### Scenario: A chained suite is priced whole
- **WHEN** a probed suite whose items chain several requests has any miss
- **THEN** a real run of it is priced at the suite's whole estimate, while a one-request-per-item suite is priced as the sum of its misses
