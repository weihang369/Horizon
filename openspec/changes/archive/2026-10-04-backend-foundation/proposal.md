# Proposal: backend-foundation (M1b)

## Why

Horizon runs entirely on the in-browser MockClient. The backend design pack (`docs/backend/`, D-62..D-79) is reviewed, and M1a has put contract rev 1.3, the shared fixtures and `schema.json` in place. Nothing in the later milestones (gateway, sessions, jobs, knowledge) can start until there is a real FastAPI + SQLite process. It needs a schema, seed data, the event bus and an HttpClient the app can switch to. This change builds that foundation with read paths and world CRUD only, so `npm run dev` can browse and replay the demo from the backend.

## What Changes

- **Spikes first** (committed notes + minimal tests), covering the three risks the pack flags:
  - sqlite-vec loaded under aiosqlite on Windows;
  - FTS/vec `AFTER DELETE` triggers firing on FK-cascade deletes;
  - `uv` locking CPU torch + torchvision from the `pytorch-cpu` index in the `docling` group.
- **New `backend/` Python project** (uv, Python 3.12):
  - the app factory and config precedence;
  - JSON logging with key redaction;
  - the `horizon` CLI;
  - the writer engine (`BEGIN IMMEDIATE`, one connection, process lock) and the reader engine;
  - a freezable `Clock` that also derives the pricing period;
  - `ids.py`.
- **Storage:**
  - Alembic `0001_initial` creates every ordinary table and FTS table in doc 02.
  - A `SpaceManager` creates the default embedding space's vec tables and their triggers at startup.
- **`reducer.py`**: a Python port of `sessionReducer.applyEvent`, passing the shared reducer fixtures and `reduce(seed events) == seed messages`.
- **`domain/energy.py`** (read side): a port of the pure energy functions, passing the shared energy fixtures, so character reads derive `state`/`fullAt` exactly like the UI.
- **Seed lifecycle:**
  - import (validate, normalise timestamps, reduce-and-assert, synthesise sections, FTS);
  - reset-demo (upsert; user data survives; `mock.reset`);
  - Windows-safe factory reset.
- **EventBus and SSE:**
  - global stream `GET /events`;
  - session stream in replay mode, with the documented `sinceSeq` / `Last-Event-ID` resume rule.
- **REST surface:**
  - world CRUD (with cascade and folder removal, duplicate name → 409);
  - every read endpoint for settings, worlds, characters, sessions (paginated messages/events, trace), usage, memory, knowledge and job snapshots;
  - `/assets/*`;
  - `/health`;
  - the error envelope (incl. 422 → `validation`);
  - the persistent `Idempotency-Key` middleware;
  - `/_test/*` behind `HORIZON_TEST=1`;
  - `POST /admin/reset-demo` and `POST /admin/factory-reset`.
- **Contract (additive, `schemaVersion` stays 1):** `HorizonClient.admin.resetDemo()` on both clients. The Settings and World Select "Reset demo data" buttons move onto it.
- **MockClient parity:** world names are unique (case-insensitive), so a duplicate create/rename rejects with `conflict`, the same as the backend.
- **Frontend `HttpClient`** (`frontend/src/client/http/`):
  - reads, world CRUD, replay subscribe and `onGlobal`;
  - `HorizonError` parsing, `Idempotency-Key` on POSTs and cursor following.
  - It is selected by `VITE_HORIZON_CLIENT=http`, and the mock stays the default.
- **Portable contract suite:**
  - each test declares the milestone it needs;
  - a new HTTP harness runs it against a test-mode backend;
  - tests beyond M1b are listed as pending by name.
- **Root `package.json`** (`setup`, `dev`, `demo`, `test`) and the Vite proxy for `/api` and `/assets/gen`.

## Capabilities

### New Capabilities
- `local-backend`: covers the local Python service as a whole:
  - loopback-only binding;
  - config and key precedence (the key ignored until M2);
  - the startup lifespan and `/health`;
  - log redaction;
  - the CLI;
  - Windows-safe factory reset;
  - the one-command dev workflow (`setup`, `dev`, `demo`, proxy).
- `data-storage`: the SQLite schema and its invariants:
  - migrations;
  - `rid`-keyed FTS/vec tables kept in sync by triggers;
  - embedding-space tables owned by the SpaceManager;
  - millisecond UTC timestamps;
  - world-scoped access (NFR-23 isolation).
- `http-api`: REST conventions for every route:
  - the error envelope and status mapping;
  - camelCase wire shapes that validate against `schema.json`;
  - pagination;
  - idempotent POSTs;
  - asset serving;
  - test-only control routes.
- `event-streams`: the global SSE stream and the per-session stream:
  - keepalive, backpressure, no-buffer headers;
  - replay and the `sinceSeq` / `Last-Event-ID` resume rule.
- `session-event-sourcing`: session events are the source of truth. Messages and session state are derived by one reducer whose TypeScript and Python versions agree on shared fixtures and on the whole seed.
- `http-client`: the frontend `HttpClient`:
  - selection by env;
  - error parsing;
  - cursor following;
  - SSE subscription;
  - idempotency keys;
  - the explicit behaviour of methods whose backend milestone hasn't shipped.

### Modified Capabilities
- `client-contract`:
  - adds `admin.resetDemo()`;
  - the portable suite gains per-test milestone gating and must run against the backend through an HTTP harness.
- `demo-data`:
  - reset is reached through `admin.resetDemo()` on both clients;
  - the backend imports the seed with validation and a reduce-and-assert check;
  - shipped seed world names are reserved.
- `worlds`: world create/rename/delete behaviour is specified for both clients:
  - unique names → `conflict`;
  - delete cascades to everything in the world and its files.
- `energy`: the shared energy fixtures must also pass in Python. Character reads derive state at read time and are frozen in demo mode.
- `knowledge-sources`: on the backend, seed sources that have no vectors read as `keyword_only` (doc 02 §5).

## Impact

- **New code:** `backend/` (pyproject, `uv.lock`, `alembic.ini`, `horizon/**`, `tests/**`, spike notes); root `package.json` + lockfile.
- **Frontend:**
  - `src/client/http/**` (new);
  - `src/client/HorizonClient.ts` (`AdminApi`);
  - `src/client/index.ts` (client selection);
  - `src/mock/MockClient.ts` (`admin`, unique world names);
  - `src/stores/mock.ts`, `SettingsScreen.tsx`, `WorldSelectScreen.tsx` (reset via `client.admin`);
  - `clientContract.portable.ts` / `.mock.test.ts` / new `.http.test.ts`;
  - `vite.config.ts` (proxy), plus a separate vitest config for the HTTP run.
- **Docs:**
  - doc 05 (rev 1.3 addendum: `admin`);
  - doc 06 (branch rule);
  - doc 03 §3 (`GET /jobs` reads in M1b, test reset route if adopted).
- **Dependencies:**
  - Python: fastapi, uvicorn, sse-starlette, pydantic v2, SQLAlchemy 2 async, aiosqlite, alembic, sqlite-vec, python-ulid, jsonschema, httpx, pytest, pytest-asyncio, ruff, mypy, plus the `docling` group (lock only).
  - Node (root): concurrently.
- **Unchanged:**
  - the Vercel build (mock only, D-73);
  - every other UI behaviour;
  - `schemaVersion: 1`;
  - no network calls and no OpenRouter key anywhere in M1b.
