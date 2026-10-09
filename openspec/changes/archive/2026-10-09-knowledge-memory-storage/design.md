# Design: knowledge-memory-storage (M5)

## Context

See proposal.md for the why. Several facts in the code today shape the design, and some contradict the design pack:

- **Storage exists, writes don't.**
  - `0001_initial` already has `memory_items`, `knowledge_sources/sections/chunks`, `embedding_spaces`, `trace_memory_refs` and `ai_purge_queue` (scope `memory` allowed).
  - It also has the FTS5 external-content tables with their triggers.
  - `db/spaces.py` creates the active space's `vec0` tables and their delete triggers.
  - Reads exist: `reads.character_memory`, `character_knowledge`, `knowledge_source`, and `fts_search`/`memory_fts_search`.
- **`fts_search` passes user text straight to `MATCH`.** A quote, `NEAR`, `AND`, `-` or a column filter in a chat message would raise or change the query. Retrieval must not reuse it as is.
- **`TurnContext` has no `QueryBundle` and no retriever.** Doc 05 says "the field exists from M3"; it doesn't. The ai-ports spec also requires contexts to round-trip through JSON, which rules out putting retriever objects into them (D10).
- **`trace_memory_refs` is written only by the seed import.**
  - `sessions/writer.py` doesn't write refs for live `insight` events.
  - `sessions/lifecycle.fork` copies `turn_traces` and `insight` events into the new session but not their refs.
  - So a Forget driven by refs alone would miss forks (D14).
- **The gateway preflight runs `require_key()` before anything else**, including scripted (D-81) calls. So "no key" means "no embedding call at all", and the knowledge-sources scenario "without a key → `keyword_only`, no ledger row" holds by construction (D7).
- **The portable M5 tests are already written** (`clientContract.portable.ts`), and they pin observable details:
  - `"# Soups\n\nMiso first.\n\nThen tofu."` becomes exactly three chunks `["# Soups","Miso first.","Then tofu."]`;
  - ≥ 3 progress events covering all three stages with non-decreasing `pct`;
  - exactly one `embedding` row for a small source, with `model == settings.models.embedding`;
  - re-indexing a seed source keeps its chunk IDs;
  - the live citation test needs `trace.knowledge.retrieved` with both cited and uncited entries, and `context.used.knowledge > 0`.
- **The Knowledge tab** (`features/profile/tabs.tsx`) renders sources, badges and O28 but wires nothing: its drop zone and Retry show "v1.1 preview" toasts. The MockClient has implemented add, delete and reindex since M1a. Its pasted-text limit is 10 MB, which contradicts D-65's 200 KB.
- **`models.embedding` is editable** in Settings → Models, but a vector space is one model with fixed dimensions (D-64).
- **Docling is an optional dependency group** (`npm run setup:docling`). `/health` reports `ready` when `data/models/` is merely non-empty.
- **Runtime.** SQLite 3.53 (FTS5 `secure-delete` since 3.44) and sqlite-vec 0.1.9 under aiosqlite. Doc 01 §4.4 already names the semaphores `embedding 2, docling 1`.

## Goals / Non-Goals

**Goals:**
- Every acceptance line of doc 06 M5, on Windows first. Each task group ends with green gates.
- One durable, restart-safe ingestion pipeline whose only state is the `knowledge_sources` row and files under `data/knowledge/`.
- Forget is provably complete at the byte level, for the files the backend owns.
- The AI stage replaces policies (chunk sizes, retrieval mix, rerank, gate, memory writing, prompt layout) by swapping port implementations, with no schema or runtime rework.

**Non-Goals:**
- Memory *policy*: `MemoryWriter` returns `[]` in both profiles, and nothing calls `Touch`/`Reinforce` from live turns.
- Any of the following:
  - a Jev gate or rerank, or MMR;
  - trigram FTS;
  - `knowledge_chunk_redirects`;
  - LangGraph or `graph.db` contents;
  - choosing the final embedding model and dimensions;
  - a user-facing space switch.
- Memory vectors used for recall: the naive `MemoryRetriever` is FTS5 only (doc 05). Vectors are still written so the AI stage starts with them.
- Query embeddings for debate and watch turns (D12).
- URL or CSV ingestion (D-65), and any contract change.

## Decisions

### D1. Ingestion is its own durable worker, not a generation job
Each source runs as one `rt.spawn` task (`ingest:{sourceId}`) owned by an `IngestionWorker` on the runtime. The worker exposes `submit`, `cancel`, `cancel_for(character|world)` and `stop`. Stages are gated by activity-aware slots:
- `docling_slots = Slots(1)`;
- `embed_slots = Slots(2)`.

