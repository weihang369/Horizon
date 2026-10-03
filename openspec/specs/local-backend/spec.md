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
- make sure the active embedding space's tables exist;
- import the seed if the database has no worlds;
- close any message left `streaming` as `interrupted`.

Restarting SHALL NOT duplicate the seed.

#### Scenario: First start on a fresh clone
- **WHEN** the backend starts with no `data/` directory
- **THEN** `data/horizon.db` is created, and `GET /api/v1/worlds` returns the two seed worlds

#### Scenario: Restart keeps data
- **WHEN** the backend is stopped and started again after a user world was created
- **THEN** the user world is still listed, and each seed world appears exactly once

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
The OpenRouter key SHALL NOT appear in any response, log line, database row, error message or event. Any `sk-or-…` string that reaches the logger SHALL be redacted.

#### Scenario: Redacted log line
- **WHEN** code logs a message containing `sk-or-v1-abc123`
- **THEN** the log file contains a redaction marker in its place and never the original string

### Requirement: Structured logs
The backend SHALL write JSON log lines to `data/logs/horizon.log`, rotating at 5 files × 5 MB, and to the console. Each line produced while handling a request SHALL carry that request's `request_id`.

#### Scenario: Request log
- **WHEN** `GET /api/v1/worlds` is served
- **THEN** a JSON log line with the method, path, status and a `request_id` is written

### Requirement: Factory reset
`POST /api/v1/admin/factory-reset` with body `{ "confirm": "DELETE EVERYTHING" }` SHALL:
- delete everything in `data/` except `models/`;
- re-run startup in the same process, so the backend keeps serving freshly seeded data without a restart.

Any other body SHALL be rejected with `validation`, and nothing SHALL be deleted. It SHALL succeed on Windows while the log file and databases are open.

#### Scenario: Wipe and continue
- **WHEN** a user world exists and the factory reset is confirmed
- **THEN** the call succeeds, the user world is gone, the two seed worlds are listed, and `data/models/` is untouched

#### Scenario: Missing confirmation
- **WHEN** the factory reset is called with `{ "confirm": true }`
- **THEN** it rejects with `validation`, and all data is unchanged

### Requirement: Command-line interface
The `horizon` command SHALL provide these subcommands:
- `serve`;
- `migrate` (apply migrations);
- `seed` (import the seed if it is missing);
- `reset` (reset demo data);
- `reset --factory --yes` (factory reset).

`reset --factory` without `--yes` SHALL do nothing and say why.

#### Scenario: Unconfirmed factory reset
- **WHEN** `horizon reset --factory` is run without `--yes`
- **THEN** it exits non-zero, and nothing is deleted

### Requirement: One-command local development
At the repository root:
- `npm run setup` SHALL install the backend core and the frontend in one step. Document conversion is a separate, optional second step.
- `npm run dev` SHALL start the backend and the frontend together, with the frontend using the backend.
- Stopping `npm run dev` SHALL stop both processes.
- `npm run demo` SHALL serve the built frontend and the API from one port.

#### Scenario: Dev session
- **WHEN** `npm run setup` (step 1) and then `npm run dev` are run on a fresh clone
- **THEN** the app on `http://localhost:5173` loads the seed worlds through `/api/v1`, served by the backend on port 8000

#### Scenario: Ctrl-C stops everything
- **WHEN** `npm run dev` is interrupted
- **THEN** neither the backend nor Vite keeps running
