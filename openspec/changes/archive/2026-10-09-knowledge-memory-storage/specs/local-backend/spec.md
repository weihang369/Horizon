## MODIFIED Requirements

### Requirement: Startup prepares an empty data directory
On startup, the backend SHALL do the following before it accepts requests:
- create `data/` if it is missing;
- apply all pending migrations;
- make sure the active embedding space's tables exist, and remove retired spaces' tables;
- import the seed if the database has no worlds;
- close any message left `streaming` as `interrupted`;
- recover every job left `queued` or `running` (see `generation-jobs`);
- recover every knowledge source left indexing (see `knowledge-sources`).

After it starts accepting requests, it SHALL remove temporary uploads and knowledge folders that no source refers to and that are older than one hour.

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

#### Scenario: Restart with a source indexing
- **WHEN** the backend is stopped while a source is being chunked and started again
- **THEN** that source resumes indexing and ends `indexed` or `keyword_only` without a user action

#### Scenario: Orphaned knowledge folder
- **WHEN** a knowledge folder with no matching source is older than one hour at startup
- **THEN** it is removed, and folders of existing sources are kept

### Requirement: Factory reset
`POST /api/v1/admin/factory-reset` with body `{ "confirm": "DELETE EVERYTHING" }` SHALL:
- stop the job scheduler, letting any provider call already sent be recorded;
- stop knowledge indexing, including any document conversion process;
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

#### Scenario: Reset during a conversion
- **WHEN** a PDF is being converted and the factory reset is confirmed
- **THEN** the call succeeds, the conversion process is gone, and no knowledge source exists except the seed ones

### Requirement: Command-line interface
The `horizon` command SHALL provide these subcommands:
- `serve`;
- `migrate` (apply migrations);
- `seed` (import the seed if it is missing);
- `reset` (reset demo data);
- `reset --factory --yes` (factory reset);
- `models fetch` (download the document conversion models, see `document-conversion`).

`reset --factory` without `--yes` SHALL do nothing and say why. `models fetch` without document conversion installed SHALL exit non-zero and name the setup step.

#### Scenario: Unconfirmed factory reset
- **WHEN** `horizon reset --factory` is run without `--yes`
- **THEN** it exits non-zero, and nothing is deleted

#### Scenario: Models fetch before setup
- **WHEN** `horizon models fetch` is run without document conversion installed
- **THEN** it exits non-zero, names `npm run setup:docling`, and downloads nothing
