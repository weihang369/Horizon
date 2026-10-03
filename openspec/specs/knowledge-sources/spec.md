# knowledge-sources Specification

## Purpose

Defines how a character's knowledge sources are added, indexed, re-indexed and removed, and what inputs are accepted, so the MockClient and the backend behave the same (D-65).

## Requirements

### Requirement: Accepted inputs
`characters.addKnowledge` SHALL accept one of two inputs:
- a file (PDF, DOCX, MD or TXT);
- pasted text `{ type: "text", title, text }`.

New sources SHALL have `type` `"file"` or `"text"`. URLs and CSV SHALL be rejected with `validation`.

#### Scenario: CSV rejected
- **WHEN** a `.csv` file is added
- **THEN** the call rejects with `validation`, and no source is created

#### Scenario: Pasted text accepted
- **WHEN** `{ type: "text", title: "Notes", text: "…" }` is added
- **THEN** a `KnowledgeSource` with `type: "text"` and `status: "indexing"` is returned

### Requirement: Knowledge limits
A file over 10 MB, a 21st source on one character, and a duplicate of an existing source on the same character SHALL each be rejected before a source is created:
- size and count with `validation`;
- a duplicate with `conflict`.

#### Scenario: Twenty-first source
- **WHEN** a character with 20 sources gets another one
- **THEN** the call rejects with `validation`, and `details.limit` is `20`

#### Scenario: Same file twice
- **WHEN** the same file content is added twice to one character
- **THEN** the second call rejects with `conflict`

### Requirement: Indexing lifecycle
A new source SHALL start as `indexing` and end as one of three statuses:
- `indexed` (searchable by keyword and meaning);
- `keyword_only` (keyword search only, because embedding was unavailable);
- `failed` (with a readable `error`).

Progress SHALL be published as `entity.changed { kind: "knowledge", id, progress: { stage, pct } }`, with `stage` one of `extracting`, `chunking` or `embedding`.

#### Scenario: Indexing with a key
- **WHEN** a source is added while a valid key is set
- **THEN** global `entity.changed` events report increasing `pct` through the stages, and the source ends `indexed` with `chunks > 0`

#### Scenario: Indexing without a key
- **WHEN** a source is added in demo mode (no key)
- **THEN** the source ends `keyword_only`, its passages are viewable, and no ledger row is written

### Requirement: Reindex
`characters.reindexKnowledge` SHALL re-run indexing for a source and return it with `status: "indexing"`. Re-indexing a `keyword_only` source while a key is set SHALL end `indexed`.

#### Scenario: Upgrade keyword-only source
- **WHEN** a key is set and a `keyword_only` source is re-indexed
- **THEN** it ends `indexed`, and a ledger row with category `embedding` is recorded

### Requirement: Delete a source
`characters.deleteKnowledge` SHALL remove the source and all its passages. `knowledgeSource(id)` SHALL then reject with `not_found`. Existing message citations SHALL keep rendering from their stored title and quote.

#### Scenario: Deleted source in an old transcript
- **WHEN** a cited source is deleted and the citing session is reopened
- **THEN** the citation chip still shows the stored title and quote, and opening the source reports it is no longer available

### Requirement: Supported formats in the UI
The knowledge drop zone SHALL list only the supported inputs: PDF, DOCX, MD, TXT and pasted text. A `keyword_only` source SHALL show a distinct badge.

#### Scenario: Keyword-only badge
- **WHEN** the Knowledge tab lists a `keyword_only` source
- **THEN** its row shows a "keyword only" badge, distinct from the indexed, indexing and failed badges
