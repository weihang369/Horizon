# Tasks

> Before starting: confirm or override design.md OQ-1…OQ-13. The tasks below implement the recommended defaults.

## 1. Spikes (stop and record in design.md if any fails)

- [x] 1.1 Create `backend/pyproject.toml` (uv, `requires-python = ">=3.12,<3.13"`, `.python-version` 3.12) with the core dependencies from doc 01 §6 plus `tzdata`. Verify that `uv sync --project backend` succeeds on Windows with a uv-managed 3.12, and that `uv run python -c "import sys; print(sys.version)"` prints 3.12.
- [x] 1.2 **Spike (a):** load sqlite-vec under aiosqlite via `AdaptedConnection.run_async` in the SQLAlchemy `connect` event, then run `select vec_version()` and a 3-row vec0 KNN query. Write the result to `backend/spikes/01-sqlite-vec-aiosqlite.md` (Windows: result; macOS/Linux: "CI later"). Verify with `backend/tests/spikes/test_vec_load.py` passing.
- [x] 1.3 **Spike (b):** build `parent` → `child` (FK `ON DELETE CASCADE`, `rid INTEGER PRIMARY KEY`) with an external-content FTS5 table and a vec0 table, both with `AFTER DELETE` triggers. Delete the parent, then assert that both indexes are empty and that a `VACUUM` keeps the hit mapping. Write the result to `backend/spikes/02-cascade-triggers.md`, and verify with `tests/spikes/test_cascade_triggers.py` passing.
- [x] 1.4 **Spike (c):** add the `docling` dependency group with `torch` and `torchvision` sourced from a `pytorch-cpu` index (`explicit = true`, marker `sys_platform != 'darwin'`). Verify that `uv lock` resolves with nothing installed or downloaded beyond the lock. Write the resolved versions to `backend/spikes/03-pytorch-cpu-index.md`.

## 2. Backend scaffold

- [x] 2.1 Create the `backend/horizon/` package layout from doc 01 §7, plus the `horizon` console script (`serve | migrate | seed | reset [--factory --yes] | export-schema --check`). Make `serve` refuse a non-loopback `--host`. Verify with `uv run horizon --help` and a CLI test showing that `--host 0.0.0.0` exits non-zero.
- [x] 2.2 Implement `config.py`:
  - precedence env > `.env` > `data/settings.local.json` > `seed/settings.json`;
  - `HORIZON_DATA_DIR`, `HORIZON_TZ`, `HORIZON_TEST`, seed dir;
  - the key is never read in M1b.

  Verify with unit tests for each precedence level, plus one showing that `OPENROUTER_API_KEY` in the env is never read.
- [x] 2.3 Implement JSON logging: console + `RotatingFileHandler` 5 × 5 MB in `data/logs/`, a `request_id` contextvar, and a `RedactFilter` for `sk-or-…`. Verify with a test that logs a fake `sk-or-v1-…` in the message, the args and an exception, and finds only the redaction marker in the file.
- [x] 2.4 Implement `domain/clock.py` (`SystemClock`, `FrozenClock` with `set`/`advance`/virtual `sleep`, `pricing_period`, `next_change_at` from the config peak windows) and `domain/ids.py`. Verify with unit tests for the Tue 10:00 peak, the Sat off-peak, a `nextChangeAt` at the 12:00/14:00/18:00 edges, and the ID regex.
- [x] 2.5 Implement the app factory and the lifespan skeleton (create `data/` → migrate → spaces → seed-if-empty → re-reduce `streaming` → [jobs no-op] → [purge no-op] → sweeper). Verify that `uv run horizon serve` starts and that `GET /api/v1/health` answers.

## 3. Shared-fixture domain ports

- [x] 3.1 Port `sessionReducer.ts` to `horizon/services/runtime/reducer.py` (`initial_runtime`, `apply_event`, `reduce_all`, `ordered_messages`, working on wire dicts). Verify with `tests/unit/test_reducer_fixtures.py` passing every case in `backend/tests/fixtures/reducer/` and the TS fixture test still green. Add a shared fixture for any divergence found during the port.
- [x] 3.2 Port `domain/energy.ts` to `horizon/domain/energy.py` (every function in the fixture file, plus `full_at`, with the `ceil(x − 1e-9)` epsilon). Verify with `tests/unit/test_energy_fixtures.py` passing every case in `cases.json` within its tolerance, and with a deliberately broken threshold making a case fail.
- [x] 3.3 Add a test asserting that `errors.ts` `DEFAULT_RETRYABLE` matches the backend's retryable table (by parsing `schema.json` `ErrorCode` + a small JSON export, or a checked-in table compared in both test suites). Verify that both suites fail when one side changes.

## 4. Storage

