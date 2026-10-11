## MODIFIED Requirements

### Requirement: CI runs every gate
The job SHALL run:
- the backend lint, type check and test suite, without the live and document-conversion tests;
- the frontend type check, lint, unit tests and the HTTP contract run;
- the seed, fixture, schema-export and asset-credit checks;
- `horizon eval smoke` in test mode, and the evaluation's corpus licence and overlap checks;
- the E2E suite on both clients with the bundled Chromium browser.

Any failing gate SHALL fail the job.

#### Scenario: A gate fails
- **WHEN** the committed schema export differs from what the contract generates
- **THEN** the job fails at the schema check and names it

#### Scenario: Linux-only breakage
- **WHEN** a frontend import differs from the file name only by letter case
- **THEN** the job fails on Linux, though the same code runs on Windows

#### Scenario: Smoke without secrets
- **WHEN** the CI job runs the smoke evaluation
- **THEN** it passes with no key and no network access, and costs nothing
