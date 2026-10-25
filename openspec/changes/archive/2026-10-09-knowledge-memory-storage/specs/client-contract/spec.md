## MODIFIED Requirements

### Requirement: Portable suite runs on every client
Each portable contract test SHALL declare the milestone whose backend routes it needs. A harness SHALL declare the milestone it supports:
- tests within that milestone SHALL run;
- every other test SHALL be reported as pending under a name that states its milestone, never skipped silently.

The suite SHALL run against the backend through an HTTP harness. From M2, the HTTP harness SHALL save an obviously fake key (`sk-or-test-…`) through `settings.setKey` as its `setKey`. From M4, it SHALL support M4. From M5, it SHALL support M5. A portable assertion on events collected from a subscription SHALL wait, within a bounded time, for them to be delivered, because a remote client receives them asynchronously. A test whose behaviour depends on a later milestone's feature SHALL be tagged with that milestone. Live knowledge citations are tagged M5.

#### Scenario: HTTP run in M1b
- **WHEN** an HTTP harness declares `supports: "M1b"`
- **THEN** every M1b test runs and passes, and every later test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M2
- **WHEN** the portable suite runs with the HTTP harness against a test-mode backend
- **THEN** every M1b and M2 test passes, and every later test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M3
- **WHEN** the portable suite runs with the HTTP harness declaring `supports: "M3"` against a test-mode backend
- **THEN** every M1b, M2 and M3 test passes, and every M4, M5 and M6 test, including live knowledge citations, is listed as pending with its milestone in the name

#### Scenario: HTTP run in M4
- **WHEN** the portable suite runs with the HTTP harness declaring `supports: "M4"` against a test-mode backend
- **THEN** every M1b to M4 test passes, including the creation pipeline, partial image failure, job mirroring, cover upload, tombstone and reset tests, and every M5 and M6 test is listed as pending with its milestone in the name

#### Scenario: HTTP run in M5
- **WHEN** the portable suite runs with the HTTP harness declaring `supports: "M5"` against a test-mode backend
- **THEN** every M1b to M5 test passes, including knowledge add, limits, progress, keyword-only upgrade, delete, seed re-index, Forget and live knowledge citations, and every M6 test is listed as pending with its milestone in the name

#### Scenario: Mock run is complete
- **WHEN** the portable suite runs with the MockClient harness
- **THEN** every test runs and passes, and none is pending

#### Scenario: Pending list is explicit
- **WHEN** a test's milestone tag is removed or misspelled
- **THEN** the suite fails, rather than running or skipping that test
