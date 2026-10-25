# Tasks

> **Constraints for every task:**
> - No network in automated tests (the socket guard stays). Only the in-process fake provider and obviously fake `sk-or-test-…` keys are used. The real key is never printed, logged or put in fixtures.
> - No contract change: `schemas.ts`, `types.ts` and `schema.json` stay as they are, and `npm run export-schema:check` passes. If a parity gap (G11) needs a contract or UI change, **stop and ask the user**.
> - No paid or live calls, no Docling install, no models fetch.
> - No subagents without asking the user first.
> - Commit at green group boundaries, without Claude attribution. Nothing is pushed: the user pushes.
>
> Each numbered group ends with its own tests and docs green. Gap IDs (G1–G11) and decisions (D1–D21) refer to design.md.

## 1. Backend test scenarios (D3, D4, D5, G2–G5)

- [x] 1.1 Make `/_test/scenario` replace instead of stack (D3): add one `clear_scenario_state(rt)` that resets `clock.period_override`, `stream_faults`, `job_faults` and the spend bias. Call it at the start of every scenario, and from `POST /admin/reset-demo` when `test_mode`. Verify with integration tests:
  - `rush_hour` then `stream_cut` reports the clock's own period and still cuts the next reply;
  - after `image_fail_all`, a test-mode reset-demo lets the next job succeed;
  - every existing `tests/integration` and `tests/sessions` scenario test still passes.
- [x] 1.2 Add `clock.spend_bias_usd` (test-only, next to `period_override`, cleared on `runtime.start`). Add it in **both** `services/settings.py:spent_today` and `services/ledger.py:spent_today`. Add the `daily_cap` scenario (bias = `max(0, cap − spent)`), which publishes `entity.changed {kind:"settings"}` (D5). Verify with integration tests:
  - `GET /settings.spentTodayUsd` equals the cap;
  - a 500-point top-up for Hana rejects `daily_budget_exceeded`;
  - a session send preflight is refused the same way;
  - `GET /usage` has no new row;
  - reset-demo in test mode restores the ledger's own total.
- [x] 1.3 Add the `no_worlds` scenario (D4), applied to every world:
  1. cancel ingestion;
  2. release live session actors and cancel non-terminal jobs (the hooks `reset_demo` uses);
  3. run `worlds_svc.delete_world` and remove world files;
  4. publish `mock.reset`.

  First check that deleting worlds leaves `usage_records` intact. If an FK blocks it, null the reference as world delete does. Verify with an integration test:
  - with a user world and a running job, `no_worlds` leaves `GET /worlds == []`, settings and key unchanged, `GET /usage` rows unchanged, and no job task running after a clock advance;
  - a following reset-demo lists exactly the two seed worlds.
- [x] 1.4 Remove `network_down` and `no_worlds` from `SCENARIO_MILESTONE`. Make `network_down` reject with 422 `validation`, `details: {field: "id", clientSide: true}` (D2). Verify with an integration test: the response, and that no state changed.
- [x] 1.5 Update the test-route section of `docs/backend/03-api.md` (the scenario list, replace semantics, `network_down` as client-side). Verify that `ruff check`, `mypy` and the full `pytest` run are green, then commit.

## 2. Portable suite with nothing pending (D2, D6, G1, G6, G7)

- [x] 2.1 In `clientContract.http.test.ts`, construct the `HttpClient` with a wrapped `fetch`:
  - while `network_down` is the active harness scenario, it throws `TypeError("fetch failed")` without calling the real `fetch`;
  - `setScenario` clears the flag before applying any other scenario;
  - the harness's own `/_test/*` and reset calls bypass the wrapper.

  Verify that the M6 portable test passes over HTTP.
- [x] 2.2 Switch the HTTP run to `supports: "M6"`. Move the world-names test from `clientContract.mock.test.ts` into `clientContract.portable.ts` as `test("M1b", …)` (G6), and give each remaining mock-only test a one-line reason (D1). Verify:
  - `npm run test:http` reports 56 passed and 0 pending;
  - `npm test` (mock harness) reports the same 56 portable tests passing;
  - the suite-integrity tests still pass.

  If the backend fails the world-names test, fix the backend to the demo-data spec, not the test.
