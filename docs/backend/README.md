# Horizon: Backend Design Pack (SWE stage)

> **Status:** v1.0, reviewed. A two-round debate between a backend and an AI representative found 4 + 2 blockers and 23 major issues; all are resolved below. · **Date:** 2026-10-03
> **Authors:** Backend engineering team, with the AI engineering team on storage for memory, knowledge and embeddings
> **Stakeholder:** Tan Wei Hang (product owner)
> **Inputs:** the requirements pack in [`docs/requirements/`](../requirements/README.md), especially [05 Data Contract](../requirements/05-data-contract.md), [07 NFRs](../requirements/07-nfr-risk-cost.md) and [08 Open Questions](../requirements/08-open-questions-handoff.md); the `HorizonClient` interface in [`frontend/src/client/HorizonClient.ts`](../../frontend/src/client/HorizonClient.ts); and D-61 ([image model test](../ai/image-model-test/README.md)).

This pack is the blueprint for **stage 3 (Backend)**. It says **what is stored where, which endpoints exist, and how the runtime behaves**, so that each milestone can go straight into an OpenSpec change (`propose → apply → archive`).

**Out of scope.** How the AI *thinks* is out of scope: prompt assembly, retrieval strategy, memory policy, routing and the debate host. That is the AI stage. The backend only provides the **interfaces (ports)**, the **storage** they need, and **placeholder** implementations (doc [05](05-ai-seams.md)).

## Documents

| # | Document | Answers |
|---|---|---|
| 01 | [Architecture](01-architecture.md) | Process model, layers, module layout, runtime components (session actors, job workers, gateway, event bus), run and dev setup |
| 02 | [Storage](02-storage.md) | What goes in SQLite, the filesystem or JSON columns; every table; the knowledge and embedding storage; lifecycles (delete, reset, forget); migrations; seed import |
| 03 | [API](03-api.md) | Conventions, the full endpoint catalogue mapped to `HorizonClient`, SSE streams, errors, idempotency, pagination, **contract rev 1.3** |
| 04 | [Gateway, budget & energy](04-gateway-budget-energy.md) | The single OpenRouter gateway (chat, decisions/Jev, images, embeddings, music), the ledger, caps, energy, peak pricing |
| 05 | [AI seams](05-ai-seams.md) | The port interfaces the AI team implements, the `Decider` (Jev) wrapper, scripted placeholders and the "naive real" versions |
| 06 | [Milestones](06-milestones.md) | M1–M6 scope, acceptance criteria and test strategy; one OpenSpec change each |

## Decisions locked with the stakeholder (2026-10-03)

These are recorded as D-62 to D-75 in the [decision log](../requirements/09-decision-log.md). The review debate added D-76 to D-79.

| Topic | Decision |
|---|---|
| Storage split | **SQLite** (`data/horizon.db`, WAL) is the source of truth. The **filesystem** holds binaries only. **JSON columns** hold value objects that are read and written whole. **LangGraph checkpoints** go in a separate `data/graph.db` |
| Vectors | **sqlite-vec**, exact (flat) KNN, partitioned by character; one `vec0` table per *embedding space*; **FTS5 BM25** in the same database |
| Embedding model | **Qwen3 Embedding 8B** via OpenRouter is the default; the final model and dimension count are chosen at the AI stage (re-index is cheap) |
| Document ingestion | **Docling, run locally on the CPU** (exception to D-38 for ingestion only). Accepts PDF, DOCX, MD/TXT and pasted text. **No URLs, no CSV.** Limits are 10 MB / 300 pages per file and 20 sources per character. The original file is kept |
| Knowledge layout | Source → **sections (parents)** → **chunks (children)**. Children are indexed (BM25 and vector) and cited; parents are what the LLM reads |
| Decisions | **Jev first:** every bounded decision defaults to a Jev question (`Decider` wrapper with a fallback). **Jev reranks**; no reranker models |
| Key | Entered in Settings and saved to gitignored `data/secrets.local.json`. `OPENROUTER_API_KEY` in `.env` takes precedence. The key is never returned, logged or exported |
| API | `/api/v1` REST + **SSE** (per session, per job, global). Commands return **202** with an `Idempotency-Key`, and are serialised by a **per-session actor**. One uvicorn worker |
| Jobs | SQLite job table + in-process asyncio workers that resume after a restart. **Creation stays plain jobs** (no LangGraph `interrupt`) |
| Memory | Characters remember **all modes, from their own perspective** (tagged with the source mode). The user can **view and forget**; Forget also **scrubs past Insight traces** |
| Lifecycle | Deleting a character leaves a **tombstone** (old transcripts still render). **Reset re-seeds seed data only**; a separate Factory reset wipes everything |
| AI depth at the end of the backend stage | **Scripted placeholders** for tests and demo, plus switchable **naive real** versions: one-call DeepSeek chat, Seedream images, Lyria song, profile draft |
| Vercel | The public demo **stays on the MockClient**; the backend is local-only |
| Delivery | This pack → **OpenSpec per milestone:**<ol><li>M1a contract rev 1.3 (frontend);</li><li>M1b backend foundation;</li><li>M2 gateway, ledger and energy;</li><li>M3 session runtime;</li><li>M4 generation jobs;</li><li>M5 knowledge and memory storage;</li><li>M6 HttpClient parity.</li></ol>Dev runs with `npm run dev` at the repo root |

