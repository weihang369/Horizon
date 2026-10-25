# Spec Delta

## MODIFIED Requirements

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