- [x] 2.3 Isolate `scripts/http-contract/globalSetup.ts` from the developer's machine (D8, G7): set `HORIZON_ROOT=<temp>`, `HORIZON_SEED_DIR=<repo>/seed` and `HORIZON_DATA_DIR=<temp>/data`. Verify by making the env recipe a small exported function, with a vitest unit test asserting that `HORIZON_ROOT` is a fresh temp dir with no `.env` in it and that `HORIZON_SEED_DIR` is the repo seed. Also confirm `npm run test:http` stays green. The real repo-root `.env` is never edited.
- [x] 2.4 Update the `clientContract.http.test.ts` header comment ("implements milestone M6, nothing pending"), and the `http-client` and `client-contract` notes in `docs/backend/06` §M6. Verify the typecheck and both contract runs are green, then commit.

## 3. Client defaults, proxy target and build guard (D8, D14)

- [x] 3.1 Read the Vite proxy target for `/api` and `/assets/gen` from `HORIZON_API_TARGET`, defaulting to `http://127.0.0.1:8000`. Verify that `npm run dev` at the root still loads the seed worlds through `:8000` (a manual check, recorded in the commit message).
- [x] 3.2 Add the `clientGuard` Vite plugin (D14) as a pure function, `resolveClient({ value, mode, command, vercel })`, plus the plugin wrapper. The rules: unknown value → error naming `VITE_HORIZON_CLIENT` and its allowed values; `http` in a build requires mode `http`; `VERCEL=1` + `http` → error. Verify with unit tests for each rule, including `"HTTP"`, empty, `mock`, a dev server with `http`, `demo`'s build with `--mode http`, an env-only `http` build, and Vercel. Also confirm that `npm run build --prefix frontend` (the Vercel command) succeeds and `npm run demo`'s build step succeeds.
- [x] 3.3 Add the root `dev:mock` script (`npm run dev --prefix frontend`). Verify that with no backend running, `npm run dev:mock` serves the app on the MockClient and the browser makes no `/api/` request.
- [x] 3.4 Update `docs/backend/01-architecture.md` §8 (`dev:mock`, `HORIZON_API_TARGET`, the guard) and the `src/client/index.ts` header comment. Verify that the typecheck, lint and vitest are green, then commit.

## 4. Playwright on both clients (D7–D13, D21, G11)

- [x] 4.1 **Verify the console line first** (D12): with a throwaway spec, run a page that fetches a 402 and a 404 from the test backend, on Edge and on bundled Chromium (`PW_CHANNEL=""`). Record the exact `Failed to load resource` text in design.md's apply notes, then delete the throwaway spec.
- [x] 4.2 Write `frontend/e2e/servers/backend.mjs` (D8, D13):
  - temp `HORIZON_ROOT` and data dir, `HORIZON_SEED_DIR` at the repo seed, `HORIZON_TEST=1`, `HORIZON_AI_PROFILE=scripted`, `HORIZON_LOG_LEVEL=WARNING`, port 8786;
  - stderr forwarded;
  - `SIGINT`/`SIGTERM`/`exit` kill the tree (`taskkill /T /F` on Windows, the process group on Unix), then remove the temp dir with retries.

  Verify on Windows: start the launcher, Ctrl-C it, and confirm no `horizon`/uv/Python process from it remains (`Get-Process`) and the temp dir is gone.
- [x] 4.3 Restructure `playwright.config.ts` (D7):
  - projects `mock-desktop`, `mock-min` (`@layout`) and `http-desktop` (`workers: 1`);
  - a custom `client` option;
  - a `webServer` array: mock Vite on 5186, the backend launcher on 8786 waiting for `/api/v1/health`, and `vite --mode http --port 5187 --strictPort` with `HORIZON_API_TARGET=http://127.0.0.1:8786`;
  - `reuseExistingServer: false` for both HTTP servers.

  Add the scripts `e2e` (all), `e2e:mock` and `e2e:http`, and keep `e2e:prod` on the mock projects. Verify that `npm run e2e:mock` is green, and that `e2e:http` doesn't start the mock server (if Playwright starts every server, build the array from the selected projects, D7).