## What the review debate changed (2026-10-03)

The backend representative (senior principal SWE) and the AI representative (senior principal AI engineer) reviewed this pack independently, then rebutted each other. The main outcomes:

| Area | Change |
|---|---|
| **Index safety** | Tables indexed by FTS5 or vec0 get `rid INTEGER PRIMARY KEY`. The hidden rowid isn't stable across VACUUM, which would have mis-mapped vectors across worlds |
| **Forget means gone** | The scrub also covers the `insight` events in `session_events`, the supersede chain and `graph.db` (via the `AiStateHooks` outbox). A test greps both databases for the forgotten text |
| **Event-sourced sessions** | `session_events` is the truth; messages are derived by a Python port of `sessionReducer.ts`. Fork = cut events + re-reduce; crash recovery = re-reduce (D-79) |
| **Seed importable** | Unique candidate IDs, candidate batches by `job_id`, synthetic knowledge sections, seed SVGs allowed |
| **Milestones** | M1 split into a frontend contract step and the backend foundation; every milestone ships its own HttpClient methods; EventBus and world CRUD moved to M1b |
| **Money correctness** | Budget **reservations** (concurrent calls can't overshoot silently); a ledger row for cancelled streams with an estimate→actual correction; restart never pays a provider twice (`provider_called_at`) |
| **Energy** | One threshold (`EST_REPLY_POINTS`, shared with the UI) for both state and gate; REAL storage; the top-up gate (D-76); discarded prefetches still drain (D-77) |
| **SQLite concurrency** | One writer engine (`BEGIN IMMEDIATE`, lock never held across network awaits) plus a reader engine |
| **AI seams** | `TurnEvent` = Emotion / Token / CitationMap / TracePatch; `MemoryOp` writes; `QueryBundle` reused per turn; per-purpose Jev timeouts with deterministic hot-path fallbacks; a ledger `purpose` column and `TurnTrace.calls[]` |
| **Browser limits** | At most 2 EventSources; job events ride the global stream |

## Fixes this pack makes to earlier material

1. **Seed:**
   - `seed/settings.json` image model → `bytedance-seed/seedream-5-0-flash`;
   - `seed/pricing.json` image prices → $0.018 per image (D-61);
   - **Jev price → $0.042 per million input tokens, output $0** (the file had 0.02 / 0.002 / 0.02).
2. **Seed:** Amara's "ED triage guidelines" changes from `type: "url"` to `"file"`. Mei's CSV source is removed (no CSV ingestion).
3. **Contract rev 1.3 (additive)** adds knowledge commands, world cover upload, three error codes, ID prefixes, the embedding model and its ledger category ([03 §7](03-api.md#7-contract-rev-13-additive)).
4. **OQ-AI-14 is overridden** (LangGraph `interrupt` for creation). The wizard plus separate job kinds already gives human-in-the-loop control; LangGraph lives only inside turn engines.
5. **NFR-10 / NFR-13 are amended for Docling.** CPU PyTorch becomes a dependency, and Docling's layout models are downloaded once from Hugging Face (D-62). OpenRouter remains the only *runtime* outbound host.