- [x] 4.1 Write the SQLAlchemy models for every ordinary table in doc 02 §3:
  - include `session_summaries`, `message_citations`, `trace_memory_refs`, `idempotency_keys`, `ai_purge_queue`, `usage_records.purpose`;
  - give `memory_items` / `knowledge_chunks` the `rid` + `id UNIQUE`;
  - give every FK an explicit `ON DELETE`.

  Verify that mypy passes on `db/`.
- [x] 4.2 Write Alembic `0001_initial` by hand: the tables, the FTS5 tables and their triggers via `op.execute`, and an `include_object` that skips the virtual and shadow tables. Verify that `horizon migrate` runs twice cleanly and that the autogenerate-diff test reports no changes.
- [x] 4.3 Implement `db/engines.py`:
  - writer engine (`pool_size=1`, `BEGIN IMMEDIATE`, a process lock) and reader engine;
  - pragmas;
  - sqlite-vec loading from spike (a).

  Implement `db/uow.py` (`write()` publishes collected events only after commit; `read()`). Verify with tests that two concurrent writes serialise without `SQLITE_BUSY`, that a rolled-back write publishes nothing, and that a read during a write sees the pre-commit state.
- [x] 4.4 Implement `db/spaces.py` (the SpaceManager): the default space `qwen3-emb-8b@1024` and idempotent `memory_vec__*` / `knowledge_vec__*` tables with `AFTER DELETE` triggers. Verify that the first start creates exactly one active space with empty vec tables, and that a restart changes nothing.
- [x] 4.5 Add a storage test for cascades: deleting a world with seeded memory and knowledge leaves zero FTS and vec rows for its characters (the data-storage spec scenario). Add the millisecond-timestamp normalisation helper with a unit test.

## 5. API foundation

- [x] 5.1 Implement `api/errors.py`:
  - `HorizonHTTPError` and its handlers;
  - 422 → `validation` with `details.fields`;
  - unknown route → 404 `not_found`;
  - 405 → `validation`;
  - 500 → a generic message, with the error logged.

  Verify with tests for each mapping, checking that the body validates against `HorizonErrorShape`.
- [x] 5.2 Implement `contract/validate.py` (jsonschema against `schema.json` `$defs`), the test-mode response-validation hook for JSON and SSE, and OpenAPI response schemas injected from `$defs`. Make `horizon export-schema --check` verify that `schema.json` loads and contains every `$def` the routes declare. Verify that a deliberately malformed response fails in test mode, and that `/api/openapi.json` contains the `World` schema.
- [x] 5.3 Implement the pagination helper (`limit` default 200, max 1,000 → `validation`; opaque cursors for event/message seq and usage `(at,id)`). Verify with unit tests for the first, middle and last pages, plus a bad cursor → `validation`.
- [x] 5.4 Implement the idempotency middleware over `idempotency_keys`:
  - same body → replay;
  - different body → 409;
  - in flight → wait;
  - 24 h expiry;
  - stale `in_flight` rows cleared at startup.

  Verify with integration tests for each case, including one that restarts the app between two identical POSTs.
- [x] 5.5 Implement `GET /assets/{path}`: `data/assets` first, then `seed/assets`; MIME types; traversal (including encoded) → 404; immutable cache on `gen/`. Verify with tests for a seed SVG, a `gen/` file's headers, and three traversal variants.
- [x] 5.6 Implement `/_test/clock` and `/_test/scenario` (empty registry → `validation` with `details.availableIn`), mounted only under `HORIZON_TEST=1`. Verify that both give 404 without the flag, and that freeze + advance changes the `createdAt` of a world created next.

## 6. Seed lifecycle

- [x] 6.1 Implement `services/seed.py` (the D5 mapping):
  - validate everything first;
  - normalise timestamps;
  - characters → `characters` + `image_assets` (emotion/blink/candidate seed batch);
  - sessions → events + reduce-and-assert + messages, `turn_traces`, `message_citations`;
  - knowledge → sources (`indexed` → `keyword_only`), synthesised sections, chunks;
  - memory, songs, ledger (`local_day`);
  - all `is_seed = 1`, in one transaction.

  Verify that an invalid file and a tampered `messages.json` each abort with the file or session named and leave zero rows.
- [x] 6.2 Add test-mode loading of the default-scenario `seed/_mock/**` overlays (characters, sessions, songs, jobs, ledger; not `variants/`). Verify that a normal run has no `*_mock*` IDs, and that test mode lists archived `chr_mockMochi` with `includeArchived=true`.
- [x] 6.3 Write the seed round-trip test. For every seed world, character, session (snapshot, messages, events, traces), knowledge source + chunks, memory item, song and ledger row, compare the API's `GET` against the seed file, after normalisation and only the documented read-time derivations. Verify that it passes, and that removing one mapper field makes it fail.
- [x] 6.4 Implement reset-demo (D12: upsert seed worlds and characters, re-insert seed sessions, replace seed ledger/memory/knowledge, keep user memories, purge-queue row, publish `mock.reset` after commit). Add `POST /admin/reset-demo` (`{confirm:true}` → 204, otherwise `validation`) and `horizon reset`. Verify with tests showing that:
  - a renamed seed world and a deleted seed world come back;
  - a user world, a user memory on a seed character and a user ledger row survive;
  - `mock.reset` is received on the global stream.
