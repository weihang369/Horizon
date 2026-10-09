# 01: Architecture

> **v1.0.** This revision applies the review debate (Rounds 1–2, 2026-10-03).

## 1. Shape of the system

```
Browser (React, HorizonClient = HttpClient; ≤ 2 EventSources: global + the open session)
   │  REST /api/v1/*      SSE /api/v1/events, /api/v1/sessions/{id}/stream      GET /assets/*
   ▼
FastAPI app (ONE uvicorn worker, 127.0.0.1:8000)
   ├─ api/          routers: thin; validate → call a service → map to contract models
   ├─ contract/     Pydantic wire models (camelCase), schema.json (exported from zod), validators
   ├─ services/     domain logic: worlds, characters, sessions, jobs, usage, knowledge, memory, seed, lifecycle
   │    ├─ runtime/ SessionActor per open session, LiveSessionManager, reducer.py (port of sessionReducer.ts)
   │    └─ jobs/    JobScheduler + workers (asyncio), resumable; DoclingRunner (one spawned process per job)
   ├─ domain/       pure functions: energy, budget, pricing, clock, ids (ULID), text
   ├─ db/           SQLAlchemy 2.0: writer engine + reader engine, repositories, unit of work, Alembic
   ├─ storage/      AssetStore, KnowledgeStore, atomic writes, orphan sweeper
   ├─ gateway/      the ONLY network code: OpenRouter chat, decisions (Jev), images, embeddings, music, meta
   ├─ events/       EventBus: append → reduce → publish (session / global channels)
   └─ ai/           ports.py (Protocols), decider.py, placeholders/, naive/   ← the AI team adds graphs/ later
data/   horizon.db · graph.db · secrets.local.json · settings.local.json · assets/ · originals/ · knowledge/ · models/ · logs/
seed/   read-only fixtures + seed assets (imported on first run; seed assets served as-is)
```

**Dependency rule.**
- `api → services → (domain, db, storage, gateway, events, ai.ports)`.
- `ai.*` implementations may use `gateway`, **read-only** repositories, `storage` and the `MemoryStore.apply` API; they get them only through the context objects (doc 05 §4).
- Nothing imports `api/`.
- A lint rule bans `httpx` outside `gateway/`.

## 2. One process, one worker

- SQLite allows one writer, and actors, SSE queues and job workers are in-memory. More workers would need Redis, which breaks NFR-10. The load is one human; LLM streaming is network-bound.
- **CPU-heavy work stays off the event loop:**
  - Docling runs in **one subprocess per conversion** (`python -m horizon.ai.docling_worker`, started with `subprocess.Popen` and waited on in a thread, so it works under any event loop on Windows). It has a timeout (10 min, `convertTimeoutMs`), runs offline at below-normal priority, counts PDF pages before converting, exits when its parent is gone, and is killed on source delete, shutdown or factory reset. A `ProcessPoolExecutor` can't kill a hung conversion, so we don't use one (M5 design D4).
  - Pillow encodes run in `asyncio.to_thread`.

## 3. Database access (SQLite + async)

- **Two engines:**
  - **The writer engine:** `pool_size=1`, guarded by a process-wide `asyncio.Lock`. It opens every transaction with **`BEGIN IMMEDIATE`** (SQLAlchemy `begin` event with `isolation_level=None`). This avoids the `SQLITE_BUSY_SNAPSHOT` read-to-write upgrade failure, which `busy_timeout` can't retry.
  - **The reader engine:** a small pool for queries, retrieval (FTS + KNN) and SSE replay.
- **Pragmas** on connect: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. sqlite-vec is loaded in the `connect` event via `AdaptedConnection.run_async` (an M1b spike proves this on Windows, macOS and Linux CI).
- **The writer lock is never held across a network `await`.**
  - Provider calls, embeddings and Jev happen *before* taking the lock.
  - SSE replay pages through events in short read transactions, never held across a send, so WAL checkpoints aren't starved.
- **JSON-column read-modify-write** (e.g. a profile `PATCH` racing a job worker) happens inside one writer transaction, so there are no lost updates.

## 4. Runtime components

