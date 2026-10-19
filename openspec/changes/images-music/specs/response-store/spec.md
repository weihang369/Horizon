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
- **WHEN** the pairwise judge asks one pair in declared order and then reversed
- **THEN** the two requests have different keys, the reversed one is sent to Jev, and both answers are stored

#### Scenario: Old entries still hit
- **WHEN** a request in declared order that was stored before M15 is looked up
- **THEN** it is found under its old key, and nothing is sent

## ADDED Requirements

### Requirement: A probe never sends
A run in probe mode SHALL serve hits from the store as usual. On a miss it SHALL stop that item before any reservation or request, and record the item as "would pay", priced by the suite's own estimator. A probe SHALL write no ledger row, no spend-log row and no store entry.

#### Scenario: A miss in a probe
- **WHEN** a probe run reaches a request with no stored entry
- **THEN** no request is sent, the item is reported as "would pay" with its estimate, and the ledger and the store are unchanged

#### Scenario: A chained item stops at its first miss
- **WHEN** a conversation in a probe misses on its third turn
- **THEN** that turn and every later turn of the conversation are counted as "would pay"
