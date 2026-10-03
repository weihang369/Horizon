# Spec Delta

## ADDED Requirements

### Requirement: Demo-data reset on every client
`HorizonClient` SHALL expose `admin.resetDemo(): Promise<void>` (rev 1.3 addendum, additive; `schemaVersion` stays `1`). It SHALL resolve once the reset described in `demo-data` has completed. Every client SHALL emit `mock.reset` on the global stream afterwards. The app's "Reset demo data" actions SHALL call it, not a mock-only API.

#### Scenario: Reset through the interface
- **WHEN** `client.admin.resetDemo()` resolves on either client
- **THEN** seed records are back to their shipped state, and `onGlobal` subscribers have received `mock.reset`

#### Scenario: Settings button on the HttpClient
- **WHEN** the app runs on the `HttpClient` and the user confirms "Reset demo data" in Settings
- **THEN** `POST /api/v1/admin/reset-demo` is called, and the screen re-queries after `mock.reset`

### Requirement: Portable suite runs on every client
Each portable contract test SHALL declare the milestone whose backend routes it needs. A harness SHALL declare the milestone it supports:
- tests within that milestone SHALL run;
- every other test SHALL be reported as pending under a name that states its milestone, never skipped silently.

The suite SHALL run against the backend through an HTTP harness.

#### Scenario: HTTP run in M1b
- **WHEN** the portable suite runs with the HTTP harness against a test-mode backend
- **THEN** every M1b test passes, and every later test is listed as pending with its milestone in the name

#### Scenario: Mock run is complete
- **WHEN** the portable suite runs with the MockClient harness
- **THEN** every test runs and passes, and none is pending

#### Scenario: Pending list is explicit
- **WHEN** a test's milestone tag is removed or misspelled
- **THEN** the suite fails, rather than running or skipping that test
