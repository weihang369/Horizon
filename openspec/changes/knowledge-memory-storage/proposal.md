# Proposal: knowledge-memory-storage (M5)

## Why

The backend can read knowledge and memory but not write them:
- `addKnowledge`, `deleteKnowledge`, `reindexKnowledge` and `forgetMemory` still reject on the `HttpClient` as "available in M5".
- Seed knowledge is keyword-only with no way to embed it.
- Live replies never cite anything.
- The Knowledge tab's drop zone and Retry only show a "v1.1 preview" toast.

M5 is the last storage milestone before HttpClient parity (M6). It makes ingestion, embedding, retrieval and Forget real, so the AI stage can swap policies (chunk sizes, rerank, memory writing) without backend rework (D-72).

## What Changes

- **Knowledge ingestion.**
  - `POST /characters/{id}/knowledge` takes a multipart file or JSON pasted text. The body is counted while it streams, the type is checked by magic bytes, the D-65 limits apply, and a duplicate is a conflict.
  - Ingestion runs as a durable per-source pipeline: original → `extracted.md` with page markers → sections and child chunks → FTS → vectors.
  - Progress is published as `entity.changed{kind:"knowledge", progress}`.
  - Restarts recover a source mid-pipeline without paying twice for an embedding batch.
  - `DELETE /knowledge/{id}` cancels in-flight work, then removes rows, vectors and files.
  - `POST /knowledge/{id}/reindex` re-runs from the lowest stale layer. A source with no original (seed) is only re-embedded, so its chunk IDs are kept.
- **Document conversion (D-62).**
  - Docling runs in a spawned subprocess, one document at a time, with a timeout and kill.
  - MD, TXT and pasted text never need Docling.
  - PDF and DOCX end `failed` with an actionable message while Docling is missing.
  - New `horizon models fetch` command.
  - Factory reset stops any conversion.
- **Embedder and spaces (D-64).**
  - Naive: Qwen3 Embedding 8B with the space's dimensions, a query instruction, truncate + renormalise, and an LRU cache.
  - Scripted: hash vectors billed as simulated spend (D-81).
  - One ledger row per batch.
  - Embedding failure ends `keyword_only`. Background re-embed covers user-added sources only.
  - The space switch dual-writes while building, then flips in one transaction. A second test space proves it.
- **"Index seed knowledge".**
  - The per-source ↻ **Index** button on keyword-only sources while a key is set, calling the existing `reindexKnowledge`.
  - No contract change. The user chose this on 2026-10-08.
  - Reset demo returns seed sources to `keyword_only`.
- **Long-term memory.**
  - `MemoryStore.apply(Insert | Supersede | Reinforce | Touch)` runs in one transaction, with a post-turn queue per character. `MemoryWriter` stays `[]` in both profiles.
- **Forget.**
  - Forget removes the whole supersede chain and scrubs `turn_traces` and `insight` event payloads to `"(forgotten)"`, including forks.
  - It queues the purge outbox and publishes `entity.changed{kind:"memory"}`.
  - The text is then gone from the database *files*: SQLite `secure_delete`, FTS5 `secure-delete`, zeroed vectors and a WAL `TRUNCATE` checkpoint.
  - A blocked reply's memory side is closed too (session-runtime OQ-8).
- **Retrieval.**
  - One `QueryBundle` per triggering user message, embedded in parallel with routing and only when it can pay off.
  - `MemoryRetriever`: scripted = most recent k, naive = FTS5.
  - `KnowledgeRetriever`: scripted = FTS5, naive = FTS5 + vector + RRF.
  - The runtime runs the retrievers in the speaker's scope and hands the hits to the engine inside the frozen `TurnContext`.
  - The scripted engine cites like the mock, which unblocks the M5 portable citation test.
  - The naive engine gets a minimal, versioned knowledge-and-memory block (prompt v2).
- **Clients and UI.**
  - HttpClient: knowledge (full) and memory (full). The portable HTTP harness moves to `supports: "M5"`.
  - Knowledge tab: drop zone and file picker, a "Paste text" dialog, per-source delete with confirm, ↻ Retry on failed sources, ↻ Index on keyword-only sources, live stage progress.
  - MockClient parity fixes: the pasted-text limit is 200 KB (D-65), and Forget of an unknown memory is `not_found`.
- **Storage.**
  - Alembic `0002` adds `knowledge_sources.embed_sent_at` and turns on FTS5 `secure-delete`.
  - Trace memory refs are written by every trace path (live insight, fork, seed).
  - The sweeper also covers `data/knowledge/`.
