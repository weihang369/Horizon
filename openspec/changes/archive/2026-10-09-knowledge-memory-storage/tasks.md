# Tasks

> **Constraints for every task:**
> - No network in automated tests (the socket guard stays); only the in-process fake provider and obviously fake `sk-or-test-…` keys. The real key is never printed, logged or put in fixtures.
> - No contract change: `schemas.ts`, `types.ts` and `schema.json` stay as they are, and `npm run export-schema` shows no drift.
> - New background work starts only through `rt.spawn`, and new waits use activity-aware `Slots`, so `/_test/clock` settles.
> - Commit at green group boundaries, without Claude attribution. Nothing is pushed.
> - **Ask the user first** before running `npm run setup:docling`, `horizon models fetch` or any paid live test.
>
> Each numbered group ends with its own tests and docs green. Decision-log rows land with the group that implements them.

## 1. Storage foundations and spikes

- [x] 1.1 Add spike tests under `backend/tests/spikes/`. Verify they pass on Windows:
  - **(a)** a `vec0` `UPDATE … SET embedding = zeros` rewrites the vector in its chunk blob in place under sqlite-vec 0.1.9 (read the shadow `_vector_chunks` blob before and after);
  - **(b)** FTS5 `secure-delete = 1` removes a deleted row's terms from `memory_fts_data` (a byte search for a unique term finds nothing after delete + commit);
  - **(c)** with `PRAGMA secure_delete = ON` on the writer, a deleted row's text is absent from `horizon.db` after `wal_checkpoint(TRUNCATE)`, and `horizon.db-wal` is 0 bytes;
  - **(d)** a `TRUNCATE` checkpoint reports busy while a reader transaction is open and succeeds after it closes.
- [x] 1.2 Write Alembic `0002_knowledge_memory`:
  - add `knowledge_sources.embed_sent_at TEXT NULL`;
  - set FTS5 `secure-delete` on `memory_fts` and `knowledge_fts` when SQLite ≥ 3.44;
  - add a startup check that records whether FTS secure-delete is active (the fallback flag, design D16);
  - add `PRAGMA secure_delete = ON` to the **writer** engine only, in `db/engines.py`.

  Verify with a migration test:
  - the column exists;
  - `memory_fts_config` holds `secure-delete = 1`;
  - the writer reports `secure_delete = 1`, readers report 0;
  - upgrading an M4-shaped database keeps its rows.
- [x] 1.3 Extend `db/spaces.py` (design D9) with `create_building(spec)` (tables + delete triggers), `non_retired()`, `building()` and `flip(building_id)` (one transaction: building → active, active → retired, `knowledge_sources.embedding_space_id` moved for fully-embedded sources). `drop_retired` stays at startup.

  Verify with unit tests:
  - a building space has its tables;
  - flip leaves exactly one active space;
  - after a restart the retired tables are gone;
  - `ensure_active` stays idempotent.
- [x] 1.4 Scaffold the new modules:
  - `services/knowledge/` (`validate.py`, `worker.py`, `pipeline.py`, `recovery.py`);
  - `services/memory/` (`store.py`, `forget.py`);
  - `ai/embedder.py`, `ai/chunker.py`, `ai/converter.py`, `ai/docling_worker.py`, `ai/retrieval.py`.

  Then:
  - extend mypy strict to them;
  - extend the static test so these packages can't call `asyncio.create_task`;
  - add the `docling` pytest marker (deselected by default, like `live`).

  Verify: `uv run mypy`, `ruff` and the static test are clean.
- [x] 1.5 Update doc 02 §2 (`data/tmp/`, the `data/models/.horizon-models.json` marker), §3.8 (`embed_sent_at`) and §3.9 (building spaces, the flip transaction, file hygiene settings). Verify the doc's table names and columns match `db/tables.py` and `0002`.

## 2. Embedder

- [x] 2.1 Add `gateway.simulated_embedding(texts, ctx, *, space, before_send=, commit_with=)`. It runs the paid-call pipeline per batch of ≤ 32: key check, preflight with caps and holds, one row with category `embedding`, `provider: "scripted"`, `model = space.model`, `tokens_in = Σ count_tokens`, priced by `estimate_embedding`, and D-84 hooks. It returns `unit_vector(sha256(kind+text), dims)`.

  Verify with unit tests for the provider-gateway "Scripted embedding source" scenarios:
  - one row for a three-paragraph source, with `tokensIn > 0`;
  - no socket opened;
  - identical unit vectors across runs;
  - a cap refusal runs no hooks.
