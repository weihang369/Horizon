# continuous-integration Specification

## Purpose

Defines the repository's continuous integration: the Linux job that runs every gate, both E2E clients and a timed fresh-clone boot, without secrets, as the Unix evidence for the local-backend run requirements.

## Requirements

### Requirement: CI runs on pushes and pull requests
A GitHub Actions workflow SHALL run one job on Linux (`ubuntu-latest`) for every push and pull request on `dev` and on `feat/**` branches. A newer run for the same ref SHALL cancel an older one that is still in progress. The job SHALL have a time limit, and SHALL only be able to read the repository.

#### Scenario: Feature branch push
- **WHEN** a commit is pushed to `feat/http-client-parity`
- **THEN** the CI job runs on Linux for that commit

#### Scenario: Superseded push
- **WHEN** two commits are pushed to the same branch in quick succession
- **THEN** the run for the first is cancelled, and the run for the second completes

### Requirement: CI uses no secrets
The workflow SHALL reference no repository or organisation secrets, SHALL create no `.env` file, and SHALL pass with no OpenRouter key. It SHALL make no paid provider calls. Its only network use SHALL be installing tools, packages and the test browser.

#### Scenario: Fork pull request
- **WHEN** CI runs for a pull request that has no access to secrets
- **THEN** the job behaves exactly as for a branch push, and passes or fails on the code alone

### Requirement: CI runs every gate
The job SHALL run:
- the backend lint, type check and test suite, without the live and document-conversion tests;
- the frontend type check, lint, unit tests and the HTTP contract run;
- the seed, fixture, schema-export and asset-credit checks;
- the E2E suite on both clients with the bundled Chromium browser.

Any failing gate SHALL fail the job.

#### Scenario: A gate fails
- **WHEN** the committed schema export differs from what the contract generates
- **THEN** the job fails at the schema check and names it

#### Scenario: Linux-only breakage
- **WHEN** a frontend import differs from the file name only by letter case
- **THEN** the job fails on Linux, though the same code runs on Windows

### Requirement: CI times a cold fresh-clone boot
Before anything is restored from a cache, the job SHALL clone the commit into an empty directory and point the npm, uv and Python-install caches at empty directories. It SHALL then run `npm run setup` and start `npm run dev`, and wait until demo mode answers with the two seed worlds. It SHALL fail when that takes more than 300 seconds. It SHALL record the setup, boot and total times in the job summary. Document conversion SHALL NOT be installed.

#### Scenario: Boot within budget
- **WHEN** the cold boot reaches demo mode in 210 seconds
- **THEN** the step passes, and the job summary shows the setup, boot and total seconds

#### Scenario: Boot over budget
- **WHEN** the cold boot has not reached demo mode after 300 seconds
- **THEN** the step fails, its processes are stopped, and the summary shows how far it got

#### Scenario: Caches do not flatter the timing
- **WHEN** the dependency caches for the gates are warm from an earlier run
- **THEN** the timed boot still downloads every package and the Python runtime itself

### Requirement: CI failures can be diagnosed from the run
When the E2E step fails, the job SHALL upload the Playwright traces, screenshots and report as a run artifact, kept for at least 7 days. A test that passes only on retry SHALL be reported as flaky.

#### Scenario: E2E failure on CI only
- **WHEN** an HTTP E2E test fails on CI and passes locally
- **THEN** the run's artifact holds that test's trace and screenshot, and the backend's error output is in the job log