- [x] 4.4 Extend `e2e/fixtures.ts` (D9, D10, D12):
  - an auto fixture that factory-resets the backend before each HTTP test;
  - `setKey(page)` through Settings → Connection with `sk-or-test-e2e-0001`, then `goBack()`;
  - `setScenario(page, id)`: the switcher UI on the mock, `request.post` to `/_test/scenario` on HTTP;
  - `GEN_TIMEOUT` (8 s mock / 60 s HTTP);
  - `expectHttpError(page, status)` (declared 4xx lines only, never 5xx).

  Remove `setMockKey`. Verify with the mock project green and a fixture self-test spec, which shows that an undeclared 404 fails and a declared 402 passes.
- [x] 4.5 Move the specs to the fixtures:
  - energy: `setKey`, `setScenario("daily_cap")`, `expectHttpError(402)`;
  - wizard: `setKey`, `GEN_TIMEOUT` on the "Pick a face" wait;
  - live-and-session-tools: `setKey`.

  The user-visible steps stay identical. Verify `npm run e2e:mock` is green.
- [x] 4.6 Run `npm run e2e:http` and close every HTTP-only failure (G11) at its source, in the backend or the seed import, never by loosening a spec. Record each one in design.md's apply notes as a G11 row with its fix. If a fix would need a contract or UI change, stop and ask the user. Verify that `npm run e2e` (all three projects) is green on Windows with Edge, twice in a row.
- [x] 4.7 Delete `frontend/scripts/http-contract/acceptance.mjs` (D21) and any reference to it outside the archive. Update the README "Scripts" rows for `e2e`, `e2e:mock` and `e2e:http`, and the "How to run" section of `docs/qa/r1-test-report.md` (a note that the suite now runs on both clients). Verify with `grep` that there are no stale references, then commit.

## 5. Environment template and README (D15, D17, D20)

- [x] 5.1 Add every `config.KNOWN_VARS` name to `.env.example`:
  - `HORIZON_ROOT` and the 16 `HORIZON_AI_*` as a commented block, naming the `scripted` and `naive` values;
  - `OPENROUTER_API_KEY=` left empty.

  Add `backend/tests/unit/test_env_example.py`, which asserts that every known variable appears, the key is empty, and no `sk-or-[A-Za-z0-9_-]+` token exists. Verify that the test passes, and that it fails when a dummy name is appended to `KNOWN_VARS` in a scratch run.
- [x] 5.2 Add `.nvmrc` (`24`) (D20). Verify with `node --version` that it matches the major, and that the README names it.
- [x] 5.3 Rewrite the README's "Run locally with the backend" section (D15):
  1. prerequisites (Node 24, uv; Windows install commands first, then Unix);
  2. clone → `npm run setup` → `npm run dev` → open the app;
  3. the optional `.env` copy (the key can also be entered in Settings);
  4. Docling as a separate step 2, with its size and `/health` reporting;
  5. the commands table (`dev:mock`, `demo`, `test`, `e2e*`).

  Remove "What the backend does today…" and "No API key is read yet". Verify by following the section literally on Windows in a scratch clone, up to demo mode.
- [x] 5.4 Add the README "Secret hygiene" section: gitleaks as an optional pre-commit hook, the install command for Windows (`winget`) and Unix (`brew`/release binary), and a `.git/hooks/pre-commit` snippet. Check the snippet's CLI form against gitleaks' current release notes. No hook file is committed and no package is added. Verify with `git status` (no hook tracked) and with `package.json`/`pyproject.toml` diffs (no new dependency).
- [x] 5.5 Record the NFR-10 reading in `docs/backend/06` §M6: "Python + Node only" means Node + uv (uv installs Python). Verify that `ruff`, `mypy`, `pytest` and the frontend gates are green, then commit.

## 6. ASSETS.md and the asset check (D16)

