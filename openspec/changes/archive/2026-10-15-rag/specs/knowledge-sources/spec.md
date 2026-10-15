# Spec Delta

## MODIFIED Requirements

### Requirement: Passages carry readable locators
Each passage SHALL have a locator: `p. N` (or a page range) for paged documents, the nearest heading as `§ Heading` for documents with headings, and `¶ N` otherwise. From M12, a passage is a piece of about 300 tokens (never more than 400), built from whole blocks under one heading path, in reading order; a heading is never a passage on its own.

#### Scenario: Markdown paragraphs
- **WHEN** a Markdown file `# Soups\n\nMiso first.\n\nThen tofu.` is added
- **THEN** it has one passage, `# Soups\n\nMiso first.\n\nThen tofu.`, with locator `§ Soups`

#### Scenario: PDF pages
- **WHEN** a PDF's second page holds the sentence "Triage starts at the door."
- **THEN** the passage containing that sentence has locator `p. 2`

#### Scenario: Sentence across a page break
- **WHEN** a PDF paragraph starts on page 3 and its sentence ends on page 4
- **THEN** one passage holds the whole sentence, with locator `pp. 3–4`

## ADDED Requirements

### Requirement: Pieces are sized by structure, then by length
A source's text SHALL be cut by structure first: a heading changes the heading path and is carried into the next piece; a piece never crosses a heading change, or a page break unless the text before it stops mid-sentence. Blocks under one heading and page SHALL be packed until a piece reaches 300 tokens or the next block would pass 400. A longer block SHALL be cut at a sentence end near 300, else at a line break, else at a word, at 400.

#### Scenario: Short paragraphs merge
- **WHEN** a section has a heading and three paragraphs of 80 tokens each
- **THEN** they form one piece that starts with the heading line

#### Scenario: Long paragraph splits
- **WHEN** one paragraph is 900 tokens long
- **THEN** it becomes pieces of at most 400 tokens, each ending at a sentence end where one exists

#### Scenario: Chinese sentence ends
- **WHEN** a long Chinese paragraph has sentences ending in "。"
- **THEN** its pieces are cut after a "。"

### Requirement: Tables and lists keep their lines
Paragraph text SHALL have its whitespace collapsed; tables and lists SHALL keep their line breaks. A table SHALL be cut only between rows, and each part after the first SHALL repeat the header row, unless the header row and that part's first row do not fit one piece together; then that part SHALL start at the row. No piece SHALL hold only a repeated header. Each piece's text, without a repeated header row, SHALL equal the collapsed source text between its stored start and end offsets. Docling's `<!-- image -->` placeholder lines SHALL end a block and be dropped.

#### Scenario: Long table
- **WHEN** a Markdown table of 60 rows is longer than 400 tokens
- **THEN** it is split between rows, and every part starts with the header row

#### Scenario: A header too wide to repeat
- **WHEN** a table's header row is 390 tokens and a later row is 40 tokens
- **THEN** the part holding that row starts at the row, and no piece is header text alone

#### Scenario: Image placeholders
- **WHEN** a converted PDF holds `<!-- image -->` lines between paragraphs, and six of them in a row
- **THEN** no piece contains an image placeholder, and none is made of placeholders alone

### Requirement: A source chunked by an older version is re-chunked on reindex
A source chunked by an earlier chunker version SHALL keep its passages until it is reindexed. Reindexing it SHALL chunk it again with the current version, giving its passages new IDs; old citations SHALL keep their stored title and quote. Seed sources SHALL keep their authored passages and IDs. No source SHALL be re-chunked without a reindex.

#### Scenario: Old source reindexed
- **WHEN** a source chunked as `para@1` is reindexed
- **THEN** its passages are rebuilt with the current version, and a message citing an old passage shows the "re-indexed" notice in the source viewer

#### Scenario: No silent sweep
- **WHEN** the backend starts with `para@1` sources stored
- **THEN** their passages are unchanged and no embedding request is made for them