- No contract (`schemas.ts` / `schema.json`) change. **No BREAKING changes.**

## Capabilities

### New Capabilities
- `document-conversion`: turning uploaded PDF and DOCX into Markdown with page markers out-of-process: Docling availability, timeouts and cancel, model fetching, and the plain-text path for MD, TXT and pasted text.
- `embedding-spaces`: the embedder (naive and scripted), its cache, query and document forms, dimension handling, and the lifecycle of embedding spaces (dual-write build, catch-up, atomic flip, retire).
- `long-term-memory`: the memory write API (`MemoryStore.apply`), per-character serialisation, the post-turn memory queue, and Forget with its guarantee that forgotten text leaves the database files.
- `retrieval`: the per-message query bundle, memory and knowledge retrievers bound to the speaker's scope, the hits handed to turn engines, and the citations they produce.

### Modified Capabilities
- `knowledge-sources`: upload validation (magic bytes, the 200 KB pasted-text limit, the page and chunk limits), the durable pipeline and its restart recovery, reindex by stale layer, delete cancelling in-flight work, the UI actions (paste, delete, Retry, Index) and keyword-only background re-embedding.
- `ai-ports`: new ports (`Embedder`, `DocumentConverter`, `KnowledgeIndexer`, `MemoryRetriever`, `KnowledgeRetriever`, `MemoryWriter`) and their profile rules; turn contexts carry retrieved hits; purge hooks gain the `memory` scope and `on_forget`.
- `session-runtime`: a blocked reply is also excluded and scrubbed on the memory side.
- `provider-gateway`: a scripted embedding source billed through the pipeline.
- `http-api`: knowledge and memory write routes, and the 10 MB upload limit on the knowledge route.
- `http-client`: knowledge and memory methods over HTTP; nothing is "available in M5" any more.
- `client-contract`: the portable HTTP harness supports M5.
- `local-backend`: startup recovers ingestion and sweeps knowledge folders; factory reset stops document conversion; the CLI adds `models fetch`.
- `demo-data`: reset returns seed knowledge to keyword-only and cancels its in-flight indexing.
- `event-streams`: knowledge and memory changes are announced.

## Impact

- **Backend, new code:**
  - `services/knowledge/` (validation, pipeline, worker, recovery);
  - `services/memory/` (store, Forget, scrub);
  - `ai/embedder.py`, `ai/chunker.py`, `ai/converter.py` (+ the `ai/docling_worker.py` subprocess entry);
  - `ai/retrieval.py` (query bundle, retrievers, FTS query builder).
- **Backend, changed code:**
  - the `ai/ports.py` and `ai/contexts.py` additions; `ai/profile.py` ports;
  - the scripted and naive turn engines (citations, prompt v2);
  - `sessions/turn.py` (the retrieval step), `sessions/writer.py` and `sessions/lifecycle.py` (trace memory refs);
  - `db/engines.py` (`secure_delete` on the writer), `db/spaces.py` (building spaces), Alembic `0002`;
  - `api/` knowledge and memory routes and the idempotency body limit;
  - `runtime.py` (worker, slots, recovery, sweeper), `cli.py` (`models fetch`);
  - `services/characters.py`, `worlds.py` and `seed.py` (cancel and reset).
- **Frontend:**
  - `client/http/HttpClient.ts`, `http.test.ts` and `clientContract.http.test.ts` (`supports: "M5"`);
  - `features/profile/tabs.tsx` and `knowledge.ts` (wiring, paste dialog, delete confirm, progress);
  - `mock/engines/knowledge.ts` and `MockClient.ts` (parity fixes).
- **Dependencies:** none in the core install. Docling stays the optional `docling` group (setup step 2). Installing it or fetching models on this machine needs the user's go-ahead (multi-GB).
- **Docs:**
  - `docs/backend/01`, `02`, `03`, `04` and `05` (retrieval step, Forget file hygiene, space switch, embedder model source, naive prompt v2);
  - `docs/requirements/09-decision-log.md` (D-91 onward).
- **Cost:**
  - ingestion embeddings cost about $0.01/M tokens; a 300-page PDF costs about $0.002;
  - a query embedding costs about $0.000001 per user message, and only for characters that have vectors;
  - the naive knowledge block adds about 1.2k input tokens to replies that retrieve;
  - the paid live check is one embedding batch, under $0.001, and runs only on explicit approval.
