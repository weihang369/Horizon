# Design

## Context

See proposal.md (Why). This section covers the state M6 starts from: the code on `dev` at `a3ae1d3`.

- **HttpClient.** Every `HorizonClient` method has a route ([HttpClient.ts](../../../frontend/src/client/http/HttpClient.ts)). Nothing rejects with `availableIn`. Transport maps a thrown `fetch` to `network` (retryable), and an error envelope to its own code.
- **Portable suite.** 55 tests: 9 M1b, 4 M2, 17 M3, 13 M4, 11 M5 and 1 M6. The HTTP run declares `supports: "M5"`, so 54 pass and 1 is pending ("network down rejects queries too; Reset demo data restores the shipped fixtures").
  - The HTTP harness ([clientContract.http.test.ts](../../../frontend/src/client/clientContract.http.test.ts)) does a factory reset and freezes the clock per test.
  - [globalSetup.ts](../../../frontend/scripts/http-contract/globalSetup.ts) starts `horizon serve` with `HORIZON_TEST=1` and a temp `HORIZON_DATA_DIR`. It does **not** isolate the repo-root `.env`.
- **Backend `/_test/scenario`** ([routes.py](../../../backend/horizon/api/routes.py), `SCENARIOS`) knows six scenarios: `character_exhausted`, `rush_hour`, `stream_cut`, `image_fail_partial`, `image_fail_all` and `song_fails`. `SCENARIO_MILESTONE` tags `network_down` and `no_worlds` as M6.
  - **The backend stacks scenarios:** `stream_faults.append`, `job_faults` and `clock.period_override` are only cleared by a factory reset.
  - **The mock replaces them** ([MockClient.ts](../../../frontend/src/mock/MockClient.ts) `applyScenarioState`/`hardReset`): any scenario switch, and `resetDemo` too (which resets to `default`), clears the previous scenario's faults.
- **Playwright 1.63** ([playwright.config.ts](../../../frontend/playwright.config.ts)):
  - 29 tests and two viewport projects (`desktop-1440`, `min-1280-reduced-motion` greps `@layout`), so 35 runs. Workers: 1 locally, 2 on CI.
  - One `webServer`: `vite --port 5186`, which is the MockClient.
  - Mock-only affordances (the QA round 1 report predicted them, docs/qa/r1-test-report.md §1):
    - `setMockKey` (the O18 switcher), in energy, live-and-session-tools and wizard;
    - the switcher's "Daily cap reached" scenario, in energy;
    - `?speed=4` in wizard, which the backend ignores;
    - `_mock` ids in tombstone (the backend imports `_mock` in test mode, OQ-6).
- **Test-mode timing.** The test-mode backend starts with a *released* `FrozenClock`, which is real time. Scripted pacing comes from `seed/runtime.json`: a portrait task takes 20 s, an emotion 15 s and a sheet 30 s. The mock compresses these with `?speed`.
- **Vite** proxies `/api` and `/assets/gen` to a hard-coded `http://127.0.0.1:8000`. `src/client/index.ts` picks the client from the build-time constant `VITE_HORIZON_CLIENT` (D-73). Any value other than `http` silently means mock.
- **Root scripts:**
  - `dev` runs concurrently `horizon serve --reload` with `vite --mode http`;
  - `demo` builds with `--mode http` and serves it from the backend;
  - `vercel.json` builds `npm run build --prefix frontend` with no mode.
- **Repo state:**
  - `.env.example` lists 9 variables. `config.KNOWN_VARS` has 25, including the 16 `HORIZON_AI_*`.
  - There's no `ASSETS.md`, no `.github/`, no `.nvmrc`. Python is pinned by `backend/.python-version` (3.12). Locally: Node v24.18.0, uv 0.11.25.
- **Shipped assets** (everything is a labelled placeholder today, D-52):
  - `seed/assets/placeholder/**`: 65 SVG portraits and 7 `.proc.json` themes;
  - `frontend/public/` (`favicon.svg`, `og.jpg`);
  - five `@fontsource` font packages;
  - three system tracks in `seed/system-tracks.json` (procedural, `credit` and `licence` already present);
  - SFX, synthesised in code (`src/audio/synth`).

Not re-decided here: D-73, D-81, D-82, D-67, the test router, OQ-6, the portable/mock-only split with `supports` gating, the console-clean rule, Edge as the default channel, and E2E's user-visible-only rule. Two decisions were taken with the user before this proposal: Unix verification is a GitHub Actions job, and gitleaks is a README recommendation only.