### 4.1 EventBus
- **Channels.** There are two channel kinds: `session:{id}` and `global`. **Job events are mirrored onto `global`** (`job.progress`, `task.update` including `previewUrl`, `job.done`), so a browser needs **at most two EventSources** (HTTP/1.1 allows 6 connections per origin). `jobs.subscribe` = a `GET /jobs/{id}` snapshot + a global stream filtered by `jobId`.
- **Session events are appended, reduced and then published:** the event insert and the reducer updates commit in one writer transaction, and only then is the event published.
- **Global events** are not persisted. Extra global payloads (additive):
  - `entity.changed{kind:"knowledge", id, progress?:{stage, pct}}` while ingesting;
  - `entity.changed{kind:"memory", id: characterId}` after post-turn memory ops.
- **Backpressure.** Subscribers are bounded queues (1,000). A slow subscriber is dropped (its stream closes), and the browser reconnects with `Last-Event-ID`.

### 4.2 SessionActor (one per open session)
- **Inbox.**
  - An asyncio task with an **inbox**. **Every write to a session's rows goes through it:** commands, `rename`, `mute`, `leave`, `end`, `delete` (stops the actor first) and listener reactions.
  - The `LiveSessionManager` does get-or-create under a lock.
- **Sequences.** It owns the event `seq` and message `seq` counters (initialised from `MAX`).
- **Preconditions.** It ports the MockClient's `liveSession()` preconditions:
  - sending to a paused 1:1 or group session auto-resumes it;
  - if a cap is still reached, the command is refused (402);
  - an ended session gives 409;
  - **energy exhaustion is an async event** (skip / `system_note`), never a pre-202 rejection.
- **The turn loop.**
  1. Choose the next speaker (port `Router`, Decider timeout 400 ms → deterministic fallback).
  2. **Allocate the `messageId`.**
  3. Check the energy gate (doc 04 §4).
  4. Reserve the budget.
  5. **Retrieve** (M5, `sessions/retrieve.py`; D-92). The runtime, not the engine, builds a scoped index for the speaker's world and character and asks the memory and knowledge retrievers for hits, which it freezes into the `TurnContext`.
     - The query text is the turn's prompt, else the latest message, else the debate motion or watch premise.
     - **Query embedding (D-97).** On `send` (1:1 and group only) the actor spawns **one** query embedding for the user message, in parallel with routing and the thinking delay. It runs only when the knowledge retriever uses vectors, a key is set and a possible responder has a source indexed in the active space. Debate, watch and greeting turns never embed.
     - A reply waits for that vector at most `retrieval.queryEmbedWaitMs` (400 ms, on the runtime clock); past that it retrieves by keyword alone. The late call is still billed and recorded. A cap refusal or provider error also means keyword-only, with no `error` event.
     - The `query_embed` call is listed on the **first** responder's `trace.calls`, like the route decision.
  6. Run `TurnEngine` and map its `TurnEvent`s (doc 05 §2) onto contract events.
  7. Merge `TracePatch`es and emit the **full** `insight`.
  8. Queue post-turn work: reactions (via the actor), memory ops (per-character queue) and the guardrail output check.
- **Prefetched openings (NFR-02).** For **openings only** (debate opening round, group `everyone-answer` openings), up to **N ≤ 2** `TurnEngine` runs may run ahead.
  - Their events are buffered **in memory**: not persisted, reduced or sequenced until **released at speaking pace**.
  - Prefetches count against the LLM semaphore and the budget reservations.
  - **Stop** cancels and discards the buffered output. Its spend stays in the ledger (`message_id` NULL), and **energy is still drained**: the spend was real (D-42; decision D-77).
- **Stop/pause** cancels the running turn task within 500 ms. The partial message is closed with `interrupted`.
- **Idle shutdown:** after 10 min idle with no subscribers, or on `leave`/`end`.

### 4.3 LiveSessionManager (NFR-31)
One session may **stream** at a time. A command that would start generation elsewhere returns **409 `conflict`** with `details.activeSessionId`. The UI confirms, calls `sessions.leave(A)` (pausing A with `navigated_away`) and retries.