- [x] 6.1 Write `frontend/scripts/assets-check/` (Node, no network, no dependencies). It:
  - builds the inventory (files under `seed/assets/**` and `frontend/public/**`, `@fontsource*` dependencies in `frontend/package.json`, track IDs in `seed/system-tracks.json`);
  - parses the table between `<!-- assets:begin -->` and `<!-- assets:end -->` in `ASSETS.md`;
  - enforces the D16 rules, printing each problem with its file or row, and a summary count on success.

  Add `npm run assets:check`. Verify with vitest unit tests on fixture inventories:
  - an unmatched file fails;
  - a stale row fails;
  - an `ai` row without a model fails;
  - a bad SPDX ID fails;
  - a track licence mismatch fails;
  - a complete table passes.
- [x] 6.2 Write `ASSETS.md`: human prose (what's a placeholder, D-52, and how real assets will be recorded), then rows for:
  - the placeholder portraits and themes (`procedural`);
  - `frontend/public` files;
  - each `@fontsource` family (author + `OFL-1.1`, checked against each package's `LICENSE`);
  - the three system tracks (`CC0-1.0`, as in `system-tracks.json`);
  - the synthesised SFX (`procedural`, no files, recorded for completeness).

  Verify that `npm run assets:check` exits 0 and its count matches the inventory.
- [x] 6.3 Point the doc mentions at the file: the `docs/requirements/06` §6 and `04` §7.1 notes that credits live in `ASSETS.md`, and the Settings → About text, which already names it, needs no change. Verify that the frontend gates are green, then commit.

## 7. Timing script and CI (D18, D19)

- [x] 7.1 Write `scripts/boot-timing.mjs` (repo root, Node, no dependencies) (D19). It:
  - clones the current commit (`git clone --no-local`) into a temp dir;
  - with `--cold`, points `npm_config_cache`, `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` at empty temp dirs;
  - runs `npm run setup`, starts `npm run dev`, and polls `http://localhost:5173/` and `/api/v1/worlds` until two seed worlds answer;
  - prints the setup, boot and total seconds (also to `$GITHUB_STEP_SUMMARY` when set);
  - kills the tree;
  - fails above 300 s;
  - removes the clone unless `--keep` is given.

  Verify on Windows with `node scripts/boot-timing.mjs --cold`. This is the **Windows fresh-clone acceptance measurement**: record the timings in `docs/backend/06` §M6.
- [x] 7.2 Write `.github/workflows/ci.yml` (D18):
  - push and pull_request on `dev` and `feat/**`;
  - the concurrency group, `permissions: contents: read`, `timeout-minutes: 45`, and no `secrets.*`;
  - checkout, setup-node (`.nvmrc`) and setup-uv;
  - the cold `boot-timing` step **before** any cache restore;
  - the warm setup with npm and uv caches;
  - the backend gates;
  - the frontend gates (`typecheck`, `lint`, `test`, `test:http`, `seed:check`, `fixtures:check`, `export-schema:check`, `assets:check`);
  - `playwright install --with-deps chromium` with a browser cache;
  - `PW_CHANNEL="" CI=1 npm run e2e`;
  - the failure artifact upload (7 days).

  Verify locally:
  - the YAML parses with a YAML parser already in `node_modules` (e.g. the transitive `yaml` package). If none is present, ask the user before downloading one;
  - every script it names exists in `package.json`;
  - `grep` finds no `secrets.` in it.
- [x] 7.3 Before handing over, check the Linux-only failure modes from D18 in the code: `127.0.0.1` in every server URL, process-group kills on Unix in both launchers, and no test relying on the machine time zone (grep for `datetime.now()` and `new Date()` in tests without a fixed clock). Fix anything found, and verify that the gates are still green on Windows. Then commit.

## 8. Final integration

- [x] 8.1 Run every gate on Windows and record the counts in `docs/backend/06` §M6:
  - backend `ruff check`, `mypy` and `pytest`;
  - frontend `typecheck`, `lint`, `test`, `test:http` (0 pending), `seed:check`, `fixtures:check`, `export-schema:check` and `assets:check`;
  - `npm run e2e` on Edge (both clients).
- [x] 8.2 Run `openspec validate http-client-parity --strict` and `openspec validate --specs --strict`, and verify both are clean. Commit the final checkpoint without attribution.
- [x] 8.3 **Manual (user):** the user pushes `feat/http-client-parity`, and the first CI run is green. If it fails only on Linux, fix it on the branch and repeat until green. Record the run's boot timings from the job summary in `docs/backend/06` §M6.
