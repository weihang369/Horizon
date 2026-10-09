# document-conversion Specification

## Purpose

Turns uploaded PDF and DOCX documents into Markdown with page markers on the user's own machine, outside the API process, and reports whether that conversion is available, so knowledge ingestion never hangs or needs a key (D-62).

## Requirements

### Requirement: Plain text needs no converter
Markdown, plain-text files and pasted text SHALL be read directly as UTF-8, whether or not document conversion is installed. Their ingestion SHALL NOT start a conversion process.

#### Scenario: Markdown without document conversion
- **WHEN** document conversion is not installed and a Markdown file is added
- **THEN** the source reaches `indexed` or `keyword_only` with its passages, and no conversion process is started

### Requirement: Documents are converted out of process
PDF and DOCX files SHALL be converted to Markdown, with a page marker before each page's text, by a separate process. At most one conversion SHALL run at a time. The API SHALL keep answering other requests while a conversion runs.

#### Scenario: Health stays responsive during a conversion
- **WHEN** a PDF is being converted
- **THEN** `GET /api/v1/health` and `GET /api/v1/worlds` still answer, and a second PDF waits in `indexing` until the first conversion ends

#### Scenario: Pages are marked
- **WHEN** a three-page PDF with text on every page is converted
- **THEN** its passages carry locators `p. 1` to `p. 3` that match the pages their text came from

### Requirement: Conversions are bounded and cancellable
A conversion SHALL stop at a configurable timeout (default 10 minutes), when its source is deleted, and when the backend stops or is factory-reset. A stopped conversion SHALL leave no running process and no partial output. A timeout SHALL end the source `failed` with a readable reason.

#### Scenario: Delete during conversion
- **WHEN** a source is deleted while its PDF is being converted
- **THEN** the conversion process is gone within a few seconds, and no file or row of that source remains

#### Scenario: Timeout
- **WHEN** a conversion runs past the configured timeout
- **THEN** its process is stopped, and the source is `failed` with an error saying reading the document took too long

### Requirement: Page limit is checked before converting
A PDF with more than 300 pages SHALL end `failed` with an error naming its page count and the limit, without converting any page.

#### Scenario: Oversized PDF
- **WHEN** a 412-page PDF is added
- **THEN** the source ends `failed` quickly, with an error naming 412 pages and the 300-page limit

### Requirement: Unavailable conversion fails with a next step
When document conversion is not installed or its models are missing, a PDF or DOCX source SHALL end `failed` with an error that names the setup steps and says to Retry afterwards. Its original file SHALL be kept, so a later Retry converts it without a new upload.

#### Scenario: PDF before setup
- **WHEN** document conversion is not installed and a PDF is added
- **THEN** the source ends `failed` with an error naming `npm run setup:docling` and `horizon models fetch`, and its original file is kept

#### Scenario: Retry after setup
- **WHEN** conversion is then installed with its models and the failed source is re-indexed
- **THEN** the source ends `indexed` or `keyword_only` with its real passages

### Requirement: Models are fetched once, explicitly
`horizon models fetch` SHALL download the conversion models into `data/models/` and record that the download completed. Conversion SHALL run offline and SHALL NOT download anything. The health report's `docling` SHALL be `ready` only after a completed fetch with conversion installed. An interrupted fetch SHALL leave `models_missing`.

#### Scenario: Interrupted download
- **WHEN** `horizon models fetch` is interrupted part-way
- **THEN** `GET /api/v1/health` reports `docling: "models_missing"`

#### Scenario: Ready after fetch
- **WHEN** conversion is installed and `horizon models fetch` completes
- **THEN** `GET /api/v1/health` reports `docling: "ready"`, and later conversions make no network request

### Requirement: Scanned documents are read by OCR
A PDF whose pages are images of text SHALL be converted by optical character recognition, so its passages contain the printed words.

#### Scenario: Image-only PDF
- **WHEN** a PDF made of page images showing "The night shift starts at seven" is added with conversion ready
- **THEN** a passage of that source contains "night shift starts at seven"
