# 06: Milestones (one OpenSpec change each)

> **v1.0.** This revision applies the review debate (Rounds 1–2, 2026-10-03).

**Loop:** `openspec propose` (from this pack) → review → `openspec apply` → tests green → `openspec archive` → squash merge to `dev`. **One branch per milestone:** `feat/<change-name>` (e.g. `feat/backend-foundation`), cut from `dev` and squash-merged back after its change is archived.

**Each milestone ships the HttpClient methods for its own routes**, so the app runs against the backend from M1b onwards. M6 only closes parity and E2E.

## M1a: `contract-rev-1-3` (frontend only)
**Scope**
- Contract rev 1.3 (doc 03 §7): doc 05, `types.ts`, `schemas.ts` and the drift reconciliation.
- **MockClient parity:**
  - the new error codes;
  - knowledge add/delete/reindex and cover upload (mocked);
  - the tombstone;
  - seed-only reset (user forks survive);
  - the top-up gate (D-76);
  - `estReplyPoints`;
  - `task.update` on the global stream.
- **Seed fixes** via `scripts/seed-build` and `pricing.config.ts`:
  - D-61 image model and price;
  - Jev $0.042/M with free output;
  - an embedding price entry;
  - Amara's source `url → file`;
  - Mei's CSV source removed;
  - **globally unique candidate IDs**.
- `npm run export-schema` writes `backend/horizon/contract/schema.json`.
- `clientContract.test.ts` is split into portable and mock-only tests.
- Shared fixture files (energy, reducer) go in `backend/tests/fixtures/`, consumed by the TS tests too.

**Acceptance**
- `seed:check`, unit tests and the existing E2E suite pass on the MockClient.
- The schema exports deterministically.

## M1b: `backend-foundation`
**Scope**
- **Spikes first:**
  1. sqlite-vec under aiosqlite via `run_async` (Windows/macOS/Linux CI);
  2. FTS and vec triggers firing on FK-cascade deletes;
  3. resolution of the `pytorch-cpu` uv index (torch + torchvision).
- The `backend/` scaffold: uv, the app factory, config, logging, the CLI, the writer and reader engines.
- Alembic `0001_initial` (every ordinary table in doc 02, including `session_summaries`, `message_citations`, `trace_memory_refs`, `idempotency_keys`, `ai_purge_queue`, `usage_records.purpose`, the memory and knowledge `rid` columns) + the SpaceManager (default space tables + triggers).
- **`reducer.py`** (a port of `sessionReducer.applyEvent`) + the cross-language fixture test.
- **Seed import** (validate, normalise timestamps, reduce-and-assert, synthetic sections, FTS) + reset-demo (upsert) + factory reset (the Windows-safe sequence).
- **EventBus + global SSE.**
- **World CRUD** (with the delete cascade and folder removal).
- All **read** endpoints, `/assets` resolution, the error envelope, pagination, the idempotency middleware, `/health`, `/_test/*`.
- Root `package.json` (`setup` in two steps, `dev` with concurrently, `demo`) and the Vite proxy.
- **HttpClient:** settings get, worlds (full), the read methods for characters, sessions, usage, memory and knowledge, **job reads (`jobs.get`, `listActive`, `subscribe` as snapshot + global filter)**, `sessions.events`/`subscribe` (replay only), `onGlobal`. Job writes stay in M4.
- **`HorizonClient.admin.resetDemo()`** (rev 1.3 addendum, OQ-5 of `contract-rev-1-3`): the Settings and World Select "Reset demo data" buttons move from the mock-only dev API to it, on both clients.
- **An HTTP harness for the portable contract suite** (`runPortableContract`, driven through `/_test/*`).

**Acceptance**
- With `npm run dev` and `VITE_HORIZON_CLIENT=http`, both seed worlds can be browsed, every profile opens and **every seed session replays** from the backend.
- World create/rename/delete works.
- Every response validates against `schema.json`.
- `reduce(seed events) == seed messages` holds in both languages.
- The isolation suite passes.

## M2: `gateway-ledger-energy`
**Scope**
- Key handling (`PUT /settings/key`, the secrets file, status), `PATCH /settings`, `testConnection`, `testModel`.
- The gateway clients (`ChatRequest`/`ChatChunk`, decisions, images, embeddings, meta), with routing, per-purpose timeouts, retries only when nothing was charged, error mapping, redaction and the `on_call` hook.
- **The reservation book.**
- The ledger with `purpose`, `cost_source` and the estimate→actual correction.
- Pricing and the peak clock; the caps and the warning on crossing.
- The energy domain (shared fixtures with `energy.ts`, REAL storage, demo-mode freeze), top-up (D-76) and set-max.
- The `Decider` (+ scripted fixtures, partial fallback).
- HttpClient: settings (full), energy.

**Acceptance**
- Recorded-HTTP (respx) tests cover each client and every ErrorCode.
- The key is absent from logs, errors, the ledger, exports and SSE.
- Concurrent preflights can't overshoot by more than Σ(actual − estimate).
- A cancelled stream gets an estimate row that is later corrected.
- The energy fixtures pass in Python and TS.