- [x] 6.5 Implement factory reset (D12 Windows-safe sequence with a lifecycle gate) as `POST /admin/factory-reset` (`{confirm:"DELETE EVERYTHING"}`) and `horizon reset --factory --yes`. Verify on Windows with an integration test: with the log file and DB open, a confirmed reset removes a user world, keeps `data/models/`, and serves the seed worlds again without a restart. Also verify that a wrong confirmation changes nothing.
- [x] 6.6 Implement startup re-reduction of leftover `streaming` messages into `interrupted`. Verify with a test that inserts a streaming turn's events, restarts the app, and finds `turn.end` with `status:"interrupted"`.

## 7. Events

- [x] 7.1 Implement `events/bus.py`: channels, bounded queues of 1,000, drop on overflow. Verify with unit tests that a stalled subscriber is closed while a second subscriber receives every event.
- [x] 7.2 Implement `GET /events` (the global SSE: 15 s ping, no-cache and `X-Accel-Buffering` headers). Verify with an ASGI test that receives `entity.changed` after a world create and a keepalive with the frozen clock advanced.
- [x] 7.3 Implement `GET /sessions/{id}/stream`:
  - register the queue first;
  - `start = max(sinceSeq, Last-Event-ID)`;
  - paged replay in short read transactions;
  - drain while skipping `seq ≤ lastSent`;
  - 404 before streaming for an unknown session.

  Verify with tests for `sinceSeq=3`, `Last-Event-ID` winning, a synthetic live event published mid-replay arriving exactly once, and `ses_nope` → 404 envelope.

## 8. Routes, isolation and contract tests

- [x] 8.1 Implement the world CRUD routes (`GET/POST /worlds`, `GET/PATCH/DELETE /worlds/{id}`):
  - name trim, 40-character cut and the `New World` fallback;
  - unique case-insensitive names → 409 `details.field:"name"`;
  - reserved shipped seed names;
  - the delete cascade with folder removal and ledger refs nulled;
  - `entity.changed` after commit.

  Verify with integration tests for every worlds-spec and demo-data reserved-name scenario.
- [x] 8.2 Implement the read routes: settings (computed `spentTodayUsd`, `pricing`, `estReplyPoints`; `missing` + `demoMode: true`), characters (list/get/assets/song/memory/knowledge/knowledgeSource, with tombstone rules and energy derived via `energy.py`), sessions (list/get/messages/events/trace), usage (list/summary, matching MockClient semantics incl. `byCategory.embedding`) and jobs (get, `?active=true`). Verify with an integration test per route, plus a peak/off-peak character `state` test with the frozen clock.
- [x] 8.3 Write `tests/contract/`. With `HORIZON_TEST=1` response validation on, call every M1b route and both streams, and assert zero validation failures. Also assert that no response contains a `null` the schema doesn't allow. Verify that it passes.
- [x] 8.4 Write `tests/isolation/` (two near-identical worlds built through the services):
  - lists, gets, knowledge, memory and a scoped FTS query for A never return B's records;
  - cross-world IDs in world-scoped paths → 404.

  Verify that it passes.
- [x] 8.5 Add the backend lint gates: ruff, and mypy strict on `domain/` and `contract/` (plus `services/runtime/reducer.py`). Verify that `uv run ruff check`, `uv run mypy` and `uv run pytest` are all green.

## 9. Frontend contract and mock parity

- [x] 9.1 Add `AdminApi { resetDemo(): Promise<void> }` as `HorizonClient.admin`. Implement it on the MockClient by delegating to the existing reset logic, and update `doc 05` with the rev 1.3 addendum. Verify that `tsc -b` passes and that a mock unit test sees `mock.reset` after `client.admin.resetDemo()`.
- [x] 9.2 Add the world-name rules to the MockClient (unique case-insensitive, and reserved shipped seed names → `conflict` `details.field:"name"`; trim/cut/fallback unchanged). Verify with unit tests, and that the existing unit and E2E suites still pass (fix test data, not the rule).
- [x] 9.3 Point the Settings and World Select "Reset demo data" buttons at `client.admin.resetDemo()`, and keep MockSwitcher's dev button. Verify that the existing reset E2E flows pass on the mock and that `stores/mock.ts` no longer exports `resetDemoData` for the screens.