These are the doc 01 §4.4 numbers. Tasks are FIFO by submission. The `knowledge_sources.status` column *is* the job record (`queued → extracting → chunking → embedding → indexed | keyword_only | failed`). Every stage transition is an `UPDATE … WHERE id = :id AND status = :expected`, so a deleted or re-submitted source turns any late write into a no-op.

- *Rejected: a `generation_jobs` kind.* `GenerationJobKind` is a contract enum. A job also takes the character's single `activeJobId`, so uploading a PDF would block a portrait job, and the creation cap and reservation semantics don't fit.
- *Rejected: an in-memory queue only.* A restart would strand `indexing` sources forever.

### D2. Restart recovery and the paying-twice rule for embedding batches
Each embedding batch is one paid call through `gateway.paid` (or its scripted twin, D7) with the D-84 hooks:
- `before_send` commits `knowledge_sources.embed_sent_at = now`;
- `commit_with` inserts the batch's vectors and clears `embed_sent_at` **in the ledger row's transaction**.

A batch's vectors and its ledger row therefore exist together or not at all. At startup:

| Status at crash | Recovery |
|---|---|
| `queued`, `extracting` | Resubmit from extraction. Conversion is free and idempotent: `extracted.md` is written atomically. |
| `chunking` | Resubmit from chunking: sections and chunks are swapped in one transaction, so there is never a partial set. |
| `embedding`, `embed_sent_at IS NULL` | Resume embedding, only for chunks with no vector in that space. Batches already recorded are never re-sent. |
| `embedding`, `embed_sent_at` set | A batch was sent and its result is unknown. The source ends **`keyword_only`**, keeps the marker, and is excluded from background re-embedding. Only a user ↻ Retry (reindex) clears the marker and resumes. |

This is the generation-jobs rule (`provider_called_at` → failed, retryable) applied to batches. The money at stake is tiny (≤ 32 chunks ≈ $0.0001), but the rule is locked, and a crash loop must never turn into a spend loop.

- *Rejected: auto-resend the in-flight batch.* It is cheap, but it breaks the locked rule and needs a special case in the spec.
- *Rejected: mark the source `failed`.* Its passages are fine and keyword search works, so `keyword_only` is the truthful status.

New column: Alembic `0002_knowledge_memory` adds `knowledge_sources.embed_sent_at TEXT NULL` (Migration Plan).

### D3. Upload validation: count, sniff, then commit after the file
`POST /characters/{id}/knowledge` dispatches on `Content-Type`:
- `multipart/form-data` with one `file` part;
- `application/json` `{type:"text", title, text}`;
- anything else is `validation`.

Steps:
1. Reject early if the declared `Content-Length` is over 10 MB + 64 KB envelope (413). Stream the part to `data/tmp/{uuid}.upload` while counting (413 at 10 MB + 1). This reuses the cover route's counting parser.
2. The idempotency middleware's `body_limit()` gains the knowledge path. It buffers keyed requests, so its limit must match.
3. **Kind = extension AND content.**
   - The extension must be `pdf | docx | md | markdown | txt`, and a declared MIME type, when present, must fit it. This mirrors the mock, so `notes.html` and `sheet.csv` fail.
   - PDF: `%PDF-` within the first 1 KB.
   - DOCX: a ZIP whose central directory lists `word/document.xml`. We read the names only and never extract, so a ZIP bomb costs nothing here. A plain ZIP or an XLSX (`xl/…`) is rejected.
   - MD/TXT: strict UTF-8 (a BOM allowed) with no NUL bytes.
4. Pasted text: a non-empty title (≤ 200 chars kept) and non-blank text of at most **200 KB** of UTF-8 (`details.limit: 204800`).
5. In **one writer transaction**:
   - check the source count against 20 (`details.limit: 20`) and the duplicate SHA-256 against the partial unique index (`conflict`, `details.existingSourceId`);
   - insert the row as `queued` with `has_original`.

   The original is moved to `knowledge/{w}/{c}/{sid}/original.{ext}` *before* the commit (atomic replace), and is removed again if the commit fails. The row never points to a missing file. Counting inside the transaction closes the race between two concurrent adds.
6. Respond 201 with the source (`status: "indexing"`). Publish `entity.changed{kind:"knowledge", id, worldId}`. Submit to the worker.

A tombstoned or unknown character is `not_found`. An archived character may still be taught.

### D4. Document conversion runs one subprocess per document, under our control
- **Which converter.** `DocumentConverter` is an AI port, but **not key-dependent** (D-62: local and free):
  - normal runs use `DoclingConverter`;
  - **test mode defaults to `ScriptedConverter`**;
  - `HORIZON_AI_CONVERTER` overrides either way.
