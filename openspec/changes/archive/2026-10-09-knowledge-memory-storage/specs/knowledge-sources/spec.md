## MODIFIED Requirements

### Requirement: Accepted inputs
`characters.addKnowledge` SHALL accept one of two inputs:
- a file (PDF, DOCX, MD or TXT);
- pasted text `{ type: "text", title, text }`.

New sources SHALL have `type` `"file"` or `"text"`. URLs and CSV SHALL be rejected with `validation`. A file SHALL be judged by its extension and its content: a PDF must start like a PDF, a DOCX must be a Word document package, and MD or TXT must be UTF-8 text without NUL bytes. A mismatch SHALL be rejected with `validation`, and no source created.

#### Scenario: CSV rejected
- **WHEN** a `.csv` file is added
- **THEN** the call rejects with `validation`, and no source is created

#### Scenario: Pasted text accepted
- **WHEN** `{ type: "text", title: "Notes", text: "…" }` is added
- **THEN** a `KnowledgeSource` with `type: "text"` and `status: "indexing"` is returned

#### Scenario: Fake PDF
- **WHEN** a file named `fake.pdf` containing `not a pdf` is added
- **THEN** the call rejects with `validation`, and no source is created

#### Scenario: Spreadsheet renamed to DOCX
- **WHEN** an Excel workbook renamed `report.docx` is added
- **THEN** the call rejects with `validation`, and no source is created

#### Scenario: Binary file renamed to TXT
- **WHEN** a file named `notes.txt` that is not valid UTF-8 is added
- **THEN** the call rejects with `validation`

### Requirement: Knowledge limits
A file over 10 MB, pasted text over 200 KB, a 21st source on one character, and a duplicate of an existing source on the same character SHALL each be rejected before a source is created:
- size and count with `validation`, and `details.limit` naming the limit;
- a duplicate with `conflict`.

A PDF over 300 pages, or a source that would give its character more than 3,000 passages, SHALL end `failed` with an error naming the limit.

#### Scenario: Twenty-first source
- **WHEN** a character with 20 sources gets another one
- **THEN** the call rejects with `validation`, and `details.limit` is `20`

#### Scenario: Same file twice
- **WHEN** the same file content is added twice to one character
- **THEN** the second call rejects with `conflict`

#### Scenario: Long paste
- **WHEN** 210 KB of pasted text is added
- **THEN** the call rejects with `validation`, and `details.limit` is `204800` on both clients

#### Scenario: Too many passages
- **WHEN** a character already has 2,990 passages and a source with 20 passages is added
- **THEN** that source ends `failed` with an error naming the 3,000-passage limit, and the character still has 2,990 passages

### Requirement: Indexing lifecycle
A new source SHALL start as `indexing` and end as one of three statuses:
- `indexed` (searchable by keyword and meaning);
- `keyword_only` (keyword search only, because embedding was unavailable);
- `failed` (with a readable `error`).

Progress SHALL be published as `entity.changed { kind: "knowledge", id, progress: { stage, pct } }`, with `stage` one of `extracting`, `chunking` or `embedding` and `pct` never decreasing for a source. A final `entity.changed` without `progress` SHALL announce the end status.

#### Scenario: Indexing with a key
- **WHEN** a source is added while a valid key is set
- **THEN** global `entity.changed` events report increasing `pct` through the stages, and the source ends `indexed` with `chunks > 0`

#### Scenario: Indexing without a key
- **WHEN** a source is added in demo mode (no key)
- **THEN** the source ends `keyword_only`, its passages are viewable, and no ledger row is written

#### Scenario: Cap reached while embedding
- **WHEN** today's cap is reached before a new source's passages are embedded
- **THEN** the source ends `keyword_only`, with its passages viewable and no `error`

### Requirement: Reindex
`characters.reindexKnowledge` SHALL re-run indexing for a source and return it with `status: "indexing"`. A source with its original file SHALL be re-read from the first stage whose stored output is out of date. A source without an original (seed) SHALL only be re-embedded, keeping its passages and their IDs. Re-indexing a `keyword_only` source while a key is set SHALL end `indexed`. Re-indexing a source that is already indexing, or a legacy `url` source, SHALL reject with `conflict`.

#### Scenario: Upgrade keyword-only source
- **WHEN** a key is set and a `keyword_only` source is re-indexed
- **THEN** it ends `indexed`, and a ledger row with category `embedding` is recorded

