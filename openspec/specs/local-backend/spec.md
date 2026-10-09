# local-backend Specification

## Purpose

Defines the local Horizon backend as a running service: how it starts, where it listens, how it is configured, how it reports health, how it protects the API key in logs, how it is wiped, and how a developer runs it next to the frontend with one command.

## Requirements

### Requirement: Loopback only
The backend SHALL accept connections on the loopback interface only (`127.0.0.1`). It SHALL refuse to start when asked to bind to any other address.

#### Scenario: Default bind
- **WHEN** `horizon serve` starts with no host option
- **THEN** it listens on `127.0.0.1:8000` and is not reachable on the machine's LAN address

#### Scenario: Non-loopback host refused
- **WHEN** `horizon serve --host 0.0.0.0` is run
- **THEN** the command exits non-zero with a message that the backend is local-only, and nothing listens

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

### Requirement: Health report
`GET /api/v1/health` SHALL return `{ ok, version, schemaVersion: 1, db, vec, docling }`. `db` and `vec` SHALL be `"ok"` only when the database answers and the vector extension is loaded. `docling` SHALL be `"not_installed"`, `"models_missing"` or `"ready"`.

#### Scenario: Core install only
- **WHEN** the backend runs after setup step 1 only
- **THEN** health returns `ok: true`, `db: "ok"`, `vec: "ok"` and `docling: "not_installed"`

### Requirement: Configuration precedence
Each setting SHALL be resolved from the first source that defines it, in this order:
1. environment variables;
2. `.env`;
3. `data/settings.local.json`;
4. `seed/settings.json`.

Model IDs and prices SHALL come from the committed seed files.

#### Scenario: Local override
- **WHEN** `data/settings.local.json` sets `audio.music` to `0.2`
- **THEN** `GET /api/v1/settings` returns `audio.music: 0.2`, and every other field keeps its seed value

#### Scenario: Environment wins
- **WHEN** `HORIZON_TZ` is set in the environment and in `.env` to different zones
- **THEN** the environment value is used

### Requirement: The API key never leaks
The OpenRouter key SHALL NOT appear in any response, log line, database row, error message, event, export or ledger entry. Every component that writes text out of the process SHALL redact with one shared rule: any `sk-or-` token followed by one or more of `[A-Za-z0-9_-]` becomes `sk-or-***`. That covers the log filter, the exception formatter, error envelopes, the ledger writer and the call observer hook. The rule SHALL match every key that `PUT /settings/key` accepts.

#### Scenario: Redacted log line
- **WHEN** code logs a message containing `sk-or-v1-abc123`
- **THEN** the log file contains `sk-or-***` in its place and never the original string

#### Scenario: Short test key is redacted too
- **WHEN** code logs a message containing `sk-or-good`
- **THEN** the log line contains `sk-or-***`

#### Scenario: Leak sweep
- **WHEN** a test sets a key, runs a connection test, a model probe, a 401, a 500 with the key echoed in its body, and a top-up, then reads the logs, every error response, every ledger row, `GET /usage`, the global SSE stream and every file under `data/` except `secrets.local.json`
- **THEN** none of them contains the key

### Requirement: Structured logs
The backend SHALL write JSON log lines to `data/logs/horizon.log`, rotating at 5 files × 5 MB, and to the console. Each line produced while handling a request SHALL carry that request's `request_id`.

#### Scenario: Request log
- **WHEN** `GET /api/v1/worlds` is served
- **THEN** a JSON log line with the method, path, status and a `request_id` is written

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

### Requirement: One-command local development
At the repository root:
- `npm run setup` SHALL install the backend core and the frontend in one step. Document conversion is a separate, optional second step.
- `npm run dev` SHALL start the backend and the frontend together, with the frontend using the backend.
- `npm run dev:mock` SHALL start the frontend alone, on the MockClient.
- Stopping `npm run dev` SHALL stop both processes.
- `npm run demo` SHALL serve the built frontend and the API from one port.

On a fresh clone, with Node and uv installed and no package cache, `npm run setup` followed by `npm run dev` SHALL reach demo mode within 5 minutes (NFR-10). Demo mode means the app loads the two seed worlds through the backend. Document conversion is not part of that budget. The README SHALL give these steps for Windows first, then Unix, and SHALL report the document-conversion step separately.

#### Scenario: Dev session
- **WHEN** `npm run setup` (step 1) and then `npm run dev` are run on a fresh clone
- **THEN** the app on `http://localhost:5173` loads the seed worlds through `/api/v1`, served by the backend on port 8000

#### Scenario: Ctrl-C stops everything
- **WHEN** `npm run dev` is interrupted
- **THEN** neither the backend nor Vite keeps running

#### Scenario: Mock-only loop
- **WHEN** `npm run dev:mock` is run with no backend running
- **THEN** the app loads the seed worlds from the MockClient, and no request to `/api/` is made

#### Scenario: Fresh clone within five minutes
- **WHEN** the repository is cloned into an empty directory with empty npm and uv caches, `npm run setup` is run, and `npm run dev` is started
- **THEN** `GET /api/v1/worlds` through the app's dev server returns the two seed worlds within 300 seconds of the start of setup, on Windows and on Linux

#### Scenario: README matches the steps
- **WHEN** the README's run section is followed on Windows, as written
- **THEN** it names the prerequisites (Node and uv), the setup and dev commands, the optional `.env` copy, and the optional document-conversion step as a separate step, and it contains no statement about features the backend lacks

### Requirement: Committed environment template
The repository SHALL include `.env.example` at the root. It SHALL list `OPENROUTER_API_KEY` and every other variable the backend configuration reads, including each AI port override, with blank or default values; advanced variables MAY appear as commented-out lines. It SHALL never contain a real key. `.env` SHALL stay git-ignored. A test SHALL fail when the configuration reads a variable that the template does not list.

#### Scenario: Template has no key
- **WHEN** `.env.example` is read
- **THEN** `OPENROUTER_API_KEY=` has an empty value, and `.env` is matched by `.gitignore`

#### Scenario: Every variable is documented
- **WHEN** a new variable is added to the backend configuration without a line in `.env.example`
- **THEN** the backend test suite fails and names the missing variable

#### Scenario: No key-shaped text
- **WHEN** `.env.example` contains a token starting with `sk-or-` followed by key characters, on any line
- **THEN** the backend test suite fails

### Requirement: Secret hygiene guidance
The README SHALL include a secret-hygiene section. It SHALL recommend a pre-commit secret scan (gitleaks) as optional, with install and hook instructions for Windows and Unix. The repository SHALL NOT install a hook or add a dependency for it, so setup stays Node and uv only.

#### Scenario: Recommendation without a hook
- **WHEN** the repository is freshly cloned and set up
- **THEN** the README describes the optional gitleaks pre-commit hook, and no hook is installed in `.git/hooks` and no package for it is added
