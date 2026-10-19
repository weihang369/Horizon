## MODIFIED Requirements

### Requirement: Entry format and key
Each entry SHALL be one file `data/cache/<key>.json` holding `{request, response, usage, savedAt}`. The key SHALL be the SHA-256 of the canonical JSON (sorted keys, no spaces, non-ASCII kept) of `{model, provider, parameters, body}`. For Jev entries, the accepted canary fingerprint SHALL be added to the key. When a Jev request lists a question's options in an order other than the bank's declared order, that order SHALL be added to the key as well. A request in declared order SHALL keep exactly the key it had before. Entries SHALL be written atomically, and the first entry for a key SHALL be kept.

#### Scenario: Same request, same key
- **WHEN** the same chat request is stored from a group A script and looked up by an eval run
- **THEN** both compute the same key

#### Scenario: Drift makes Jev entries stale
- **WHEN** a new canary baseline with a different fingerprint is accepted
- **THEN** no earlier Jev entry is found for any request

#### Scenario: Both orders are asked
- **WHEN** the decisions suite asks an item's choice in declared order and then with its options reversed
- **THEN** the two requests have different keys, the reversed one is sent to Jev, and both answers are stored

#### Scenario: Old entries still hit
- **WHEN** a request in declared order that was stored before M15 is looked up
- **THEN** it is found under its old key, and nothing is sent

## ADDED Requirements

### Requirement: A probe never sends
A run in probe mode SHALL serve hits from the store as usual. On a miss it SHALL reserve nothing, send nothing, record the request with the gateway's estimate, and answer empty: no Jev answers, an empty reply, or a failed embedding batch. The caller's usual missing-answer path then runs. A probe SHALL reach no network, and SHALL write no ledger row, spend-log row or store entry.

#### Scenario: A miss in a probe
- **WHEN** a probe run reaches a Jev request with no stored entry
- **THEN** no request is sent, the request is recorded with its estimate, the caller gets no answers, and the ledger and the store are unchanged

#### Scenario: A chained suite is priced whole
- **WHEN** a probed suite whose items chain several requests has any miss
- **THEN** a real run of it is priced at the suite's whole estimate, while a one-request-per-item suite is priced as the sum of its misses
