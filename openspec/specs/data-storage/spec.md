# data-storage Specification

## Purpose

Defines the invariants of the backend's SQLite store: what the schema covers, how timestamps are written, how full-text and vector indexes stay in sync with their source rows, and how every read stays inside one world (NFR-23).

## Requirements

### Requirement: Versioned schema
The database schema SHALL be created and upgraded only by numbered migrations. The first migration SHALL create every ordinary table and full-text table in the storage design. Vector tables SHALL be created by the application, never by a migration. Applying migrations to an up-to-date database SHALL change nothing.

#### Scenario: Migrate twice
- **WHEN** `horizon migrate` runs on a database that is already current
- **THEN** it succeeds and makes no schema change

#### Scenario: No drift
- **WHEN** the migration-autogenerate check compares the models with a freshly migrated database
- **THEN** it reports no differences and ignores the virtual tables

### Requirement: Millisecond UTC timestamps
Every stored timestamp SHALL be ISO-8601 UTC with exactly three fractional digits (`2026-10-03T08:15:02.123Z`). Imported seed timestamps SHALL be normalised to this form.

#### Scenario: Seed timestamp normalised
- **WHEN** a seed world with `createdAt: "2026-09-14T08:00:00Z"` is imported and read back
- **THEN** its `createdAt` is `"2026-09-14T08:00:00.000Z"`

### Requirement: Search indexes follow their rows
Full-text and vector index entries SHALL be removed whenever their source row is deleted, including when the deletion is caused by a cascade from a parent record. Index entries SHALL be keyed by a stable integer row key, not by SQLite's implicit rowid.

#### Scenario: World delete clears indexes
- **WHEN** a world whose characters have knowledge and memory is deleted
- **THEN** no full-text or vector entry for those chunks or memories remains

#### Scenario: Stable keys survive VACUUM
- **WHEN** rows are deleted, the database is vacuumed and a full-text search is run
- **THEN** every hit maps back to the correct chunk

### Requirement: Embedding-space tables exist at startup
The backend SHALL keep a record of embedding spaces with exactly one active space. At startup it SHALL ensure that the active space's memory and knowledge vector tables and their delete triggers exist. A restart SHALL NOT recreate or empty them.

#### Scenario: Default space on first run
- **WHEN** the backend starts on an empty database
- **THEN** one active embedding space exists, and its vector tables are present and empty

### Requirement: World-scoped reads
Every read of characters, sessions, memory and knowledge SHALL be bound to a world (and a character where relevant). Full-text and vector lookups SHALL re-check the world and character of each hit. No read in world A SHALL return a record of world B.

#### Scenario: Two near-identical worlds
- **WHEN** worlds A and B hold characters with the same name, memory text and knowledge text, and A's lists, sources and passages are read
- **THEN** no record, chunk or memory belonging to B is returned

#### Scenario: Scoped full-text lookup
- **WHEN** a phrase that occurs in both worlds' knowledge is searched for within A's character
- **THEN** only A's chunks are returned
