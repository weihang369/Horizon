## Purpose

Defines the Playwright end-to-end suite as the acceptance suite for both clients: one set of specs, run against the MockClient and against a test-mode backend, isolated from the developer's own data and keys.

## ADDED Requirements

### Requirement: One spec tree, run on both clients
Every E2E spec SHALL run against the MockClient and against the backend through the `HttpClient`, with the same user-visible steps and the same assertions. Layout-only specs (tagged `@layout`) MAY run on the MockClient only. A single command SHALL run the suite on both clients. Separate commands SHALL run it on one client.

#### Scenario: Both clients from one command
- **WHEN** `npm run e2e` is run in `frontend/`
- **THEN** every spec runs once on the MockClient and once on the `HttpClient`, the `@layout` specs also run at 1280×720 on the MockClient, and the command fails if any run fails

#### Scenario: One client at a time
- **WHEN** `npm run e2e:http` is run
- **THEN** only the `HttpClient` runs execute, and no MockClient dev server is started

### Requirement: The backend under test is isolated
The HTTP runs SHALL use a backend started for the run in test mode with the scripted AI profile, on ports that differ from the dev ports (8000, 5173), with a temporary data directory. It SHALL read no repository `.env` and no stored key. If a port it needs is taken, the run SHALL fail rather than use the server already listening there. When the run ends or is interrupted, the backend's whole process tree SHALL stop and its temporary data SHALL be removed, on Windows and on Unix.

#### Scenario: Dev server already running
- **WHEN** `npm run dev` is running and `npm run e2e:http` is started
- **THEN** the E2E backend starts on its own ports, and the developer's `data/` directory is not read or changed

#### Scenario: A developer's .env is ignored
- **WHEN** the repository-root `.env` sets an AI port override and a key, and `npm run e2e:http` runs
- **THEN** the backend under test uses the scripted profile with no key until a test sets one

#### Scenario: Interrupted run leaves nothing behind
- **WHEN** an HTTP run is interrupted with Ctrl-C on Windows
- **THEN** no `horizon`, uv or Python process from that run keeps running, and its temporary data directory is gone

#### Scenario: Port taken
- **WHEN** another process listens on the E2E backend's port
- **THEN** the HTTP run fails before any test with an error naming the port

### Requirement: Every HTTP test starts from shipped data
Each HTTP test SHALL start from freshly seeded data with the test-mode overlays, as after a factory reset, so no test sees another test's records. HTTP tests SHALL run one at a time against their shared backend. The backend clock SHALL run in real time during E2E.

#### Scenario: Wizard character does not leak
- **WHEN** the wizard spec creates "Sarah" and a later spec lists the Meridian Council roster
- **THEN** the later spec sees only the shipped roster

### Requirement: Client-specific steps live in fixtures
Steps that differ between clients SHALL be fixtures with one name and the same visible effect on both clients:
- **Setting a key** enters a fake key in Settings → Connection on both clients.
- **Applying a scenario** uses the mock state switcher on the MockClient and the backend's test route on HTTP.
- **Waiting for a generation job** allows the backend's real-time pacing on HTTP.

Specs SHALL NOT branch on the client themselves.

#### Scenario: Key through Settings
- **WHEN** a spec sets a key with the shared fixture and returns to its page
- **THEN** on both clients Settings shows the key as set, and the page's live actions are enabled

#### Scenario: Daily cap on both clients
- **WHEN** the energy spec applies the daily-cap scenario and requests a top-up for Hana
- **THEN** on both clients the dialog stays open and explains that today's budget is reached

#### Scenario: Wizard on the backend
- **WHEN** the wizard spec runs on HTTP, where a portrait takes 20 seconds
- **THEN** it passes without changing its steps

### Requirement: Console stays clean on both clients
A test SHALL fail on any console error or warning, or any uncaught page error, on either client. On HTTP, the browser's resource-error line for a 4xx response SHALL be accepted only when the test has declared that status as expected. A 5xx response, or an undeclared status, SHALL fail the test.

#### Scenario: Expected refusal
- **WHEN** the energy spec declares 402 as expected and the backend refuses the top-up with 402
- **THEN** the browser's resource-error line for that response does not fail the test

#### Scenario: Unexpected status
- **WHEN** a request in a test returns 404 and the test declared no expected status
- **THEN** the test fails and names the console line

### Requirement: Differences between clients are fixed at the source
When a spec passes on the MockClient and fails on HTTP because the backend shows different data or text, the backend or its seed import SHALL be fixed to match. The spec SHALL NOT be loosened. A difference that needs a contract or UI change SHALL be raised with the user before anything changes.

#### Scenario: Seed text differs
- **WHEN** the Knowledge spec expects "2 sources · cited 6× in conversations" and the HTTP run shows a different count
- **THEN** the backend's seed data or read model is corrected until both clients show the same text
