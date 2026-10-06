## MODIFIED Requirements

### Requirement: Startup prepares an empty data directory
On startup, the backend SHALL do the following before it accepts requests:
- create `data/` if it is missing;
- apply all pending migrations;
- make sure the active embedding space's tables exist;
- import the seed if the database has no worlds;
- close any message left `streaming` as `interrupted`;
- recover every job left `queued` or `running` (see `generation-jobs`).

Restarting SHALL NOT duplicate the seed.

#### Scenario: First start on a fresh clone
- **WHEN** the backend starts with no `data/` directory
- **THEN** `data/horizon.db` is created, and `GET /api/v1/worlds` returns the two seed worlds

#### Scenario: Restart keeps data
- **WHEN** the backend is stopped and started again after a user world was created
- **THEN** the user world is still listed, and each seed world appears exactly once

#### Scenario: Restart with a job in flight
- **WHEN** the backend is stopped while a job is running and started again
- **THEN** before the first request is served, that job's tasks are requeued, finished or failed by the recovery rules

### Requirement: Factory reset
`POST /api/v1/admin/factory-reset` with body `{ "confirm": "DELETE EVERYTHING" }` SHALL:
- stop the job scheduler, letting any provider call already sent be recorded;
- delete everything in `data/` except `models/`;
- re-run startup in the same process, so the backend keeps serving freshly seeded data without a restart.

Any other body SHALL be rejected with `validation`, and nothing SHALL be deleted. It SHALL succeed on Windows while the log file and databases are open.

#### Scenario: Wipe and continue
- **WHEN** a user world exists and the factory reset is confirmed
- **THEN** the call succeeds, the user world is gone, the two seed worlds are listed, and `data/models/` is untouched

#### Scenario: Missing confirmation
- **WHEN** the factory reset is called with `{ "confirm": true }`
- **THEN** it rejects with `validation`, and all data is unchanged

#### Scenario: Reset during a job
- **WHEN** a portrait job is running and the factory reset is confirmed
- **THEN** the call succeeds, no job exists afterwards, and no job task runs after the reset
