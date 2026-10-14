# Spec Delta

## MODIFIED Requirements

### Requirement: Command-line interface
The `horizon` command SHALL provide these subcommands:
- `serve`;
- `migrate` (apply migrations);
- `seed` (import the seed if it is missing);
- `reset` (reset demo data);
- `reset --factory --yes` (factory reset);
- `models fetch` (download the document conversion models, see `document-conversion`);
- `eval <suite>`, `eval capture <messageId>`, `eval review <set>`, `eval overlap` and `eval corpus-check` (see `evaluation-harness` and `ai-call-capture`);
- `stats [--days N]`;
- `space build [--space ID] [--yes]` (build an embedding space, see `embedding-spaces`).

`reset --factory` without `--yes` SHALL do nothing and say why. `models fetch` without document conversion installed SHALL exit non-zero and name the setup step. `space build` SHALL print what it would embed and its estimated cost and ask before spending; without a confirmation it SHALL spend nothing. It SHALL refuse while the server is running.

#### Scenario: Unconfirmed factory reset
- **WHEN** `horizon reset --factory` is run without `--yes`
- **THEN** it exits non-zero, and nothing is deleted

#### Scenario: Models fetch before setup
- **WHEN** `horizon models fetch` is run without document conversion installed
- **THEN** it exits non-zero, names `npm run setup:docling`, and downloads nothing

#### Scenario: Stats are read-only
- **WHEN** `horizon stats` runs while the server is stopped
- **THEN** the database file's contents are unchanged afterwards

#### Scenario: Space build declined
- **WHEN** `horizon space build` is run and the user answers no to its estimate
- **THEN** it exits without spending, and the active space is unchanged

#### Scenario: Space build while serving
- **WHEN** `horizon space build --yes` is run while the server is running on the same data directory
- **THEN** it exits non-zero and changes nothing