## M3: `session-runtime`
**Scope**
- The SessionActor (inbox for **all** session writes, the liveSession() preconditions, `messageId` allocated first, TracePatch merging, the full insight, prefetched openings N ≤ 2 with the D-77 drain), the LiveSessionManager, token coalescing, SSE resume (`max(sinceSeq, Last-Event-ID)`).
- Session create/fork (event cut + re-reduce)/rename/delete/leave/end; **every** chat, debate and watch command; the debate phase machine; watch pacing via `clock.sleep`; Markdown export.
- **Ports:**
  - `TurnEngine` (§2.1 events), `Router` (with `queue`), `ReactionPredictor`, `DebateHost`, `WatchDirector`, `Summariser` (`session_summaries`) and `Guardrail` (incl. the block scrub), each with a scripted placeholder;
  - the **naive DeepSeek `TurnEngine`** (cache-friendly window, tag parser) and the **Jev `Router`**;
  - `AiStateHooks` (no-op implementation) + the purge-outbox worker.
- `message_citations` written at `turn.end`.
- HttpClient: sessions, chat, debate, watch (full).

**Acceptance**
- 1:1, group, debate and watch run end to end in `scripted` mode (CI) and `naive` mode (manually, with a key).
- Stop or pause takes effect within 500 ms; a mid-stream reconnect loses and duplicates nothing.
- Replay equals what was seen live, and a fork at any `atSeq` equals the mock's.
- A second live session gets a 409; a paused 1:1 send auto-resumes.

## M4: `generation-jobs`
**Scope**
- The JobScheduler and workers (semaphores, one non-terminal job per character, the `provider_called_at` restart rule); job events mirrored onto the global stream; estimate/start (with reservation)/cancel/retry.
- `characters.update` (PATCH, deep-merge, version bump), `profile_draft`/`profile_regenerate` (naive), `portrait_candidates`/`portrait_tweak` (with `job_id` batches), `lockPortrait`, `emotion_set`/`emotion_regenerate`/blink (Seedream 5.0 Flash + `ImagePromptCompiler` v2), originals first then WebP, asset versions + `acceptAssetVersion`, `song` (Lyria + the ambient fallback).
- approve/archive/restore/**delete (tombstone, 409 while streaming)**; world cover upload.
- **UI wiring for cover upload** in the World editor (`worlds.uploadCover`, already implemented by the MockClient in M1a; OQ-3).
- HttpClient: characters (full), jobs (snapshot + global filter).

**Acceptance**
- The full creation wizard works against the backend in `naive` mode.
- Killing the server mid-job and restarting **never pays twice** (asserted with recorded HTTP).
- The creation cap blocks before spending.
- Assets are ≤ 250 KB WebP.

## M5: `knowledge-memory-storage`
**Scope**
- `addKnowledge` (Content-Type dispatch, magic bytes, counted upload, limits)/`deleteKnowledge`/`reindexKnowledge` (re-embed only when there's no original).
- The `DocumentConverter` (Docling in a spawned process with a timeout and cancel; health `not_installed`/`models_missing`) and `horizon models fetch`.
- Sections and chunks + FTS; the Embedder (Qwen3 Embedding 8B, LRU, query instruction), vec writes, `keyword_only` + re-embed, space build with dual-write and flip.
- **"Index seed knowledge"** explicit action.
- `MemoryStore.apply(MemoryOp…)`; memory read; **Forget** (supersede chain, `turn_traces` + `insight` events scrub, purge outbox).
- `QueryBundle` vectors filled in; the `MemoryRetriever`/`KnowledgeRetriever` scripted and naive implementations; `entity.changed` knowledge progress and memory events.
- HttpClient: knowledge (full), memory.
- **UI wiring for knowledge add/delete/reindex** in the Knowledge tab: the drop zone (file + pasted text), per-source delete and ↻ Retry (= reindex), and live `progress` from `entity.changed`. The MockClient has implemented these since M1a (OQ-3).

**Acceptance**
- PDF, DOCX, MD and pasted text reach `indexed`, and O28 shows chunks with the right locators.
- A scanned PDF yields text through Docling OCR.
- Deleting a source leaves no rows, vectors or files.
- **After Forget, the text appears nowhere in `horizon.db` or `graph.db`.**
- The isolation suite covers FTS and vector retrieval.

## M6: `http-client-parity`
**Scope**
- Close any HttpClient gaps; run the portable `clientContract` tests against both clients; run the Playwright E2E suite against the backend in `scripted` mode (via `/_test/*`).
- `VITE_HORIZON_CLIENT` defaults (`http` for dev, `mock` for Vercel).
- README run instructions, an `ASSETS.md` check, and the gitleaks recommendation.

**Acceptance**
- E2E passes on both clients.
- `npm run setup` (step 1) + `npm run dev` reaches demo mode on a fresh clone (Windows + one Unix) within NFR-10's 5 minutes; Docling (step 2) is reported separately.

## Test strategy

| Layer | Tooling | Notes |
|---|---|---|
| Domain unit | pytest | energy, budget/reservations, pricing clock, reducer, ids. **Shared JSON fixtures with TS** |
| Contract | jsonschema against `schema.json` | Every route and every SSE event type |
| Integration | httpx `ASGITransport`, a temporary `data/` per test | Real SQLite + sqlite-vec, frozen `Clock` (incl. `sleep`), `scripted` AI |
| Provider | respx recorded responses | No live calls in CI; manual `pytest -m live` (≤ $0.05) |
| Isolation | Dedicated suite | NFR-23 + "forgotten text nowhere" |
| E2E | Playwright | Both clients from M6 |