#### Scenario: Seed source keeps its passage IDs
- **WHEN** a seed source is re-indexed with a key set
- **THEN** it ends `indexed`, and its passages have the same IDs as before, so old citations still resolve

#### Scenario: Already indexing
- **WHEN** a source that is still indexing is re-indexed
- **THEN** the call rejects with `conflict`

### Requirement: Delete a source
`characters.deleteKnowledge` SHALL remove the source and all its passages, keyword entries, vectors and files, stopping any indexing still running for it first. `knowledgeSource(id)` SHALL then reject with `not_found`, and deleting it again SHALL reject with `not_found`. Existing message citations SHALL keep rendering from their stored title and quote.

#### Scenario: Deleted source in an old transcript
- **WHEN** a cited source is deleted and the citing session is reopened
- **THEN** the citation chip still shows the stored title and quote, and opening the source reports it is no longer available

#### Scenario: Delete while indexing
- **WHEN** a source is deleted while it is still indexing
- **THEN** the call succeeds, no row, vector or file of that source remains afterwards, and indexing does not resume after a restart

### Requirement: Supported formats in the UI
The knowledge drop zone SHALL list only the supported inputs: PDF, DOCX, MD, TXT and pasted text. Dropping or picking files SHALL add them, and a "Paste text" action SHALL add pasted text with a title. A `keyword_only` source SHALL show a distinct badge. Each source SHALL offer delete after a confirmation. A `failed` source SHALL offer Retry. A `keyword_only` source SHALL offer Index while a key is set. An indexing source SHALL show its current stage and progress.

#### Scenario: Keyword-only badge
- **WHEN** the Knowledge tab lists a `keyword_only` source
- **THEN** its row shows a "keyword only" badge, distinct from the indexed, indexing and failed badges

#### Scenario: Index a seed source
- **WHEN** a key is set and the user presses Index on a keyword-only seed source
- **THEN** `reindexKnowledge` is called for it, the card shows the embedding stage, and it ends with the indexed badge

#### Scenario: No Index without a key
- **WHEN** no key is set and the Knowledge tab lists a keyword-only source
- **THEN** the card shows no Index button and says a key enables search by meaning

#### Scenario: Paste text
- **WHEN** the user pastes a title and text in the Paste text dialog and confirms
- **THEN** a text source appears as indexing, and it ends readable in the source viewer

## ADDED Requirements

### Requirement: Indexing survives a restart
A source left indexing by a stop or crash SHALL resume after the next start from the stage it reached. Embedding requests whose results were already recorded SHALL NOT be sent again. A source whose embedding request was in flight at the crash SHALL end `keyword_only`, and SHALL be embedded again only when the user re-indexes it.

#### Scenario: Crash between batches
- **WHEN** the backend stops after two of three embedding batches of a source were recorded, and starts again
- **THEN** only the third batch is sent, and the source ends `indexed` with three `embedding` ledger rows in total

#### Scenario: Crash during a batch
- **WHEN** the backend stops while an embedding batch is in flight, and starts again
- **THEN** no embedding request is sent for that source, it is `keyword_only`, and a user re-index embeds its remaining passages

### Requirement: Keyword-only user sources are re-embedded when a key appears
When a key becomes set, and at startup with a key set, user-added `keyword_only` sources SHALL be embedded in the background. Seed sources and sources whose embedding was cut by a crash SHALL NOT be.

#### Scenario: Key added after uploads
- **WHEN** a user source was added in demo mode and then a key is saved
- **THEN** that source ends `indexed` without any user action, while seed sources stay `keyword_only`

### Requirement: Passages carry readable locators
Each passage SHALL have a locator: `p. N` (or a page range) for paged documents, the nearest heading as `§ Heading` for documents with headings, and `¶ N` otherwise. Each paragraph of Markdown, text or pasted text SHALL be its own passage, in reading order.

#### Scenario: Markdown paragraphs
- **WHEN** a Markdown file `# Soups\n\nMiso first.\n\nThen tofu.` is added
- **THEN** its passages are `# Soups`, `Miso first.` and `Then tofu.`, in that order

#### Scenario: PDF pages
- **WHEN** a PDF's second page holds the sentence "Triage starts at the door."
- **THEN** the passage containing that sentence has locator `p. 2`