- [x] 2.2 Implement the `Embedder` port in `ai/embedder.py` (design D7):
  - `HashEmbedder` (scripted, through 2.1);
  - `QwenEmbedder` (naive): the active space's model, provider and dims through `gateway.embed(dimensions=)`; queries wrapped `Instruct: …\nQuery: …`; truncate + L2-renormalise longer vectors; a shorter or non-finite vector is `malformed`;
  - an LRU of 4 096 entries keyed `(space.id, kind, sha256(text))`;
  - purposes `embed_doc` / `query_embed`;
  - a once-per-start log line when `settings.models.embedding` ≠ the active space's model.

  Teach the fake provider `dimensions` plus test modes returning 4 096-dim and 512-dim vectors.

  Verify with tests for every embedding-spaces scenario:
  - an edited `models.embedding` still bills the space model;
  - query requests carry the instruction and passages don't;
  - 4 096 → 1 024 unit vectors, and 512 is `malformed`;
  - the second identical query makes no request and no row;
  - no key means no request and no row;
  - 70 texts → 3 `embed_doc` rows with no energy change.
- [x] 2.3 Extend `ai/profile.py` with the ports `embedder`, `knowledge_retriever`, `memory_retriever` (naive implementations), `memory_writer` (scripted `[]` in both profiles) and `converter`. The converter is not key-dependent: Docling by default, and `ScriptedConverter` by default when `HORIZON_TEST=1`; `HORIZON_AI_CONVERTER` overrides. Let `POST /_test/ai-profile` accept the new port overrides.

  The converter and retriever *builders* land with their classes (4.2, 5.1, 7.2); this task fixes the selection rules.

  Verify with tests for the ai-ports "AI profile selection" rules: override one port, the converter chosen without a key and outside the profile, and deterministic conversion in test mode. The end-to-end "Real conversion without a key" scenario is verified in 5.2 with a stub converter.
- [x] 2.4 Update doc 04 §1 (the embedder takes its model and dims from the active space; `embed_doc`/`query_embed`; the LRU) and doc 05 §2.2 (Embedder, DocumentConverter, retriever rows; the converter isn't key-dependent). Add decision-log rows **D-95** (the active space, not `models.embedding`, picks the model) and **D-96** (conversion isn't key-dependent; PDF/DOCX fail actionably without Docling; test mode is deterministic). Verify the docs name the same ports and env vars as `ai/profile.py`.

## 3. Knowledge upload and validation

- [x] 3.1 Implement `services/knowledge/validate.py` (design D3):
  - extension and declared-MIME agreement;
  - `%PDF-` within the first 1 KB;
  - DOCX = a ZIP whose names include `word/document.xml`, judged from the names only;
  - MD/TXT = strict UTF-8 (BOM allowed), no NUL;
  - pasted text: a title, non-blank, ≤ 204 800 bytes.

  Fixtures are generated in the tests (a minimal PDF, DOCX and XLSX via `zipfile`, invalid UTF-8). Verify with unit tests covering every knowledge-sources "Accepted inputs" scenario, including the spreadsheet renamed `.docx` and the binary `notes.txt`.
- [x] 3.2 Add `POST /characters/{id}/knowledge`:
  - **Content-Type dispatch:** multipart is a file, JSON is text, anything else is a 422 `validation`.
  - **Counted streaming** to `data/tmp/{uuid}.upload` (413 with `details.limit: 10485760`), reusing the cover route's parser.
  - **The idempotency middleware's `body_limit()`** covers the knowledge path.
  - **One transaction:** the 20-source count (`details.limit: 20`), duplicate SHA-256 → `conflict` with `details.existingSourceId`, and a `queued` row. The original is moved to `knowledge/{w}/{c}/{sid}/original.{ext}` before the commit and removed if the commit fails.
  - A tombstoned or unknown character → `not_found`.
  - 201 + `entity.changed{kind:"knowledge"}` after the commit.
  - Submission to the worker is stubbed until group 4.

  Verify with integration tests for the http-api scenarios (pasted text 201 valid against `schema.json`, `text/plain` 422, a chunked 11 MB upload 413, a keyed 11 MB upload 413) plus: 21st source, same file twice, CSV, `notes.html`, fake PDF, a 210 KB paste, no `entity.changed` on a rejected upload, and no stray file in `data/tmp` or `knowledge/` after any rejection.