- **What each converter reads.**
  - Both read MD/TXT/pasted text directly; Docling never sees them.
  - `ScriptedConverter` turns PDF/DOCX into deterministic placeholder passages, the same rule as `mock/engines/knowledge.ts`. CI and the portable suite never need Docling.

  *Apply note (5.4):* verified against **Docling 2.133** (CPU torch 2.14); `horizon models fetch` downloads about 1.4 GB (layout, table, figure and RapidOCR models), and a dropped Hugging Face connection only needs a re-run (the marker is written last). Docling's default OCR runs on bitmap regions; on a page that is a single scanned bitmap it returns duplicated fragments, so a PDF with **no text layer on any page** (checked with pypdfium2 alongside the page count) is OCRed page-whole (`RapidOcrOptions(backend="torch", mode=OcrMode.FULL_PAGE)`). PDFs with text keep region OCR: page-whole OCR there would be slower and replace exact text with recognised text. Docling reads DOCX heading levels from `styles.xml` style names, so the test DOCX carries a styles part, as every Word file does.

  *Apply note (9.2):* a scripted PDF/DOCX conversion takes 0.8 s **on the runtime clock** (virtual in test mode, D-82), as a Docling run takes real time. Without it, a test-mode backend finishes a small source before the next HTTP request arrives, so the portable "reindex while indexing → `conflict`" test would race. With it the source stays in flight until the harness advances time, the same as the MockClient's staged pacing. *Rejected:* a `/_test` hook to hold ingestion (a test-only path the mock would have to mirror); pacing every stage (every backend test would need a longer settle).