## 10. HttpClient

- [x] 10.1 Implement `client/http/transport.ts`: base URL, JSON, envelope → `HorizonError` (code, message, retryable, retryAfterSec, details), fetch failure → `network`, a per-call `Idempotency-Key` reused on its single network retry. Verify with unit tests against a stubbed `fetch`.
- [x] 10.2 Implement `client/http/paging.ts` (follow `nextCursor`) and `client/http/sse.ts`:
  - a ref-counted shared global stream;
  - a single session stream with `seq` dedupe;
  - an injectable `EventSource`.

  Verify with unit tests using a fake EventSource (reconnect → no duplicate `seq`; three `onGlobal` callbacks → one stream).
- [x] 10.3 Implement `HttpClient`:
  - settings.get;
  - worlds (all, incl. delete; `uploadCover` → `notYet("M4")`);
  - the character/session/usage/memory/knowledge/job reads;
  - `sessions.events`/`subscribe`;
  - `onGlobal`;
  - `admin.resetDemo`;
  - every other method → `notYet(<milestone>)` per doc 06.

  Verify with a unit test that every `notYet` method rejects with `validation` + `details.availableIn` without calling `fetch`.
- [x] 10.4 Select the client in `client/index.ts` via `VITE_HORIZON_CLIENT` (`mockDev` null under HTTP), and add the committed `frontend/.env.http`. Verify that `npm run build` (no mode) still produces a mock-only app with `npm run budget` green, and that `vite build --mode http` builds.

## 11. Portable suite on both clients

- [x] 11.1 Add milestone gating to `clientContract.portable.ts` (`test(milestone, name, fn)`, harness `supports`, `[pending Mx]` skips, unknown milestone → throws). Tag every existing test per doc 06. Split "queries work without a key" into a read test (M1b) and a `missing_key` test (M3), and split the knowledge test's read half into M1b (accepting `indexed | keyword_only`). Verify that the mock run executes every test with none pending.
- [x] 11.2 Add the new portable M1b tests:
  - world create/rename/delete;
  - duplicate and reserved names → `conflict`;
  - reset restores renamed and deleted seed worlds and keeps a user world;
  - `subscribe(sinceSeq)` on a seed recording;
  - `messages == reduce(events)` for every seed session.

  Verify that they pass on the mock harness.
- [x] 11.3 Switch the mock harness's `reset` to `client.admin.resetDemo()`. Add `clientContract.http.test.ts` with `vitest.http.config.ts`: a globalSetup spawns `uv run --project ../backend horizon serve --port 8765` with `HORIZON_TEST=1` and a temp `HORIZON_DATA_DIR`. Per-test factory reset, a frozen clock at `START`, the `eventsource` package injected, and `setKey` → pending M2. Add `npm run test:http`. Verify that every M1b test passes over HTTP and that later tests are listed as `[pending Mx]`.

## 12. Workspace, dev loop and docs

- [x] 12.1 Add the root `package.json` (`setup`, `setup:docling`, `dev`, `demo`, `test`; devDependency `concurrently`). Add the Vite `server.proxy` for `/api` and `/assets/gen`, and `horizon serve --static` for `demo`. Update `.gitignore` (`.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, root `node_modules/`). Verify that `npm run setup` works on a fresh clone and that `npm run demo` serves the app and the API on one port.
- [x] 12.2 Manual Windows check: `npm run dev`, then Ctrl-C. Verify that no `python`/`uvicorn`/`node` process from the session remains. If one does, apply the design's no-`--reload` fallback and record it.
- [x] 12.3 Update the docs:
  - doc 06: the branch-per-milestone rule; job reads in M1b;
  - doc 03 §3: job reads, test-mode overlays, the `/_test/scenario` registry, `admin.resetDemo`;
  - doc 02 §5: `_mock` is imported in test mode only;
  - root README: a "Run locally" section with `setup` / `dev` / `demo` / `test`.

  Verify that every command in the README runs as written.

## 13. Integration checks

- [x] 13.1 Acceptance walk-through with `npm run dev` (`VITE_HORIZON_CLIENT=http`):
  - both seed worlds browse;
  - every seed character profile opens (Knowledge tab shows `keyword_only` badges, Mei's failed source keeps its error);
  - every seed session replays;
  - world create/rename/delete works and duplicates are refused.

  Record the result in the change folder.
- [x] 13.2 Run the full gate: `uv run pytest`, ruff, mypy, `npm test`, `npm run test:http`, `npm run typecheck`, `npm run lint`, `npm run seed:check`, `npm run export-schema:check` and the Playwright E2E suite on the mock. Verify that all are green.
- [x] 13.3 Run `openspec validate backend-foundation --strict`. Verify that it is valid.
