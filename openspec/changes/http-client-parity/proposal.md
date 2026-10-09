# Proposal

## Why

M1b–M5 each shipped the HttpClient methods for their own routes. The app now runs against the backend, but three things are still unproven:
- **The two clients agree.** One portable contract test is still pending on HTTP (`[pending M6]`). Two scenarios the portable harness names, `network_down` and `no_worlds`, have no backend counterpart.
- **The E2E suite covers the backend.** All 29 Playwright tests (35 runs across the two viewport projects) run only against the MockClient, and four specs use mock-only affordances.
- **A stranger can run the backend from a fresh clone.** The README still says "No API key is read yet". `ASSETS.md`, which Settings → About links to, doesn't exist. Nothing runs off Windows.

M6 is the last backend milestone (doc backend/06), so it has to prove all three.

## What Changes

- **Parity audit and closure:**
  - an audit table of every `HorizonClient` method against both clients, recorded in design.md;
  - `network_down` becomes a transport fault in the HTTP harness, the only way to exercise the real "server unreachable" path;
  - the backend gains `no_worlds` and `daily_cap` test scenarios;
  - test scenarios *replace* each other instead of stacking, as on the mock;
  - the HTTP portable run declares `supports: "M6"`, so nothing is pending.
- **Playwright on both clients:**
  - `mock-*` and `http-*` projects run the same specs.
  - Under `http-*`, a launcher script starts a test-mode backend on its own port, with a temp data dir, `HORIZON_TEST=1` and `scripted` AI, plus a Vite `--mode http` dev server whose proxy target comes from the environment.
  - Mock-only steps become client-aware fixtures with identical user-visible steps: `setKey` through Settings → Connection, `setScenario`, and generation timeouts.
  - Each HTTP test starts from a factory reset.
  - The console-clean rule gains a narrow, opt-in allowance for HTTP status lines the test expects.
- **Client defaults and a build guard:**
  - `npm run dev` (root) stays on `http`, and a new root `npm run dev:mock` gives the frontend-only loop;
  - a Vite config guard fails any build that would bundle the HttpClient outside `--mode http`, and any Vercel build (`VERCEL=1`) on `http`;
  - an unknown `VITE_HORIZON_CLIENT` value also fails the build.
- **Docs and hygiene:**
  - the README's run section is rewritten for a fresh clone (Windows first, Docling as a separate step 2);
  - stale milestone text is removed;
  - a "Secret hygiene" section recommends gitleaks as an optional pre-commit hook. No hook or dependency is added.
- **`ASSETS.md`:**
  - one row per shipped asset group: provenance for AI assets, credit and licence for library assets and fonts, "procedural" for placeholders;
  - an offline `assets:check` that fails on any shipped file with no row, any row matching no file, or any row missing a required field.
- **`.env.example` covers every variable** `config.py` reads, including the 16 `HORIZON_AI_*` overrides. A backend test pins this.
- **CI:** a single GitHub Actions job on `ubuntu-latest` (`.github/workflows/ci.yml`) is the "one Unix" evidence. It runs:
  - every backend and frontend gate;
  - Playwright on both clients (bundled Chromium);
  - a timed cold-cache fresh-clone boot to demo mode, which fails over 5 minutes.

  The job uses no secrets.
- No contract change and no new `HorizonClient` method. `SCHEMA_VERSION` stays `1`. No paid or live calls.

## Capabilities

### New Capabilities
- `e2e-suite`: the Playwright suite as an acceptance suite for both clients: projects, server lifecycle, isolation, client-aware fixtures, and the console-clean rule.
- `continuous-integration`: the GitHub Actions job: what it runs, on which triggers, with which caches and no secrets, and the timed fresh-clone boot.
- `asset-credits`: `ASSETS.md` as the record of every shipped asset's provenance or credit, and the offline check that keeps it complete.

### Modified Capabilities
- `http-client`: "Client selection" gains the dev defaults (`dev` / `dev:mock`) and the build guard.
- `client-contract`: "Portable suite runs on every client" gains the M6 run (nothing pending). `network_down` on HTTP is a transport fault that the HTTP harness injects. Scenarios replace one another.
- `http-api`: "Test-only control routes" gains `no_worlds` and `daily_cap`. Applying a scenario first clears the previous one's faults and overrides.
- `local-backend`:
  - "One-command local development" gains `dev:mock`, the fresh-clone time budget and the README run instructions;
  - "Committed environment template" requires every variable the config reads, pinned by a test;
  - a new "Secret hygiene guidance" requirement: a README recommendation only, with no hook and no dependency.

## Impact

- **Frontend:**
  - `src/client/clientContract.http.test.ts` (harness fetch fault, `supports: "M6"`);
  - `vite.config.ts` (proxy target from env, client guard);
  - `playwright.config.ts` (projects per client, two web servers, per-project workers);
  - `e2e/fixtures.ts` (client-aware fixtures);
  - `e2e/energy.spec.ts`, `wizard.spec.ts` and `live-and-session-tools.spec.ts` (use the new fixtures);
  - new: `e2e/servers/` launcher, `scripts/assets-check/`;
  - `package.json` scripts (`e2e`, `e2e:mock`, `e2e:http`, `assets:check`).
- **Backend:**
  - `horizon/api/routes.py` (`/_test/scenario`: `no_worlds`, `daily_cap`, replace semantics);
  - `horizon/domain/clock.py` (test-only spend bias next to `period_override`);
  - the two `spent_today` implementations (`services/settings.py`, `services/ledger.py`);
  - new tests in `tests/integration` and `tests/unit`.
- **Repo root:**
  - `package.json` (`dev:mock`), `README.md`, `.env.example`;
  - new `ASSETS.md`, `.github/workflows/ci.yml`, `.nvmrc`.
- **Docs:** `docs/backend/06` §M6 and §test strategy notes; `docs/backend/01` §8 (`dev:mock`, the guard).
- **Dependencies:** none added. CI downloads the Playwright Chromium build at run time.
- **Operational:** the user pushes the branch to start the first CI run, and the job uses the repo's GitHub Actions minutes.