## Goals / Non-Goals

**Goals:**
- A written parity audit in which every gap is closed or justified.
- The portable suite with nothing pending on either client.
- The same Playwright specs green on both clients, with user-visible steps identical.
- A build that cannot accidentally ship the HttpClient to Vercel.
- A fresh clone reaches demo mode in ≤ 5 min. This is measured on Windows locally and on Linux in CI.
- `ASSETS.md` kept complete by a check, not by memory.

**Non-Goals:**
- Visual or layout E2E on HTTP. Layout is client-independent, so `@layout` stays a mock-only project.
- macOS CI, a Windows CI runner, or branch-protection settings. Those are GitHub settings the user owns.
- Installing gitleaks or any hook.
- Docling in CI. Step 2 stays manual (`pytest -m docling` locally).
- Changing seed timing to make HTTP E2E faster.
- Any contract or UI change. If the audit finds one is needed, implementation stops and asks the user.

## Decisions

### D1. The parity audit is a table, and every row ends closed or justified

doc 06's "close any HttpClient gaps" doesn't define a gap. Here a gap is any observable difference between the two clients that a portable test, an E2E spec or the UI can see. Method presence is not enough. The audit was done for this design from the code; apply re-verifies it by running the suites.

| # | Gap | Where | Resolution |
|---|---|---|---|
| G1 | `network_down` has no HTTP counterpart | portable M6 test | **Closed:** D2 (a transport fault in the HTTP harness) |
| G2 | `no_worlds` missing on the backend | portable M6 test | **Closed:** D4 |
| G3 | Backend scenarios stack; the mock's replace | `/_test/scenario` | **Closed:** D3 |
| G4 | Mock `resetDemo` clears the active scenario; backend reset-demo doesn't | reset in test mode | **Closed:** D3 (test mode only) |
| G5 | `daily_cap` scenario missing on the backend | energy E2E | **Closed:** D5 |
| G6 | World-name rules are tested mock-only, though the backend implements them (demo-data "Shipped seed world names are reserved") | `clientContract.mock.test.ts` | **Closed:** promoted to the portable suite as M1b (D6). If HTTP fails it, the backend is fixed to match, not the test |
| G7 | `test:http` reads the developer's repo-root `.env` (an `HORIZON_AI_*` override there changes the run) | `globalSetup.ts` | **Closed:** D8's isolation applies to both launchers |
| G8 | `setKey("sk-or-bad…")` is `invalid` immediately on the mock; the backend learns it from a 401 | settings | **Justified:** already specified (client-contract "Key validity is learned from the provider") and covered mock-only |
| G9 | `?speed=` and the O18 switcher exist only on the mock (`mockDev` is null on HTTP) | dev affordances | **Justified:** dev tools by design (D-73). E2E reaches them only through client-aware fixtures (D10) |
| G10 | Wizard placeholders are SVG on the mock and WebP from the backend | mock-only test | **Justified:** asset bytes aren't contract. Both are labelled placeholders |
| G11 | Visible text and counts from the seed differ between clients (e.g. "2 sources · cited 6×", "End of indexed passages · 6 of 6", Mei's failed source) | E2E on HTTP | **Found by running:** each difference the HTTP project shows is a parity bug, fixed in the backend or the seed import. Never fixed by loosening a spec. If a fix needs a contract or UI change, stop and ask the user |

The remaining mock-only tests are G8, G10, "demo speed ×4", "admin.resetDemo is the dev reset" (it checks the dev API wiring) and the three suite-integrity checks. Each keeps a one-line reason in its name or a comment.

### D2. `network_down` on HTTP is a transport fault injected by the harness

The HTTP harness constructs its `HttpClient` with a wrapped `fetch` (`HttpClientOptions.fetch` already exists). While `network_down` is active, the wrapper throws `TypeError("fetch failed")` before any request is sent. The transport turns that into `HorizonError { code: "network", retryable: true }`, which is what the mock rejects with. The wrapper doesn't touch the harness's own `/_test/*` calls or the `EventSource`. As on the mock, the next `setScenario` clears it.

The backend's `/_test/scenario` drops `network_down` from `SCENARIO_MILESTONE` and answers it with 422 `validation`, `details: { field: "id", clientSide: true }`, so a caller learns that this scenario is simulated by the client.

- *Rejected: a backend middleware that returns a 503 envelope with `code: "network"`.* It would only test envelope parsing, not the "server unreachable" path the http-client spec names. It would also make the server claim a network failure it never had.
- *Rejected: a middleware that aborts the connection.* ASGI connection aborts behave differently across uvicorn versions and between Windows' proactor loop and Linux, which makes for a flaky fault.

### D3. Scenarios replace each other, on both clients

Applying any `/_test/scenario` first clears the previous scenario's state: `clock.period_override`, `stream_faults`, `job_faults` and the D5 spend bias. Then it applies the new one. In test mode, `POST /admin/reset-demo` clears the same state, because the mock's `resetDemo` resets to `default`. A factory reset already clears it (`runtime.start`). This matches the mock's switcher semantics.

No existing HTTP test depends on stacking: each one applies at most one scenario after its factory reset. Apply confirms this by running the suite.

- *Rejected: keep stacking and add a `/_test/scenario {id:"default"}` clear.* That leaves a semantic difference between the clients that the portable suite would have to know about.

### D4. `no_worlds` deletes every world, user worlds included, as the mock does

The mock's `no_worlds` overlay empties worlds, characters, sessions, memory, knowledge and jobs, and `hardReset` doesn't refill emptied collections. User worlds go too. Settings, the key and ledger rows survive.

The backend does the same through the existing per-world delete path, for every world:
1. cancel ingestion (`rt.ingest.cancel_for`);
2. release live session actors and cancel non-terminal jobs, using the hooks `reset_demo` already uses;
3. run `worlds_svc.delete_world` (cascade);
4. remove world files.

It then publishes `mock.reset`. Settings, the key and ledger rows are untouched. A later `admin.resetDemo()` restores the two seed worlds; demo-data already requires that deleted seed worlds come back.

Apply must check that deleting worlds leaves ledger rows intact. If `usage_records` references characters with a hard FK, deleting worlds must null the reference, as world delete already must.

- *Rejected: `no_worlds` = factory reset with the seed import skipped.* It would also wipe settings and the key, unlike the mock, and leave the runtime in a "no seed" state that startup re-imports on the next restart.

### D5. `daily_cap` is a test-only spend bias on the clock

The mock's `daily_cap` sets `spentTodayUsd = 1.0` (= the default cap) and sets a key. On the backend, the scenario sets `clock.spend_bias_usd = max(0, cap − spent)`, next to the existing test-only `period_override`. Both `spent_today` implementations add it: `services/settings.py` for settings and usage, and `services/ledger.py` for preflight, top-up headroom and session pausing. Today's spend then equals the cap everywhere.

No ledger row is written, so `usage.list` stays truthful. The bias is cleared by D3. The scenario publishes `entity.changed {kind:"settings"}` so open screens re-query.

The backend does not invent a key (the mock's `KEY_SET`). The E2E spec sets a key with D10's `setKey` first, as it already does.

- *Rejected: insert a synthetic ledger row.* It would show in Usage, the CSV and the leak/ledger tests.
- *Rejected: PATCH the cap down to the current spend.* That's visible in Settings, and `dailyCapUsd` has a minimum.

### D6. The HTTP portable run declares `supports: "M6"`

With D2–D4, the M6 test runs on HTTP, and the http-client delta's "HTTP run in M6" scenario applies: nothing is pending on either client. The `Milestone` type and the gating stay, so a mis-tagged test still fails the suite. G6's world-name test moves into `clientContract.portable.ts` under `test("M1b", …)`.

- *Rejected: `supports: "all"`.* It means the same today, but `"M6"` states which backend the run proves.

### D7. Playwright projects per client, sharing one spec tree

| Project | Client | Server | Viewport | Grep | Workers |
|---|---|---|---|---|---|
| `mock-desktop` | MockClient | `vite --port 5186` (unchanged) | 1440×900 | all | config default |
| `mock-min` | MockClient | same | 1280×720, reduced motion | `@layout` | config default |
| `http-desktop` | HttpClient | backend :8786 + `vite --mode http --port 5187` | 1440×900 | all | **1** |

- Each project passes `use: { baseURL, client: "mock" | "http" }`. `client` is a custom fixture option the fixtures read (D10).
- `testProject.workers: 1` (Playwright ≥ 1.52; the repo has 1.63) serialises the HTTP project on its single shared backend, while the mock projects keep CI's 2 workers.
- Scripts:
  - `npm run e2e` runs all three projects (the M6 acceptance);
  - `e2e:mock` runs `--project=mock-*`;
  - `e2e:http` runs `--project=http-desktop`;
  - `e2e:prod` stays the mock projects against `vite preview`, which is what Vercel serves.
- `webServer` becomes an array, and each server starts only when a selected project needs it. Apply verifies that Playwright skips unneeded web servers for `--project` filters. If it doesn't, the config builds the array from the requested projects (`process.argv`).

- *Rejected: one backend per worker.* N backend startups and N temp dirs, to speed up a suite that is CPU-bound locally anyway.
- *Rejected: `@layout` on HTTP too.* Layout doesn't depend on the client, so it would only double the runtime.

### D8. Test-mode backends are isolated from the developer's machine

A Node launcher, `frontend/e2e/servers/backend.mjs`, is shared in spirit with `globalSetup.ts`: both use the same env recipe. It:
- creates a temp dir and sets `HORIZON_ROOT=<temp>`, so no repo-root `.env` is read (the M5 smoke trick);
- sets `HORIZON_SEED_DIR=<repo>/seed`, `HORIZON_DATA_DIR=<temp>/data`, `HORIZON_TEST=1`, `HORIZON_AI_PROFILE=scripted` and `HORIZON_LOG_LEVEL=WARNING`;
- spawns `uv run --project backend horizon serve --port 8786`.

Playwright waits on `http://127.0.0.1:8786/api/v1/health`. The launcher kills the process tree and removes the temp dir on exit. Test mode never reads a key in any case (openrouter-key spec), so this isolation also guards the rest of `.env`: AI overrides, data dir, time zone.

The HTTP Vite server reads its proxy target from `HORIZON_API_TARGET` (default `http://127.0.0.1:8000`, so `npm run dev` is unchanged), for both `/api` and `/assets/gen`.

`globalSetup.ts` gets the same `HORIZON_ROOT`/`HORIZON_SEED_DIR` treatment (G7).

- *Rejected: rely on `HORIZON_TEST=1` ignoring the key.* That covers the key only, not `HORIZON_AI_TURN=naive` or `HORIZON_DATA_DIR` left in a developer's `.env`.

### D9. Isolation: a factory reset before every HTTP test, with the clock left running

An auto fixture in the HTTP project calls `POST /admin/factory-reset` before the page opens. The clock stays released (real time): the UI's own timers, SSE pacing and the scripted pacing then behave as they will for a user, and D-82 is untouched.

- *Rejected: reset-demo between tests.* User data survives by design, so the wizard's "Sarah" and forks from the live spec would leak into later tests and their counts.
- *Rejected: a frozen clock with a Playwright "time pump".* `advance` awaits settlement, so a pump racing open SSE streams and browser timers is the "virtual time that never advances" hang this milestone was told to avoid.
- *Rejected: a new clock-rate knob.* It changes D-82's semantics to save seconds.

### D10. Client-aware fixtures keep user-visible steps identical

`e2e/fixtures.ts` gains the following, all keyed off the project's `client` option:

- **`setKey(page)`:** opens `#/settings` (the Connection tab is the default), types the fake key `sk-or-test-e2e-0001` into the key field, presses "Save key", waits for the saved state, then `page.goBack()`. The steps are the same on both clients; the QA report recommended this.
  - It replaces `setMockKey` everywhere.
  - The O18 switcher stays exercised in the mock project through `setScenario`.
- **`setScenario(page, id)`:**
  - mock: drives the O18 switcher UI (Ctrl+Shift+D → the scenario button → Close), as energy.spec does today;
  - HTTP: `request.post("/api/v1/_test/scenario")` through the page's base URL. The backend's global event (`entity.changed` or `mock.reset`) makes the open screen re-query.
- **`GEN_TIMEOUT`:** 8 s on the mock, 60 s on HTTP. It is used only on the expects that wait for a generation job (the wizard's "Pick a face"). `open(…, { speed })` keeps sending `?speed=`, which the backend ignores (G9).
- **`expectHttpError(page, status)`:** see D12.

Choosing the HTTP side of `setScenario` is a harness action, the same kind of thing as the mock switcher, so the E2E rule about user-visible steps still holds for everything the spec asserts.

### D11. Generation on HTTP runs at real speed

The wizard's portrait task takes 20 s of real time on HTTP, against 5 s on the mock at `?speed=4`. The spec already calls `test.slow()` (3 × 45 s). `GEN_TIMEOUT` covers the two waits that span a job. Expected HTTP wizard time is about 35 s; that budget is in the risks section.

- *Rejected: a faster `seed/runtime.json` for tests.* The two clients' timings would drift from the shipped config the spec checks against.

### D12. Console-clean on HTTP: expected statuses are declared, not ignored

Chromium logs `Failed to load resource: the server responded with a status of N (…)` as a console error for every non-2xx `fetch`. On HTTP, an expected refusal (the energy spec's 402 `daily_budget_exceeded`) would fail the console-clean fixture.

The fixture therefore accepts that exact line only for statuses the test declared with `expectHttpError(page, 402)`, and only in 4xx. A 5xx, or an undeclared status, still fails the test.

Apply verifies the exact line format on Edge and Chromium with a throwaway spec, before relying on it.

- *Rejected: allow-listing all 4xx lines.* It would hide real bugs, such as a 404 from a wrong route.
- *Rejected: a 200 with an error body.* It breaks the HTTP contract.

### D13. Named failure modes and their guards

| Failure mode | Guard |
|---|---|
| SSE streams left open across tests | Each test's browser context is closed before the next test's fixture runs, which ends its `EventSource`s. The factory reset (D9) runs after that close. The backend's SSE handler already exits on client disconnect. Apply adds a check that after the HTTP project, the backend reports no open SSE subscribers in its shutdown log line |
| Virtual time that never advances | E2E never freezes the clock (D9). `test:http` keeps its frozen clock, and every wait there is a harness `advance` |
| Port clash with a running `npm run dev` (8000/5173) or a second E2E run | E2E uses 8786/5187 (and 5186 for mock) with `--strictPort`. HTTP servers set `reuseExistingServer: false`, so an occupied port fails loudly instead of silently testing a developer's real backend and data |
| Leftover processes on Windows when Playwright exits or is interrupted | The launcher handles `SIGINT`/`SIGTERM`/`exit`, then kills its tree (`taskkill /T /F` on Windows, process group `SIGTERM` on Unix: uv → python → uvicorn). After that it removes the temp dir with retries, because Windows holds the SQLite/WAL handles until the process is gone |
| Expected-error console noise | D12 |
| HTTP-only text differences | G11: fix the backend, not the spec |

### D14. Client defaults: `dev` is HTTP, `dev:mock` is the frontend-only loop, and a guard protects builds

doc 06's "`http` for dev, `mock` for Vercel" refers to the documented one-command dev (doc 01 §8). The root `npm run dev` already means HTTP.

- A new root `npm run dev:mock` (`npm run dev --prefix frontend`) is the frontend-only loop that needs no backend. `frontend`'s own `npm run dev` stays mock.
- A Vite config guard, `clientGuard`, checks at config time:
  1. the value must be unset, `mock` or `http`; anything else fails ("HTTP" must not silently mean mock);
  2. `http` in a **build** requires `mode === "http"` (`--mode http`, i.e. `npm run demo`);
  3. `VERCEL=1` with `http` always fails.

  So a stray `VITE_HORIZON_CLIENT=http` in the Vercel dashboard fails the deploy instead of shipping a client that calls a backend that doesn't exist. Vercel's `vercel.json` build (no mode) stays mock.

- *Rejected: a runtime fallback to mock when `/api` doesn't answer.* D-73 makes the client a build-time constant, and a silent fallback hides a broken backend.
- *Rejected: flipping frontend `npm run dev` to HTTP.* That breaks the UI team's loop whenever no backend is running.

### D15. README: the fresh-clone path first, Windows first

The "Run locally with the backend" section is rewritten:
1. **Prerequisites:** Node 24 (`.nvmrc`) and uv (which installs Python 3.12 from `backend/.python-version` by itself). Windows install commands come first (`winget`/PowerShell installer), then Unix.
2. **Steps:** clone, `npm run setup`, `npm run dev`, then open `http://localhost:5173`. Copying `.env.example` to `.env` is optional: the key can be entered in Settings (D-67).
3. **Optional step 2:** Docling (`npm run setup:docling` + `horizon models fetch`) in its own subsection, with its size and the fact that `/health` reports `docling` separately.
4. **Commands** table, including `dev:mock`, `e2e`, `e2e:http` and `assets:check`.
5. **Secret hygiene:** recommends gitleaks as an optional pre-commit hook, with the install command for Windows and Unix and a `.git/hooks/pre-commit` snippet. Apply checks the exact gitleaks CLI form against its current release notes. No hook is committed and no dependency is added.
6. The stale lines are removed: "What the backend does today…" and "No API key is read yet".

**Challenge to NFR-10.** "Prerequisites are Python + Node only" was written before uv was adopted (M1b). uv is the Python toolchain here, and it installs Python itself. The README states Node + uv, and the decision log keeps NFR-10's intent: no Docker, Redis, external DB, GPU, CUDA or PyTorch for step 1. Apply records this in docs/backend/06 §M6 as an NFR-10 reading, not a new decision.

### D16. ASSETS.md is a machine-readable table, kept complete by an offline check

`ASSETS.md` at the repo root has prose for humans, then one table between `<!-- assets:begin -->` and `<!-- assets:end -->` with these columns:

| Column | Content |
|---|---|
| Pattern | A repo-relative glob, `npm:<package>` or `track:<id>` |
| Kind | The asset type |
| Source | `procedural`, `ai`, `library` or `font` |
| Credit / provenance | Who made it, or how it was generated |
| Licence | An SPDX identifier |

`npm run assets:check` (`frontend/scripts/assets-check/`, Node, no network) builds the inventory of shipped assets:
- every file under `seed/assets/**` and `frontend/public/**`;
- every `@fontsource*` dependency in `frontend/package.json`;
- every track ID in `seed/system-tracks.json`.

It fails on any of these:
- an inventory item that no row matches;
- a row that matches nothing;
- an `ai` row missing a model, date, prompt reference or technique (docs 06 §6);
- a `library` or `font` row missing a credit or a valid SPDX licence;
- a `track:` row whose licence disagrees with `system-tracks.json`.

Not shipped, so not inventoried: `data/` (user-generated assets) and `docs/**` (e.g. the D-61 image-model test results).

Today every row is `procedural` or `font`. The check exists so that real seed assets (the asset sprint, docs 06 §7) can't land without provenance. Settings → About's "Asset credits" text already points to `ASSETS.md`, so no UI change is needed.

- *Rejected: provenance fields inside each seed JSON.* Fonts and `public/` have no JSON to hold them, and a reviewer wants one page.

### D17. `.env.example` lists every variable the config reads, pinned by a test

Every name in `config.KNOWN_VARS` must appear in `.env.example`, as `NAME=` or, for advanced ones, as a commented `# NAME=` line:
- `HORIZON_ROOT` (commented, "tests and tools");
- the 16 `HORIZON_AI_*` (a commented block naming the `scripted`/`naive` values).

`OPENROUTER_API_KEY=` stays empty, and no line may hold an `sk-or-` token.

A unit test in `backend/tests/unit/` parses the file and asserts all three points. This is the same pattern as M5's `set(AI_VARS) == set(profile.ENV_VARS)`, so a new variable can't be added to config without being documented.

### D18. CI: one job on `ubuntu-latest`, no secrets, a cold timed boot and then the warm gates

`.github/workflows/ci.yml` defines one job, `ci`, with these settings:
- **Triggers:** `push` and `pull_request` for `dev` and `feat/**`;
- **Concurrency:** `ci-${{ github.ref }}`, cancel-in-progress;
- **Permissions:** `contents: read`, and no `secrets.*` reference anywhere;
- **Timeout:** 45 min. Actions are pinned to major versions.

| Step | What |
|---|---|
| 1 | Checkout; `actions/setup-node` with `node-version-file: .nvmrc`; `astral-sh/setup-uv` (pinned uv) |
| 2 | **Timed fresh-clone boot (cold):** `node scripts/boot-timing.mjs --cold` (D19) clones the checked-out commit into `$RUNNER_TEMP/fresh` with `git clone --no-local`. It points `npm_config_cache`, `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` at empty temp dirs, so nothing comes from a cache. Then it runs `npm run setup`, starts `npm run dev`, and polls until the app and `GET /api/v1/worlds` (two seed worlds through the Vite proxy) answer. It fails over 300 s and writes setup, boot and total seconds to `$GITHUB_STEP_SUMMARY` |
| 3 | Warm setup in the workspace, with npm (setup-node `cache: npm`, both lockfiles) and uv (`enable-cache`, keyed on `uv.lock`) caches |
| 4 | Backend gates: `ruff check`, `mypy`, `pytest` (its `addopts` already exclude the `live` and `docling` markers) |
| 5 | Frontend gates: `typecheck`, `lint`, `test`, `test:http`, `seed:check`, `fixtures:check`, `export-schema:check`, `assets:check` |
| 6 | `npx playwright install --with-deps chromium` (browser cache keyed on the Playwright version); `PW_CHANNEL="" CI=1 npm run e2e` |
| 7 | On failure: upload `frontend/test-results` and `playwright-report` (traces, screenshots) as an artifact, kept 7 days |

**Why cold timing first.** It runs before any cache is restored into the default locations, in a separate clone with redirected caches, so a cache restore can't make "fresh" look fast. The warm steps afterwards then don't pay twice for the download. GitHub's network is faster than a home connection, so the number is a lower bound. The Windows measurement (D19) is the user-facing one.

**Linux-only failure modes we expect:**
- **Path case:** an import that differs in case passes on Windows and fails on Linux. TypeScript's casing check (`forceConsistentCasingInFileNames`, on by default) catches it, and Python imports run in CI.
- **File locks:** the Windows-specific retry paths (factory reset, temp-dir removal) are no-ops on Linux, but must not *depend* on Windows timing.
- **Process cleanup:** process groups (`detached: true` + `kill(-pid)`) instead of `taskkill`.
- **Port binding and `localhost`:** Node ≥ 17 may resolve `localhost` to `::1`. All server URLs use `127.0.0.1` except Playwright's `baseURL`, and Vite listens on both by default.
- **Inotify limits** for `--reload`: only in the timed boot, and a watcher failure there fails the boot visibly.
- **Time zone:** the runner is UTC and the config defaults to `Asia/Kuala_Lumpur`. Tests already pin or freeze time; any test that silently relied on the machine zone surfaces here and is fixed in the test.
- **Line endings:** schema export and `seed:check` must be byte-stable on LF checkouts.

**Diagnosing a CI-only flake:** the artifact (step 7) holds Playwright traces (`trace: "retain-on-failure"` already). `retries: 1` on CI stays, and a test that passes only on retry is listed as flaky in the report. The backend launcher writes its stderr to the job log.

- *Rejected: a matrix (Windows + Linux).* Windows is measured locally by the user's own machine, and a Windows runner doubles the minutes.
- *Rejected: running the gates against the cold clone.* It would make every gate pay the cold install.

### D19. One timing script, used by CI and by the Windows measurement

`scripts/boot-timing.mjs` (repo root, Node, no dependencies) takes `--cold` (redirect caches to empty temp dirs) and `--keep` (keep the clone for inspection). Its steps:
1. clone the current commit;
2. run `npm run setup`;
3. start `npm run dev`;
4. poll until demo mode answers;
5. print the timings;
6. kill the tree.

The user's Windows measurement (`node scripts/boot-timing.mjs --cold`) and CI run the same code, so "≤ 5 min" means the same thing on both. Docling is never run by it; its time is reported separately in the README.

### D20. `.nvmrc` pins Node 24

Local development uses Node v24.18.0, and `package.json` has no `engines` field. `.nvmrc` holds `24`, read by CI's `setup-node` and by nvm/fnm users. Python stays pinned by `backend/.python-version`.

### D21. The M1b acceptance walk-through script is retired

`frontend/scripts/http-contract/acceptance.mjs` was M1b's hand-run check of the real app over HTTP. `npm run e2e:http` now covers it and more, so it's deleted to keep one source of truth. Archived M1b tasks still mention it as history.

## Risks / Trade-offs

- **Chromium's resource-error line format differs between Edge versions** → D12 matches on the stable prefix plus the status number, and apply checks it on both Edge (local) and Chromium (CI) before relying on it.
- **Real-time generation makes HTTP E2E slow and timing-sensitive on a 2-vCPU runner** → `GEN_TIMEOUT` of 60 s against a 20 s task, `test.slow()`, and `retries: 1` on CI. Expected HTTP project time is about 3 min (factory reset + 29 tests).
- **Per-test factory reset cost** (wipe + seed + `_mock` import, about 1–2 s) → accepted. It's the price of exact isolation.
- **Playwright starting web servers for filtered-out projects** → verified in apply. If it does, the config builds the server list from the selected projects (D7).
- **`no_worlds` touching ledger FKs** → verified in apply (D4).
- **G11 may find visible-text differences that need UI or contract changes** → implementation stops and asks the user (standing rule).
- **The CI cold boot depends on PyPI, npm and python-build-standalone availability** → a download outage fails the job with a clear step name. Re-run is the remedy, and no retry loop is added to hide it.
- **GitHub Actions minutes** → about 15 min per run, cancelled on superseded pushes (concurrency group).
- **Cold timing on GitHub isn't a home machine** → the Windows run (D19) is the acceptance number, and CI's is the Unix evidence and regression alarm.

## Migration Plan

- No data migration and no contract change.
- **Order:**
  1. backend scenarios (D3–D5);
  2. HTTP harness (D2, D6) to make `test:http` fully green;
  3. Vite target + guard (D8, D14);
  4. Playwright projects and fixtures (D7–D13);
  5. docs, `.env.example`, ASSETS (D15–D17);
  6. CI and timing (D18–D20).

  Each step ends at a green checkpoint commit.
- **Rollback:** revert the squash commit. CI can be disabled on its own by deleting `.github/workflows/ci.yml`.
- **First CI run:** the user pushes `feat/http-client-parity`. If CI fails only on Linux, the fix lands on the branch before the squash merge.

## Open Questions

- Whether to make the `ci` job a required check for PRs into `dev`. That's a GitHub branch-protection setting the user can turn on after the first green run. It changes nothing here.

## Apply notes

- **D8, launcher form.** The E2E launcher is `frontend/e2e/servers/backend.ts`, run as `node e2e/servers/backend.ts` (Node 24 strips the types), not a `.mjs`. It imports the same recipe as `test:http`'s global setup, `frontend/scripts/test-backend/env.ts`. The recipe also drops any inherited `HORIZON_*` and `OPENROUTER_API_KEY`, because the environment outranks `.env`.
- **D13, forced kills.** Verified on Windows: `taskkill /T /F` on the launcher, which is how Playwright stops a web server there, leaves no uv, `horizon.exe` or Python process and frees the port. No handler runs in that case, so each temp dir records its launcher's PID, and every start sweeps the dirs of dead launchers.
- **D12, the console line.** Verified on Edge 154 and Chromium 153 (Playwright's bundled build). A 4xx `fetch` logs at `error` level with the text `Failed to load resource: the server responded with a status of <N> (<Reason>)`, for example `… status of 402 (Payment Required)`. The URL isn't in the text; it is in `ConsoleMessage.location().url`. The allowance therefore matches the prefix and the status, and also requires the location to be an `/api/` URL.
- **Dev server binds `::1`.** On this machine Vite's `localhost` resolves to `::1` only, and `127.0.0.1:5173` refuses connections. Anything that polls the dev server (the timing script, D19) uses `localhost`, not `127.0.0.1`. Backend URLs stay `127.0.0.1`, because uvicorn binds there explicitly.
- **A load-sensitive backend test.** `tests/sessions/test_prefetch.py::test_preflight_lock_wait_is_measured` asserts a wall-clock p95 under 20 ms. It failed once while the HTTP contract run and Vite builds ran in parallel on the same machine, and passed 3 of 3 alone. It predates M6. CI's 2-vCPU runner may trip it; if it does, the CI fix is to run it in isolation, not to raise the bound.
- **G11 findings from the first `e2e:http` run** (29 of 31 passed; no backend errors):
  - **G11a, tombstone song.** `GET /characters/{tombstone}/song` was 404; the mock resolves `null`. character-lifecycle says reads on a tombstone resolve (memory and knowledge come back empty), and the tombstone's songs are deleted. Fixed in the backend: the read resolves, and returns `null` for a tombstone. The M1b test that pinned the 404 now asserts `null`. No contract change: `ThemeSong | null` was already the type.
  - **G11b, wizard "Skip for now" bounced back to Emotions.** This was a race in the UI that only shows over HTTP. The step saves `creationStep`, then navigates, and the gate redirect checks reachability against the *cached* character. On the mock, `entity.changed` fires inside `update()`, so the cache is fresh before navigation. Over HTTP the event arrives later on SSE, so the stale `creationStep` redirected the route back. Fixed by priming the character cache with `update()`'s answer (`putResource`) in the wizard's `save()` and in the Emotions `skip()`. Nothing visible changes, and the mock behaves as before; this is a bug fix, not a UI change, so it was made without stopping.
- **D19, measured.** The cold Windows run took 18.8 s (clone 1.4, setup 10.9, dev → demo mode 6.5) against the 300 s budget. The temp caches really were empty: 43 MB of npm tarballs, 110 MB of uv packages and a Python 3.12.13 runtime were downloaded, and the clone's venv was built on that Python. On Windows the script runs npm through the shell as one command string (npm is `npm.cmd`), which avoids Node's DEP0190 warning.
- **D18, verified offline.** The workflow parses with PyYAML (already in the backend venv; nothing downloaded). Every `npm run` it names exists, it contains no `secrets.` reference, and the cold boot step comes before every cache restore. Its first real run is task 8.3.
