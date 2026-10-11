## MODIFIED Requirements

### Requirement: Factory reset
`POST /api/v1/admin/factory-reset` with body `{ "confirm": "DELETE EVERYTHING" }` SHALL:
- stop the job scheduler, letting any provider call already sent be recorded;
- stop knowledge indexing, including any document conversion process;
- stop the AI-call capture writer and drop its queue;
- delete everything in `data/` except `models/` (including `data/cache/` and `data/evals/`);
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

#### Scenario: Store and eval runs deleted
- **WHEN** `data/cache/` and `data/evals/` hold files and the factory reset is confirmed
- **THEN** both folders are empty or gone afterwards

### Requirement: Command-line interface
The `horizon` command SHALL provide these subcommands:
- `serve`;
- `migrate` (apply migrations);
- `seed` (import the seed if it is missing);
- `reset` (reset demo data);
- `reset --factory --yes` (factory reset);
- `models fetch` (download the document conversion models, see `document-conversion`);
- `eval <suite>`, `eval capture <messageId>`, `eval review <set>`, `eval overlap` and `eval corpus-check` (see `evaluation-harness` and `ai-call-capture`);
- `stats [--days N]`.

`reset --factory` without `--yes` SHALL do nothing and say why. `models fetch` without document conversion installed SHALL exit non-zero and name the setup step.

#### Scenario: Unconfirmed factory reset
- **WHEN** `horizon reset --factory` is run without `--yes`
- **THEN** it exits non-zero, and nothing is deleted

#### Scenario: Models fetch before setup
- **WHEN** `horizon models fetch` is run without document conversion installed
- **THEN** it exits non-zero, names `npm run setup:docling`, and downloads nothing

#### Scenario: Stats are read-only
- **WHEN** `horizon stats` runs while the server is stopped
- **THEN** the database file's contents are unchanged afterwards

## ADDED Requirements

### Requirement: Start-up reports AI switches and model mismatches
At start-up, the backend SHALL log one line each when AI-call capture or LangSmith tracing is on. It SHALL log an error, and still start, when the settings' chat model differs from the price table's chat model.

#### Scenario: Mismatched chat model
- **WHEN** `seed/settings.json` names a chat model different from `seed/pricing.json`
- **THEN** start-up logs an error naming both models, and the backend serves requests with the price table's model