- [x] 3.3 Update doc 03 (the knowledge route's 201/413/422 and `details` fields; the memory route). Verify it matches the integration tests' expectations.

## 4. Chunker, ingestion worker and knowledge lifecycle

- [x] 4.1 Implement `ai/chunker.py` (`para@1`, tokenizer `utf8/4`; design D6):
  - children = the mock's `paragraphs()` (heading lines are their own passage, long paragraphs are cut at a sentence end near 900 chars);
  - sections = runs under one heading path, capped near 1 500 tokens;
  - `<!-- page N -->` → `p. N` / `pp. N–M`, otherwise `§ Heading`, otherwise `¶ N`;
  - `char_start`/`char_end` index `extracted.md`.

  Verify with unit tests: `# Soups\n\nMiso first.\n\nThen tofu.` gives exactly those three passages; a page-2 sentence gets `p. 2`; a 3 000-char paragraph is cut; offsets slice back to each child's text.
- [x] 4.2 Implement `ScriptedConverter` in `ai/converter.py`:
  - plain UTF-8 read for MD/TXT/text;
  - deterministic placeholder passages for PDF/DOCX, the same rule as `mock/engines/knowledge.ts`, with `p.`/`§` locators;
  - the `DocumentConverter` protocol and a readiness function (`not_installed` / `models_missing` / `ready`, where `ready` needs the marker file, design D5).

  Point `/health`'s `docling_status` at it. Verify with unit tests, and that health reports `models_missing` for a non-empty `models/` without the marker.
- [x] 4.3 Implement `IngestionWorker` (design D1, D7, D8, D19):
  - `submit`, `cancel`, `cancel_for(character|world)`, `stop`;
  - `docling_slots(1)` and `embed_slots(2)`;
  - compare-and-set status transitions; the chunk swap in one transaction; the 3 000-passage check;
  - a key check before embedding (no key → `keyword_only`, no call);
  - embedding batches for every non-retired space, with `before_send` setting `embed_sent_at` and `commit_with` writing vectors and clearing it in the ledger transaction;
  - the terminal status derived from vectors in the active space;
  - progress events per D19, rate-limited to 250 ms of clock time.

  Wire the route from 3.2 to it. Verify with integration tests:
  - Markdown with a key → `indexed`, exactly 1 `embedding` row, ≥ 3 schema-valid progress events with non-decreasing `pct` over all three stages, then a final event without progress;
  - no key → `keyword_only` with no row;
  - cap reached → `keyword_only` with no `error`;
  - 70 paragraphs → 3 rows;
  - 2 990 + 20 passages → `failed` with 2 990 kept;
  - an empty `.md` → `failed` "no readable text".
- [x] 4.4 Implement startup recovery (design D2 table) and background re-embed (design D8: at startup with a key, and when the key becomes `set`; user sources only; `embed_sent_at IS NULL`). Add a fake-provider hook that parks the Nth embeddings request.

  Verify with tests for the knowledge-sources "Indexing survives a restart" scenarios:
  - **Crash between batches:** only batch 3 is sent, and 3 rows exist in total.
  - **Crash during a batch:** no request after the restart, the source is `keyword_only`, and a user reindex finishes it.
  - **Restart while chunking:** the source resumes.
  - **Key added after an upload:** the user source ends `indexed` and seed sources stay `keyword_only`.
- [x] 4.5 Add `DELETE /knowledge/{id}` and `POST /knowledge/{id}/reindex` (design D18; knowledge-sources "Reindex" and "Delete a source"):
  - **Delete:** cancel first, then one transaction, then `rmtree`. `not_found` twice.
  - **Reindex:** from the lowest stale layer when there is an original; re-embed only when there isn't (chunk IDs kept); `conflict` when indexing or `url`.
  - **Callers of `worker.cancel_for` / `stop`:** character delete, world delete, reset demo (seed sources return to `keyword_only`) and factory reset.
  - **The sweeper** removes `data/knowledge/**` and `data/tmp/*.upload` orphans older than 1 hour.

  Verify with tests:
  - delete while indexing leaves no rows, vectors or files, and nothing resumes after a restart;
  - a cited source deleted keeps its message citations;
  - a seed reindex with a key → `indexed` with identical chunk IDs;
  - reindex while indexing → `conflict`;
  - the demo-data "Indexed seed source after reset" scenario;
  - "Reset during a conversion" with a stub converter;
  - "Orphaned knowledge folder".
- [x] 4.6 Update doc 02 §3.8 (pipeline, statuses, recovery table, locators, re-embed triggers) and §4 (lifecycles cancel ingestion; reset → seed `keyword_only`), and doc 01 §4.4 (the ingestion worker and its slots). Add decision-log rows **D-91** (Index seed knowledge = per-source button), **D-98** (reset demo returns seed knowledge to keyword-only) and **D-99** (an in-flight embedding batch at a crash → `keyword_only` until a user Retry). Verify the docs and the tests agree on every status transition.

## 5. Docling converter and models fetch

- [x] 5.1 Implement `DoclingConverter` (design D4):
  - `subprocess.Popen([sys.executable, "-m", "horizon.ai.docling_worker", …])`, waited on with `asyncio.to_thread`;
  - environment `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `OMP_NUM_THREADS`; below-normal priority;
  - `convertTimeoutMs` (default 600 000) → kill, reap, remove the temporary output, `failed` "took too long";
  - cancel → kill;
  - the JSON result protocol (`pages` | `error` + `reason` ∈ `page_limit`/`encrypted`/`unreadable`).

  Implement the `ai/docling_worker.py` shell: argument parsing, the protocol, the parent-PID watchdog thread, and a pluggable convert function. Verify with tests that drive the protocol with a **stub worker command** (no Docling), all of which leave no child process (`psutil`-free check via `Popen.poll`):
  - success, timeout, cancel during conversion, a crash exit and a page-limit exit;
  - the watchdog exits when the parent PID is gone.
- [x] 5.2 Make PDF/DOCX fail actionably when conversion is unavailable: `failed` naming `npm run setup:docling` and `horizon models fetch`, with the original kept. Verify with tests for the document-conversion scenarios "PDF before setup" and "Retry after setup" (the stub converter becomes ready → reindex → real passages).
- [x] 5.3 Add `horizon models fetch` to `cli.py`:
  - with Docling missing it exits non-zero naming `npm run setup:docling` and downloads nothing;
  - otherwise it downloads into `data/models/`, then writes `.horizon-models.json`;
  - an interrupted fetch leaves no marker.

  Verify with CLI tests (Docling import absent; the download function stubbed to succeed and to fail midway) and with health reporting `ready` only with the marker.
- [x] 5.4 **[Needs the user's go-ahead: multi-GB download]** Run `npm run setup:docling` and `horizon models fetch` on this machine. Then:
  - fill in the real convert function in `ai/docling_worker.py`: a pypdfium2 page pre-check, `artifacts_path`, OCR enabled, Markdown with `<!-- page N -->` markers;
  - verify the Docling 2.x API against the installed version;
  - run `uv run pytest -m docling`: a generated 3-page PDF gives locators `p. 1`–`p. 3`; a generated DOCX with headings gives `§` locators; a Pillow-made image-only PDF ("The night shift starts at seven") yields that text; a generated 412-page PDF fails in under 5 s naming 412 and 300; no network request is made during conversion (socket guard).
- [x] 5.5 Update doc 01 §6/§8 (setup step 2 now includes `horizon models fetch`), doc 02 §2 (`models/` marker), and the backend README section on Docling if one exists. Verify that `horizon --help` lists `models fetch` as documented.

## 6. Memory store and Forget

- [x] 6.1 Implement `services/memory/store.py` `MemoryStore.apply(character_id, world_id, ops)` (design D17):
  - validate the whole batch (unknown, other-character or other-world IDs; importance outside [0, 1]);
  - embed `Insert`/`Supersede` texts before the writer lock, for every non-retired space, only with a key;
  - one transaction for rows, FTS, vectors, `superseded_by`, `importance`, `last_recalled_at` and `recall_count`;
  - a per-character `asyncio.Lock`;
  - publish `entity.changed{kind:"memory", id: characterId, worldId}`.

  Verify with tests for the long-term-memory scenarios "One bad operation", "Supersede", "Another world's memory" and "Two sessions at once".
- [x] 6.2 Add one helper deriving `trace_memory_refs` from `trace.memory.recalled[]`, used by `sessions/writer.py` on every `insight`, by `sessions/lifecycle.fork` (new message IDs) and by the seed import. Verify:
  - a live insight with recalled memories writes refs;
  - forking the seed session whose insight recalls a memory gives the fork's messages their own refs;
  - seed import counts are unchanged.
- [x] 6.3 Implement Forget (design D16) in `services/memory/forget.py` and `DELETE /memory/{id}`:
  - the chain fixpoint;
  - zero vectors, then delete;
  - rewrite `turn_traces` and `insight` payloads via refs plus the `instr()` pass;
  - delete the refs;
  - a purge row `{scope:"memory", ids:{memoryItemIds, characterId, messageIds}}`;
  - after the commit, a `scrub_memory` inbox message to each live actor (its in-memory state drops the text), then `entity.changed`, then `wal_checkpoint(TRUNCATE)` (5 × 100 ms retries, then a background retry);
  - `not_found` for an unknown ID.

  Change the MockClient's `forgetMemory` to reject an unknown ID with `not_found`.

  Verify with tests for:
  - "Forget the current version" (the chain);
  - "Unknown memory" (backend);
  - "Recalled in a seed debate and a fork";
  - "Open session" (live actor);
  - message contents unchanged.
- [x] 6.4 Add the byte-level test to `tests/isolation/`:
  1. Insert a memory containing a unique word through `MemoryStore.apply`.
  2. Get it recalled in a live turn (an overridden turn engine emits a `memory.recalled` TracePatch).
  3. Fork that session, then Forget the memory.
  4. With no reads in progress, assert that neither the text nor the word occurs in the bytes of `horizon.db`, `horizon.db-wal` or `graph.db` (if present).

  Also run it with the FTS secure-delete fallback forced (the `optimize` path). Verify both variants pass.
- [x] 6.5 Extend `AiStateHooks` with `on_forget(memory_item_ids, character_id, message_ids)` (default no-op). The purge worker dispatches the `memory` scope (object `ids`) to it and handles the other scopes as before. Verify:
  - the ai-ports "Forget reaches the forget hook" scenario;
  - the long-term-memory "Retried after a crash" scenario (stop before delivery → delivered after restart, marked done).
- [x] 6.6 Add the post-turn memory queue (design D17): after a `complete`, unblocked reply, call `MemoryWriter.after_turn` for the speaker, then `apply`; log failures. On a guardrail block, skip the writer, and in the scrub transaction forget any memory whose `source_message_id` is the blocked message (session-runtime delta).

  Verify with tests:
  - the default writer leaves memory unchanged;
  - a failing writer leaves the session normal and logs;
  - "Blocked reply leaves no memory" (a remembering writer plus a blocking guardrail);
  - the existing "Blocked after streaming" test still passes.
- [x] 6.7 Update doc 02 §3.7 (`apply`, Forget steps and file hygiene) and §4 (Forget, guardrail memory side), and doc 05 §4 (`on_forget`, object payload). Add decision-log row **D-94** (Forget byte-level hygiene: `secure_delete`, FTS5 secure-delete, zeroed vectors, WAL truncate). Verify that doc 02's Forget steps match `forget.py` step for step.

## 7. Retrieval and turns

- [x] 7.1 Implement the FTS query builder in `ai/retrieval.py` (design D13): Unicode word tokens ≥ 2 chars, lower-cased, de-duplicated, ≤ 16, each quoted, joined with `OR`; empty → no query. Route `reads.fts_search`/`memory_fts_search` through it. Verify with unit tests: the retrieval "Message full of syntax" scenario runs without error and matches on the plain words, and an empty or punctuation-only query returns nothing.
- [x] 7.2 Implement the retrievers (design D13):
  - **Scripted:** knowledge = FTS top 5; memory = 3 most recent current items.
  - **Naive:** knowledge = FTS 20 ∪ `vec0` KNN 20 (`character_id` partition + world/character re-bind on join), RRF k = 60, top 5, score = rrf/(2/61) clamped; memory = FTS top 3 over current items.
  - k values from config `retrieval.*`.

  Verify with tests:
  - "Keyword-only seed knowledge is still found" (Amara + burnout);
  - "Meaning match" (hand-placed vectors);
  - "Superseded memory never recalled";
  - every score in [0, 1].
- [x] 7.3 Add the frozen hit types to `ai/contexts.py` (`KnowledgeHit`, `MemoryHit`; `TurnContext.knowledge/memory`). Add the runtime retrieval step to `TurnRunner.run` and to prefetch construction, scoped from the runtime's speaker row (design D10). The query text is the prompt, else the latest message, else the motion or premise. Verify:
  - the ai-ports "Context round-trips through JSON" test with hits;
  - "Retrieved hits are in the context";
  - a test engine that records its context sees only the speaker's world and character.
- [x] 7.4 Implement the query bundle (design D12). On `send` (1:1 and group), `rt.spawn` the query embedding when the knowledge retriever `uses_vectors`, the key is set, and an eligible responder has vectors (an indexed `EXISTS` per send; see the D12 apply note). Responders await it for at most `retrieval.queryEmbedWaitMs` (400); otherwise they use FTS only. A cap or provider failure → FTS only, with no `error` event. The `query_embed` call appears on the first responder's `trace.calls`.

  Verify with tests for:
  - "Group message to three characters" (1 row);
  - "Nobody has vectors" (0 rows);
  - "Scripted profile" (0 rows);
  - "Slow embedding" (a parked fake request → FTS-only reply; the late row is still recorded);
  - "Cap reached" (no `error` event);
  - existing M3 tests counting rows or `trace.calls` stay green.
- [x] 7.5 Port `citations.ts` (`citeKnowledge`, `insertMarkers`, `liveCitations`) into the scripted turn engine (design D15). It uses its own RNG stream `{seed}:{turn}:cite`, inserts markers before streaming, sets `trace.knowledge` and `context.used.knowledge`, and doesn't use memory.

  Verify with tests for:
  - the retrieval "Live citations" scenario at the service level;
  - "Unchanged without knowledge" (a snapshot of contents and emotions for a no-knowledge character, recorded before the change);
  - `turn.end.citations` keeping only markers present.
- [x] 7.6 Add the naive engine prompt v2 (design D15): `PROMPT_VERSION = "v2"` (`"naive-2"`, following the M3 `"naive-1"` naming); when there are hits, one system block after the history (passages numbered with section text ≤ 1 200 chars, deduplicated by section; ≤ 3 memories; the cite-only-when-used line). Yield a `CitationMap` for every numbered passage. After the stream, set `trace.knowledge.retrieved` with `cited` flags, `trace.memory.recalled` and `context.used.memory/knowledge`. With no hits the request is byte-identical to v1.

  Verify with tests for:
  - "Cited passage" (fake chat answers containing `[2]`);
  - "Recalled memory in the trace" (and refs written via 6.2);
  - the no-hits request equals the v1 request.
- [x] 7.7 Extend `tests/isolation/` with two near-identical worlds whose characters share knowledge text, memory text and (hash) vectors. Assert that FTS retrieval, vector KNN retrieval and memory recall in world A return only A's rows, through the retrievers and through a full scripted turn. Verify that the suite passes.
- [x] 7.8 Update doc 01 §4.2 (the retrieval step and query-bundle timing) and doc 05 §2.2, §4 (hits in the context instead of pre-bound retrievers) and §5 (prompt v2 block). Add decision-log rows **D-92** (retrieval in the runtime, hits in the context), **D-93** (naive prompt v2 knowledge-and-memory block) and **D-97** (query embedding only for user messages to characters with vectors). Verify the docs match the turn order in `sessions/turn.py`.

## 8. Embedding space switch

- [x] 8.1 Implement the `build_space(spec)` service (design D9): batch-embed every chunk and memory missing from the building space with the same hooks, a final catch-up pass, then `flip`. Make ingestion and `MemoryStore.apply` dual-write while a space is building (already routed through `non_retired()` in 4.3 and 6.1; this task adds the build itself).

  Verify with tests using a second test space `hash@64`, covering the embedding-spaces scenarios:
  - "Source added during a build" (vectors in both, still `indexed` after the flip);
  - "Atomic switch" (one active space, KNN answers from the new space only);
  - "Retired tables removed" after a restart.
- [x] 8.2 Update doc 02 §3.9 with the build service's steps and its lack of a route or UI. Verify the steps match `build_space`.

## 9. Clients and the Knowledge tab

- [x] 9.1 Implement `forgetMemory`, `addKnowledge` (`postForm` with a `file` part, or a JSON `POST`), `deleteKnowledge` and `reindexKnowledge` in `HttpClient.ts`, with `Idempotency-Key` on every `POST`. Drop the `later("M5")` entries, update `http.test.ts`, and set the harness to `supports: "M5"` in `clientContract.http.test.ts`.

  Verify:
  - the http-client "Upload a Markdown file over HTTP" scenario;
  - "Forget over HTTP";
  - "Nothing is held back in M5";
  - `npm run typecheck` is clean.
- [x] 9.2 MockClient parity: set the pasted-text limit to 204 800 bytes (`details.limit`) in `mock/engines/knowledge.ts` (Forget's `not_found` landed in 6.3). Add M5 portable tests:
  - Forget removes a memory, announces `memory`, and an unknown ID is `not_found`;
  - a 210 KB paste → `validation` with `details.limit: 204800`;
  - reindex while indexing → `conflict`.

  Verify that the portable suite passes on the MockClient with nothing pending.
- [x] 9.3 Wire the Knowledge tab (`features/profile/tabs.tsx`, `knowledge.ts`; design D20):
  - the drop zone and click-to-pick (`.pdf,.docx,.md,.markdown,.txt`), added one at a time, with errors through `reportError`;
  - a "Paste text" dialog (title, textarea, 200 KB counter) on the existing overlay and button primitives;
  - delete with a confirm;
  - ↻ Retry on `failed`, and ↻ Index on `keyword_only` while the key status is `set` (otherwise the "a key enables search by meaning" hint);
  - a `useKnowledgeProgress` hook showing the stage and a bar on indexing cards;
  - remove the v1.1 toasts; keep the ribbon.

  Verify with vitest tests: the Index button is rendered with a key and absent without one, the progress hook keeps the latest stage per source, and the paste dialog rejects an empty title and over-limit text.
- [x] 9.4 Run the portable suite on both clients: the MockClient run is complete, and the HTTP run with `supports: "M5"` against a test-mode backend passes every M1b–M5 test (including "live replies cite indexed passages"), with only M6 pending. Verify from both runs' output.

## 10. Integration checks

- [x] 10.1 Run every gate: backend `pytest` (default markers), `mypy`, `ruff`; frontend `typecheck`, `vitest`, `seed:check`; `npm run export-schema` with no drift; Playwright E2E on the MockClient. Verify that all are green, and record the counts in the apply summary.
- [x] 10.2 Run a real-server smoke on a spare port in test mode and in normal mode without a key. Check:
  - Markdown and pasted text reach `keyword_only` in normal mode without a key, and `indexed` in test mode with the fake key;
  - a PDF fails actionably with Docling absent (or converts, if 5.4 ran);
  - Index on a seed source;
  - delete removes the folder;
  - Forget returns 204 and the memory leaves the list;
  - `/health` reports the docling state.

  Verify each step's HTTP status and response.
- [x] 10.3 **[Paid; needs the user's explicit approval]** Add `tests/live/test_live_embedding.py` (`live` marker, skipped by default; checks only key presence, never prints it): one real batch of 3 short texts through `QwenEmbedder`. Assert 1 024 dims, unit norm ±1e-3, one `embedding` row with the space model, and cost > 0 and < $0.001. Run it once, only when the user approves. Verify the pass and its recorded cost.
