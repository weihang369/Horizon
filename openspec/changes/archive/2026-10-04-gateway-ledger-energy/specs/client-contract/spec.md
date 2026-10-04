# Spec Delta

## MODIFIED Requirements

### Requirement: Portable suite runs on every client
Each portable contract test SHALL declare the milestone whose backend routes it needs. A harness SHALL declare the milestone it supports:
- tests within that milestone SHALL run;
- every other test SHALL be reported as pending under a name that states its milestone, never skipped silently.

The suite SHALL run against the backend through an HTTP harness. From M2, the HTTP harness SHALL support M2, and its `setKey` SHALL save an obviously fake key (`sk-or-test-…`) through `settings.setKey`.

#### Scenario: HTTP run in M1b
- **WHEN** an HTTP harness declares `supports: "M1b"`
- **THEN** every M1b test runs and passes, and every later test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M2
- **WHEN** the portable suite runs with the HTTP harness against a test-mode backend
- **THEN** every M1b and M2 test passes, and every later test is listed as pending with its milestone in the name

#### Scenario: Mock run is complete
- **WHEN** the portable suite runs with the MockClient harness
- **THEN** every test runs and passes, and none is pending

#### Scenario: Pending list is explicit
- **WHEN** a test's milestone tag is removed or misspelled
- **THEN** the suite fails, rather than running or skipping that test

## ADDED Requirements

### Requirement: Key validity is learned from the provider
The portable suite SHALL assert only the key behaviour both clients share: once a key is rejected, `testConnection` rejects with `invalid_key`, and settings then report `openRouterKeyStatus: "invalid"`. A key that is accepted reports `set`, with `demoMode: false`, and passes `testConnection`. The MockClient's immediate `invalid` on `setKey("sk-or-bad…")` SHALL be covered by a mock-only test.

#### Scenario: Bad key on either client
- **WHEN** `setKey("sk-or-bad-zzz")` is called, then `testConnection`
- **THEN** `testConnection` rejects with `invalid_key`, and `settings.get()` reports `openRouterKeyStatus: "invalid"` and `demoMode: true`

#### Scenario: Good key on either client
- **WHEN** `setKey("sk-or-good")` is called, then `testConnection`
- **THEN** `setKey` returns `openRouterKeyStatus: "set"` and `demoMode: false`, and `testConnection` resolves with `ok: true`