### 4.4 JobScheduler + workers
- **Scheduling.** A scheduler loop picks `queued` tasks.
- **Semaphores:** image 2, music 1, llm 4 (prefetch included), embedding 2, docling 1.
- **One non-terminal job per character** (it equals `activeJobId`).
- **Restart recovery** follows doc 02 §3.5: no `provider_called_at` → requeue; called but no result → `failed` (retryable). **A provider is never paid twice without a user Retry.**

### 4.4b Ingestion worker (M5)
- One task per knowledge source (`services/knowledge/worker.py`), started through `rt.spawn`; the source row is the
  durable record. Conversion holds `docling_slots` (1), embedding `embed_slots` (2).
- Delete, character and world deletes, reset demo and factory reset stop the affected tasks first (a conversion
  process is killed; an embedding call already sent finishes and is recorded, D-86).
- Restart recovery and the in-flight batch rule: doc 02 §3.8.

### 4.5 Gateway
Doc [04](04-gateway-budget-energy.md). Every paid call does preflight (caps, **reservations**) → request → ledger (actual or estimate with correction) → energy drain (only `purpose == 'reply'`) → events.

### 4.6 AI purge outbox
- `ai_purge_queue` rows are written by lifecycle services **after** their commit (graph.db can't share a transaction with horizon.db).
- A worker calls `AiStateHooks` (doc 05 §4) at least once, and retries on startup.

### 4.7 Clock
- `domain/clock.py`: `now()`, `today_start(tz)`, `pricing_period()`, `next_change_at()` and **`sleep()`**. Pacing (watch `paceMs`, debate `pauseMs`, reveal timing) uses `clock.sleep`, so tests can advance virtual time.
- **Virtual time in tests (D-82).** While the test clock is frozen, `sleep` registers a timer and **waits** until the clock is advanced past it; time never moves on its own. `advance(ms)` fires due timers in deadline order (registration order on ties) and, after each one, waits for the work it woke to **settle**: every runtime task holds an activity token while it runs and hands it over while it waits on a timer, its inbox or an LLM slot (`domain/vclock.py`). `POST /_test/clock { advanceMs }` returns only once that work is stored, so the portable suite's `tick(ms)` drives live sessions over HTTP deterministically. Background work in `sessions/` and `ai/` starts only through `rt.spawn`; a settle that takes longer than 10 s of real time fails naming the busy tasks. `release: true` returns the same clock object to real time and wakes every sleeper. A test-mode `period_override` (the `rush_hour` scenario) pins the pricing period.
- `HORIZON_TZ` defaults to `Asia/Kuala_Lumpur`.

## 5. Configuration

- **Settings precedence:** env > `.env` > `data/settings.local.json` (UI-editable) > `seed/settings.json`.
- **Key precedence:** `OPENROUTER_API_KEY` (env/.env) > `data/secrets.local.json`. The key is held as a `SecretStr`, and a log filter redacts `sk-or-…`.
- **Model IDs and routing** are pinned in `seed/settings.json` and `seed/pricing.json` (NFR-14), along with the pricing table and the **per-purpose Decider timeouts**. Both files are generated by `frontend/scripts/seed-build` and checked by `seed:check`.
- **Test mode.** `HORIZON_TEST=1` enables `/api/v1/_test/{clock,scenario,ai-profile,decider-fixtures}`. It is never on in normal runs.

## 6. Tech stack (`backend/pyproject.toml`, managed by **uv**)

| Concern | Choice | Notes |
|---|---|---|
| Runtime | Python **3.12** (uv-managed) | python-build-standalone supports `enable_load_extension` |
| Web | FastAPI, uvicorn, sse-starlette | OpenAPI at `/api/docs` |
| Models | Pydantic v2 | Wire models (camelCase) separate from ORM models; no SQLModel |
| DB | SQLAlchemy 2.0 async + aiosqlite, Alembic | Writer and reader engines (§3); `include_object` skips virtual tables |
| Vectors | sqlite-vec (pin verified in M1b; 0.1.9 is current stable) | vec0 partition keys |
| HTTP out | httpx | Only in `gateway/` |
| Images | Pillow | |
| Documents | **Docling** (CPU) | In a **`docling` dependency group** synced by `setup` step 2. `torch` **and** `torchvision` are direct dependencies, sourced from the `pytorch-cpu` index (`explicit = true`, marker `sys_platform != 'darwin'`), verified in M1b. `/health` reports `docling: "not_installed" \| "models_missing" \| "ready"` |
| IDs | python-ulid | |
| Tests | pytest, pytest-asyncio, httpx `ASGITransport`, respx, jsonschema | |
| Lint | ruff, mypy (strict on `domain/`, `contract/`, `gateway/`) | |

## 7. Repository layout

```
backend/
  pyproject.toml  uv.lock  alembic.ini  .env.example
  horizon/
    main.py  config.py  cli.py            `horizon serve | migrate | seed | reset | models fetch | export-schema`
    api/        settings worlds characters jobs sessions commands usage knowledge memory events admin assets errors _test
    contract/   models.py  schema.json  validate.py
    domain/     energy.py budget.py pricing.py clock.py ids.py text.py
    db/         engines.py base.py models/ repositories/ uow.py migrations/ spaces.py (SpaceManager)
    services/   worlds characters assets lifecycle usage knowledge memory seed export  jobs/  runtime/
    storage/    assets.py knowledge.py atomic.py sweeper.py
    gateway/    client.py chat.py decisions.py images.py embeddings.py music.py meta.py reservations.py errors.py redact.py
    events/     bus.py sse.py
    ai/         ports.py decider.py hooks.py placeholders/ naive/
  tests/        unit/ contract/ integration/ isolation/ fixtures/ (shared with TS: energy, reducer)
package.json (root)   "setup" | "dev" | "demo"  (concurrently, kill-on-exit)
```

## 8. Run and dev

- **`npm run setup`:**
  1. `uv sync` (core) and `npm ci` (frontend). **Demo mode works after this step** (NFR-10, ≤ 5 min).
  2. `npm run setup:docling` (`uv sync --group docling`: CPU torch + Docling), then `uv run --project backend horizon models fetch` (the Docling models into `data/models/`, then `HF_HUB_OFFLINE=1`; the fetch writes `data/models/.horizon-models.json` last, and `/health` reports `ready` only once it exists). This step can be skipped: Markdown, text and pasted text never need it, and a PDF or DOCX added before it ends `failed` with these steps; Retry converts the kept original afterwards (D-96).
- **`npm run dev`:**
  - `concurrently --kill-others` runs `uv run horizon serve --reload --reload-dir backend/horizon` (port 8000) and Vite (port 5173).
  - Vite proxies `/api` and `/assets/gen` to port 8000, without buffering. It still serves `/assets/placeholder/**` from `seed/assets`.
- **`npm run demo`:** builds the frontend; `horizon serve` serves `frontend/dist` + the API on one port.
- **`npm run dev:mock`:** the frontend alone on the MockClient, with no backend (the UI loop).
- **Picking the client:** `VITE_HORIZON_CLIENT=mock|http`. It's `http` under `dev`, and **`mock` for the Vercel build** (D-73). A config-time guard (`frontend/scripts/build/clientGuard.ts`) fails any other value, an `http` build without `--mode http` (only `npm run demo` builds that way), and any `http` run with `VERCEL=1`.
- **Proxy target:** Vite proxies to `HORIZON_API_TARGET` (default `http://127.0.0.1:8000`); the E2E HTTP project points it at its own test backend.
- **Startup lifespan:**
  1. create `data/`;
  2. `alembic upgrade head`;
  3. the SpaceManager ensures the vec tables;
  4. seed if empty;
  5. re-reduce leftover `streaming` messages → `interrupted`;
  6. recover jobs;
  7. drain `ai_purge_queue`;
  8. start the sweeper.

## 9. Observability (OQ-AI-15 default A)

- **Logs:** structured JSON in `data/logs/horizon.log` (rotating 5 × 5 MB) and on the console, with `request_id`, `session_id`, `job_id` and `message_id`; the key is redacted.
- **The ledger** (with `purpose`) and **`TurnTrace`** (with `calls[]`) are the user-facing view of the same data.
- **`gateway.on_call` hook:** a no-op now; the AI stage attaches the `ai_calls` evaluation store to it.
- **LangSmith** is opt-in at the AI stage.