- **The subprocess.** `DoclingConverter` runs `python -m horizon.ai.docling_worker --in … --out … --models data/models --max-pages 300`:
  - with `subprocess.Popen`, waited on via `asyncio.to_thread`;
  - environment `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `OMP_NUM_THREADS=min(4, cpus)`;
  - below-normal priority (`BELOW_NORMAL_PRIORITY_CLASS` on Windows, `nice` elsewhere).
- **Why not `asyncio.create_subprocess_exec`.** Uvicorn on Windows can run a selector event loop, where asyncio subprocesses raise `NotImplementedError`. A thread-waited `Popen` works under any loop.
- **What the worker does.**
  1. Counts pages first (pypdfium2 ships with Docling) and exits early with `reason: "page_limit"`, so a 900-page PDF fails in milliseconds instead of after minutes of OCR.
  2. Converts with `artifacts_path` = `data/models`.
  3. Writes Markdown with `<!-- page N -->` markers to a temporary file, prints one JSON result line, and exits with a status code.
  4. A watchdog thread exits the worker if its parent PID disappears (Windows doesn't kill children with their parent).
- **Timeout.** `knowledge.convertTimeoutMs`, default 600 000. On timeout, cancel or delete, the worker is `kill()`ed and reaped, and its temporary output removed. Timeout → `failed` ("Reading this document took too long…").
- **Readiness.** `not_installed` (no `docling` module) or `models_missing` (no completion marker, D5) → PDF/DOCX sources end **`failed`** with an actionable message: "Reading PDF and DOCX files needs document conversion. Run `npm run setup:docling` and `horizon models fetch`, then Retry." The original is kept, so Retry works once Docling is ready. No re-upload is needed, and nothing hangs.
- *Rejected: a long-lived Docling worker process.* Model load (~5–15 s) per document is acceptable for rare uploads. One process per document gives clean kill semantics and releases memory, and a crashed conversion can't poison the next one.
- *Rejected: in-process Docling.* It is a CPU-bound torch import in the API process, with no kill.
- *Rejected: refusing PDF/DOCX uploads when Docling is missing.* The user would have to upload again after setup.
- *Rejected: scripted placeholders in demo mode (no key).* Keying the converter on the profile would show fake passages for a real PDF just because no key is set.

### D5. `horizon models fetch` writes a completion marker
The CLI downloads the Docling layout, table and OCR models into `data/models/` (network, explicit, once), then writes `data/models/.horizon-models.json` (`{docling, fetchedAt}`). `/health` reports `ready` only when the marker exists and `docling` imports, which fixes "any file in the folder" reading as ready after an interrupted download. Factory reset already keeps `models/`.

The exact Docling download API is verified against the installed version during apply, which needs the user's go-ahead for the multi-GB install.

### D6. One chunker, matching the mock's paragraph rule
`KnowledgeIndexer` has a single implementation used by both profiles (`chunker_version = "para@1"`, `tokenizer = "utf8/4"` = `count_tokens`):
- **Children** are the mock's `paragraphs()`. Split on blank lines and collapse whitespace. A paragraph over 1 200 characters is cut at a sentence end near 900. Heading lines are their own paragraph, which the portable test pins.
- **Sections (parents)** are runs of children under one heading path, capped near 1 500 tokens at child boundaries.
- **Pages** come from the `<!-- page N -->` markers.
- **Locators:** `p. N` (or `pp. N–M`) for paged documents; otherwise `§ {nearest heading}`; otherwise `¶ {i}`.
- `char_start`/`char_end` index `extracted.md`.
- The 3 000-children-per-character limit is checked at the chunking commit. Over it → `failed` with the numbers.

Chunk sizes are AI-stage tunables (doc 05 §6). Changing them bumps `chunker_version`, which makes reindex re-chunk.

### D7. The embedder: the space decides the model; scripted is billed and keyed
- **Naive (`QwenEmbedder`).**
  - It uses the **active space's** `model`, `provider` and `dims` through `gateway.embed(dimensions=space.dims)`.
  - Queries are wrapped as `Instruct: {space.query_instruction}\nQuery: {text}`; documents are sent raw.
  - A vector longer than `dims` is truncated and L2-renormalised (Qwen3 is Matryoshka-trained). A shorter or non-finite one is `malformed`.
  - An LRU of 4 096 entries is keyed by `(space.id, kind, sha256(text))`. A cache hit makes no call and writes no row.
- **Scripted (`HashEmbedder`).**
  - `unit_vector(sha256(kind+text), dims)` (the fake provider's function).
  - It is billed through a new `gateway.simulated_embedding(...)`: preflight with caps and holds, one row per 32-text batch, `category: "embedding"`, `provider: "scripted"`, `model = space.model`, `tokens_in = Σ count_tokens`, priced by `estimate_embedding`.
  - It honours the same D-84 hooks.
- **Keys.** Both require a key (the preflight's `require_key`). The pipeline checks `keys.status() == "set"` *before* the embedding stage, so a keyless run skips straight to `keyword_only` and never produces a `missing_key` error.
- **Purposes.** `embed_doc` (ingestion, memory) and `query_embed`. Category `embedding`. They count toward the daily cap only, never energy or the creation cap.
- **Why the space and not `settings.models.embedding`.** Mixing models in one `vec0` space corrupts KNN silently. The Settings value only takes effect through a space switch (D9), which is AI-stage. A mismatch is logged once at startup. The portable test's `model == settings.models.embedding` holds because both are seeded the same.
  - *Rejected: follow the setting live.*
  - *Rejected: auto-trigger a paid rebuild when the setting changes* (hidden spend, NFR-30).

### D8. Status is derived from vectors; background re-embed is narrow
- **Status.** A source is `indexed` iff every chunk has a vector in the active space (`embedding_space_id = active`). With passages but missing vectors it is `keyword_only`.
- **Embedding failure.** Any of these ends `keyword_only`, with `error` left empty because the source is readable: no key, cap refusal, provider error after retries, or `malformed`.
- **Background re-embed.** It runs on two triggers only:
  - at startup with a key set;
  - when the key becomes `set`.

  It covers sources with `is_seed = 0 AND status = 'keyword_only' AND embed_sent_at IS NULL AND chunk_count > 0`. Seed sources are never re-embedded in the background: they need the explicit per-source **Index** (D11).
- *Rejected: periodic retry.* It is hidden recurring spend, and a broken key or model would spin.

### D9. Space switch: dual-write, catch-up, atomic flip
`SpaceManager` grows these operations:
- `create_building(spec)`: its `vec0` tables and triggers;
- `building()`;
- `flip(building_id)`;
- the existing `drop_retired`.

While a space is `building`, every vector write (ingestion batches, `MemoryStore.apply`) embeds for **each non-retired space**: active plus building. Each space gets its own call, because models differ.

`build_space(spec)` is a service:
1. Embed every chunk and memory missing from the building space, in batches with the same hooks.
2. Run a final catch-up pass inside the writer lock window: rows inserted meanwhile were dual-written, so this only closes the gap between the scan and the lock.
3. In one transaction:
   - building → `active`, active → `retired`;
   - `knowledge_sources.embedding_space_id` moves to the new space for sources fully embedded there.
4. The next start drops the retired tables.

There is no route or UI. It is exercised by tests with a second test space (`hash@64`), and the AI stage gets the service.

*Apply note (8.1):* "every chunk and memory missing" is narrowed to **what the active space covers**: chunks of
`indexed` sources and memories with an active-space vector. Embedding keyword-only (seed) sources during a build would
index them on the user's behalf, against D-91; a build reproduces the old space's coverage in the new model. A batch in
flight at a crash is re-paid by the next build run (the build is explicit and rare; the per-source `embed_sent_at`
marker belongs to the ingestion pipeline).
- *Rejected: building in place* (ALTER the `vec0` dims). `vec0` can't, and a crash would leave a half-converted space.

### D10. Retrieval runs in the runtime; engines receive hits, not retrievers
In `TurnRunner.run`, after the energy gate and before the engine slot, the runtime:
1. Calls `MemoryRetriever.recall` and `KnowledgeRetriever.retrieve` with the **speaker's** `world_id`/`character_id`, taken from the runtime and never from the engine.
2. Freezes the hits into the `TurnContext`:
   - `knowledge: list[KnowledgeHit{chunkId, sourceId, title, type, locator, text, sectionText, score}]`;
   - `memory: list[MemoryHit{id, kind, text, sourceSessionId, score}]`.

Prefetched openings retrieve at prefetch time. Engines report what they used through their `TracePatch` (`knowledge`, `memory`, `context.used`) and a `CitationMap`. These remain engine-owned trace sections.
- **Why.**
  - The context stays immutable and JSON round-trippable (ai-ports), so an evaluation harness can replay it.
  - The scope is enforced by construction (NFR-23), because ports never touch rows.
  - The AI stage's `gate` (a Decider question in the runtime, doc 05 §3) slots in at exactly this point.
- *Rejected: pre-bound retriever objects inside `TurnContext`* (doc 05 §4's wording). They break JSON round-tripping and give engines a storage handle. Doc 05 §4 is updated (D-92).

### D11. "Index seed knowledge" is the per-source Index button (user decision, 2026-10-08)
- **No contract method.** The Knowledge tab shows **↻ Index** on `keyword_only` cards while the key status is `set`. It calls `reindexKnowledge`. For a source with no original this re-embeds only, so chunk IDs are kept and old citations still resolve (portable test).
- **Without a key** the badge stays and a hint reads "Add your OpenRouter key to search by meaning".
- **Cost.** Each press is one or two batches (< $0.0001 per seed source), shown on the button's tooltip from the price table.
- **Reset demo** deletes and re-inserts seed sources: new `rid`s, and the vectors go through the delete triggers. So **seed sources return to `keyword_only`** (truthful, and cheap to redo).
- *Rejected: keeping seed vectors across reset.* It needs `rid`-stable upserts of chunks and vectors for a < $0.001 saving.

### D12. One query bundle per user message, and only when it can pay off
When the actor accepts a `send` (1:1 or group), it starts `query_embed(text)` with `rt.spawn` **only if** all of these hold:
1. The active `KnowledgeRetriever` declares `uses_vectors` (naive does, scripted doesn't).
2. The key status is `set`.
3. At least one eligible responder has vectors in the active space: one indexed `EXISTS` over `knowledge_sources (character_id, status, embedding_space_id)`, run inside the spawned embedding task on every send. *Apply note:* the per-session cache invalidated by `entity.changed{knowledge}` was dropped; the lookup is sub-millisecond, runs off the send path, and a cache would only add a stale-gate failure mode (a source indexed between sends).

The bundle is keyed by the triggering message ID and reused by every responder of that message. Retrieval awaits it for at most `retrieval.queryEmbedWaitMs` (default 400, about the route decision's budget, since both run in parallel), on the runtime clock (`vclock.wait_at_most`, so the race is the same in virtual time, D-82). Past that it retrieves FTS only. The late vector still lands in the LRU, and the call is still billed.

The call's ledger row has `purpose: query_embed`, `session_id` and the user message's ID. It appears as a turn-level call on the first responder's `trace.calls`, like the route decision. A cap refusal or provider error means FTS only, with no error event.

Debate and watch turns have no user message, so they retrieve with FTS only, using the latest message (or the motion or premise) as query text.
- *Rejected: embed every message.* It is spend and latency for characters with no vectors, and the scripted profile would add rows to every turn, breaking M3 portable assertions on rows and trace calls.
- *Rejected: block until the vector arrives.* It puts provider latency on the hot path.

### D13. Retrievers, a safe FTS query and scores in [0, 1]
- **FTS query builder.** Unicode word tokens (`\w+`, length ≥ 2) from the query text, lower-cased and de-duplicated, at most 16, each double-quoted, joined with `OR`. User text can never inject FTS syntax. An empty token set retrieves nothing.
- **Scripted.**
  - `KnowledgeRetriever` = FTS (BM25) top 5.
  - `MemoryRetriever` = the 3 most recent current items (not superseded).
  - Score = `1/(1+rank)` mapped into [0.5, 0.95] for display.
- **Naive.**
  - `KnowledgeRetriever` = FTS top 20 ∪ vector KNN top 20, fused with RRF (k = 60), top 5. The KNN is `WHERE embedding MATCH :q AND character_id = :c AND k = 20` on the active space's `vec0`, re-joined to `knowledge_chunks` with the world and character re-bound.
  - Score = `rrf / (2/61)`, clamped to [0, 1]: 1.0 means first in both lists. `TurnTrace.knowledge.retrieved[].score` and `Citation.score` are unit by contract.
  - `MemoryRetriever` = FTS top 3 over current items.
- **Sizes.** k values are config (`retrieval.*`), AI-stage tunables. Children sharing a parent section are deduplicated for the prompt (D15) but stay separate hits.

### D14. Trace memory refs are maintained wherever traces are written
One helper derives `(memory_item_id, message_id)` pairs from `trace.memory.recalled[]`. It is used by:
- `sessions/writer.py` on each `insight`, replacing the message's refs;
- `sessions/lifecycle.fork`, for the copied traces under their new message IDs;
- the seed import, as today.

Forget then finds every trace and every `insight` event through refs. A defensive second pass over the character's world scans `turn_traces.trace` and `insight` payloads with `instr()` for the item's JSON-escaped text. It catches any path that wrote a trace without refs, and logs a warning when it finds one. Its cost is O(traces in one world), which is acceptable for a rare user action.

### D15. Scripted citations mirror the mock; the naive engine gets a minimal versioned block
- **Scripted.** `ScriptedTurnEngine` ports `liveCitations`/`citeKnowledge`/`insertMarkers` from `mock/script/citations.ts`, with **its own RNG stream** (`{seed}:{turn}:cite`). Lines, timings and emotions of existing turns are unchanged, and only characters with hits can change at all.
  - With hits, about 55 % of replies cite 1–2 passages (best word overlap with the prompt), and one more passage is retrieved but uncited.
  - The markers are inserted *before* streaming, so the tokens carry them.
  - It sets `trace.knowledge` (`trigger: "always"`, `query` = prompt ≤ 120 chars) and `context.used.knowledge`.
  - It never uses memory hits, as the mock doesn't (parity).
- **Naive.** `PROMPT_VERSION` becomes `v2`. When hits exist, one system message goes after the history (NFR-35: dynamic last, so the cached prefix is untouched):
  - "Passages you can use…" with `[n] Title, locator: section text` (each ≤ 1 200 chars, deduplicated by section);
  - "Things you remember about this world…" (≤ 3 memories);
  - one line: cite a passage with its `[n]` only when you rely on it.

  The engine yields a `CitationMap` for all numbered passages (the runtime keeps only the markers present, as in M3). After the stream it sets `trace.knowledge.retrieved` with `cited` flags from its own output, `trace.memory.recalled` and `context.used.memory/knowledge`. With no hits the request is identical to v1.
- *Rejected: no block until the AI stage* (doc 05 §5 "no dynamic blocks"). Naive mode would then never use knowledge, and the M5 feature would be invisible outside the scripted demo. The block is small, versioned and replaceable. Doc 05 §5 is updated (D-93).

### D16. Forget is complete at the byte level
`DELETE /memory/{id}` (404 if unknown). Every step below runs in **one writer transaction**:
1. **Chain.** Collect the chain: every item reachable by following `superseded_by` forward from the item, plus every item whose `superseded_by` points into the set (repeated to a fixpoint). Forgetting any version forgets all of them.
2. **Zero vectors, then delete.** `UPDATE {mem_vec} SET embedding = zeros WHERE rid IN chain`, for every non-retired space. sqlite-vec stores vectors packed in chunk blobs. Spike 1.1 showed that in 0.1.9 a delete also zeroes the slot; zeroing first is kept as a guard against a version that only clears the validity bit. Then delete the items. The FTS delete trigger and the `vec0` delete trigger fire, and their `trace_memory_refs` rows go.
3. **Scrub.**
   - Rewrite every `turn_traces.trace` and `insight` `session_events.payload` found by refs + D14's pass. Each `memory.recalled[]` entry for a chain ID gets `text: "(forgotten)"`.
   - Delete the refs.
   - Insert `ai_purge_queue {scope: "memory", ids: {memoryItemIds, characterId, messageIds}}`.
4. **Commit.** After the commit:
   - publish `entity.changed{kind:"memory", id: characterId, worldId}` (the mock's shape);
   - for every affected session with a **live actor**, post a `scrub_memory` message to its inbox so its in-memory reduced state drops the text (one writer per session);
   - run `PRAGMA wal_checkpoint(TRUNCATE)`, retried up to 5 × 100 ms if readers block it, then handed to a background retry. Forget responds 204 after the first attempt.

**Why the bytes are really gone:**
- **The writer connection runs `PRAGMA secure_delete = ON`.** Deleted and rewritten cells and freelist pages are zeroed. This costs extra page writes on deletes only, which is negligible at our size.
- **Alembic `0002` sets FTS5 `secure-delete = 1`** on `memory_fts` and `knowledge_fts`, so an FTS delete removes the terms from index segments instead of appending a tombstone. This needs SQLite ≥ 3.44, checked at startup. On an older SQLite, Forget runs `INSERT INTO memory_fts(memory_fts) VALUES('optimize')` instead.
- **The `TRUNCATE` checkpoint** copies the zeroed pages home and truncates `horizon.db-wal` to 0 bytes. Old frames would otherwise still hold the text.
- **`graph.db`** doesn't exist until the AI stage. The test greps it if present, and the rule "ids, never text" is the AI layer's contract (doc 05 §4).
- Not covered: the OS's freed disk blocks and backups. They are outside the files the backend owns, and doc 02 says backup is a copy of `data/`.

**Guardrail block (closes session-runtime OQ-8).** A blocked reply is never handed to the post-turn memory queue. As defence in depth, the scrub transaction also deletes, through the same Forget routine, any memory item whose `source_message_id` is the blocked message.

**Message content is not memory.** Forget removes the memory and its trace copies. It does not edit transcripts: a phrase the user typed stays in the session where they typed it. The specs say so explicitly, and the byte test uses a memory text that occurs nowhere else.

### D17. `MemoryStore.apply`: embeddings first, one transaction, serialised per character
`apply(character_id, world_id, ops)`:
1. Embeds the texts of every `Insert`/`Supersede` draft *before* taking the writer lock, for each non-retired space, but only when a key is set. Otherwise the items are written without vectors and stay FTS-only.
2. In **one transaction**:
   - inserts rows (FTS through the trigger);
   - writes vectors;
   - sets `superseded_by` (`Supersede`);
   - updates `importance` (`Reinforce`) and `last_recalled_at`/`recall_count` (`Touch`).

Ops are validated first: unknown IDs, another character's or another world's IDs, and importance outside [0, 1] all mean the whole batch fails with nothing written. A per-character `asyncio.Lock` serialises `apply` (OQ-SWE-09: memory writes serialised per character).

The **post-turn queue** runs after a `complete`, non-blocked reply. It calls `MemoryWriter.after_turn(ctx, perspective)` for the speaker, then applies the ops through `apply`. With the `[]` writer it costs one call and no I/O. A failing writer is logged and never affects the turn.

### D18. Deletes and lifecycles cancel ingestion first
- **`deleteKnowledge`:**
  1. `worker.cancel(sid)`: cancel the task and kill Docling if it is running. An embedding call already sent finishes shielded at its real cost (D-86); its `commit_with` sees the source gone and writes the ledger row without vectors.
  2. One transaction deletes the source. Sections, chunks, FTS and vectors go by cascade and triggers.
  3. After the commit, `rmtree(knowledge/{w}/{c}/{sid})` and publish `entity.changed`.

  `not_found` if unknown. Deleting a source with status `indexing` is allowed. `reindexKnowledge` on an `indexing` source is `conflict`; on a legacy `url` source it is `conflict`.
- **Character delete, world delete and reset demo** call `worker.cancel_for(...)` before their transactions. Factory reset calls `worker.stop()` (which kills Docling) before closing engines, as doc 02 §4 requires.
- **The startup sweeper** also removes `data/knowledge/**` folders with no source row that are older than one hour, plus `data/tmp/*.upload` older than one hour.

### D19. Progress events are stage-based and monotonic
`entity.changed{kind:"knowledge", id, worldId, progress:{stage, pct}}` is published:

| Point | `stage` | `pct` |
|---|---|---|
| Extraction start | `extracting` | 0.05 |
| Extraction end | `extracting` | 0.45 |
| Chunking start | `chunking` | 0.55 |
| Chunking end | `chunking` | 0.65 |
| Embedding start | `embedding` | 0.70 |
| After each batch | `embedding` | 0.70 + 0.25 × done/total |

Then one terminal `entity.changed` with no `progress`. A keyless run publishes no embedding stage. Events are rate-limited to at most one per source every 250 ms of clock time (embedding batches only), so a 300-page PDF doesn't flood the stream.

### D20. Clients and UI
- **HttpClient.**
  - `forgetMemory` → `DELETE /memory/{id}`.
  - `addKnowledge` → `postForm` with a `file` part, or a JSON `POST` for text.
  - `deleteKnowledge` → `DELETE`; `reindexKnowledge` → `POST …/reindex`.
  - Every `POST` carries `Idempotency-Key`. `later()` loses its last users. The type keeps `"M6"` for future use.
- **Knowledge tab.**
  - The drop zone takes dropped files and opens a file picker on click (`accept=".pdf,.docx,.md,.markdown,.txt"`). Files are added one at a time; each error goes through `reportError`.
  - A "Paste text" button opens a small dialog (title, textarea, a 200 KB counter). It reuses the existing overlay and button primitives, with no new visual language.
  - Each card gets a delete button with a confirm ("Delete {title}? Its passages go; old citations keep their quotes.").
  - ↻ Retry on `failed` and ↻ Index on `keyword_only` (key set) both call `reindexKnowledge`.
  - `indexing` cards show the stage and a bar fed by a `useKnowledgeProgress` hook (`onGlobal` filter).
  - The "Preview: final design by AI team" ribbon stays, because the final presentation is AI-stage. The v1.1 toasts go.
- **MockClient parity.** The pasted-text limit becomes 200 KB, and `forgetMemory` of an unknown ID rejects with `not_found`. New portable tests pin both.

## Risks / Trade-offs

- **Docling on CPU is slow and heavy (a 300-page scanned PDF can take minutes).**
  - Mitigations: one document at a time, below-normal priority, the page pre-check, the timeout, kill on cancel and parent-death exit.
  - The UI shows `extracting` progress, but no per-page percentage. Docling has no stable callback; we accept that.
- **The Docling API drifts between 2.x releases** (model download helper, page-break export, OCR engine).
  - Mitigation: all Docling calls live in `ai/docling_worker.py` behind a JSON protocol. Its tests use the `docling` marker and run locally after the user-approved install.
  - CI never imports Docling.
- **A Windows child process survives a hard kill of the server.** The parent-PID watchdog makes it exit within about 2 s. A job object would be stronger but adds win32 code.
- **The WAL `TRUNCATE` checkpoint can be blocked by a long-lived reader.**
  - Readers use short deferred transactions and SSE replays read in bounded pages, so this is rare.
  - Forget retries and then hands off to background retries.
  - The byte test runs with no concurrent readers. The spec states the guarantee holds "once no read is in progress".
- **`secure_delete` costs throughput.** Every delete writes zeros. At this scale (thousands of rows) it is unmeasurable, and it is the only way to honour D-70 at the file level.
- **FTS5 `secure-delete` on an older SQLite.** The startup check falls back to `optimize` after each Forget. Its cost is O(memory_fts size), which is small.
- **sqlite-vec internals.** Zero-then-delete relies on `vec0` UPDATE writing into the chunk blob in place. A spike test confirms it under 0.1.9 and fails loudly on upgrade.
- **Hash vectors in scripted mode make identical texts collide across worlds.** That is exactly what the isolation suite needs: it proves that partition keys and re-binding, not vector distance, keep worlds apart.
- **The naive knowledge block raises reply cost** (about 1.2k input tokens when hits exist). D-78 already budgets knowledge-heavy replies at 13–26 ⚡. It applies only to characters with knowledge or memories.
- **Re-chunking after a chunker version bump** gives new chunk IDs, so old citation chips can't highlight the passage. They still show their stored quote. `knowledge_chunk_redirects` is the AI-stage fix (doc 05 §6).
- **Scope.** This is the largest milestone (47 tasks, many of them multi-part, against 64 smaller ones in M3). It stays one change because every part shares the embedder, the spaces and the scrub path. Splitting would mean two migrations and two passes over `sessions/turn.py`. Task groups are ordered so each ends green.

## Migration Plan

- Alembic **`0002_knowledge_memory`**:
  - `ALTER TABLE knowledge_sources ADD COLUMN embed_sent_at TEXT NULL`;
  - `INSERT INTO memory_fts(memory_fts, rank) VALUES('secure-delete', 1)` and the same for `knowledge_fts` (guarded by the SQLite version);
  - no downgrade, as per project policy. The backup is a copy of `data/`.
- **Existing databases.** Seed sources stay `keyword_only`. User data has no knowledge yet (the M4 HttpClient refused uploads).
- **Startup order** gains the following steps after job recovery:
  1. the ingestion recovery (D2);
  2. the FTS5 secure-delete check;
  3. a log line for the embedding model mismatch (D7);
  4. the background re-embed (D8), when a key is set;
  5. the sweeper's knowledge and tmp scope.
- **Rollback** = check out the previous `dev` and restore `data/`. Column `embed_sent_at` is unused by older code, so an un-restored DB still works.
- **Docs and decision log:**
  - D-91 Index seed knowledge = per-source button;
  - D-92 retrieval in the runtime with hits in the context;
  - D-93 naive prompt v2 knowledge-and-memory block;
  - D-94 Forget byte-level hygiene;
  - D-95 the active space, not `models.embedding`, picks the embedding model;
  - D-96 document conversion is not key-dependent, and PDF/DOCX fail actionably without Docling;
  - D-97 query embedding only for user messages to characters with vectors;
  - D-98 reset demo returns seed knowledge to keyword-only;
  - D-99 an in-flight embedding batch at a crash ends `keyword_only` until a user Retry.
- Pages to update: doc 01 §4.2 (the retrieval step), doc 02 §2 (`data/tmp`), §3.7, §3.8, §3.9 and §4, doc 03 (the knowledge route status codes), doc 04 §1 (the embedder model source) and doc 05 §2.2, §4 and §5.

## Open Questions

- **Docling's exact model download and OCR APIs in the installed 2.x version.** This changes only the internals of `ai/docling_worker.py` and `horizon models fetch`. It is resolved during apply, after the user approves the install.
- **Default `convertTimeoutMs` (600 s).** It is a config knob; tune after the first real scanned-PDF run on this machine.
