# Contributing to Horizon

Thanks for taking a look. Bug reports, fixes and ideas are all welcome. This page covers how to set up, what to run
before a pull request, and how changes are made here.

## Set up

Follow [Run it locally](README.md#run-it-locally): Node.js 24 and uv, then

```bash
npm run setup      # npm installs (root + frontend) and uv sync for backend/
npm run dev        # backend on :8000 and the app on :5173
```

PDF and DOCX knowledge needs the optional Docling step (`npm run setup:docling`, then `horizon models fetch`).
`GET /api/v1/health` reports `docling` as `not_installed`, `models_missing` or `ready`; a PDF or DOCX added before the
step ends `failed`, and **↻ Retry** converts it afterwards. You don't need an OpenRouter key to work on Horizon: every
automated test runs on a fake provider.

**Only the frontend?** The app runs on its in-browser mock client with no backend and no Python (Node.js 20.19+ or
22.12+ is enough for Vite 8):

```bash
cd frontend
npm install
npm run dev        # what the live demo runs
```

| Command (repo root) | What it does |
|---|---|
| `npm run setup` | npm installs (root + frontend) and `uv sync` for `backend/` |
| `npm run setup:docling` | Optional: CPU PyTorch + Docling, then `horizon models fetch` |
| `npm run dev` | Backend with auto-reload + the app on the backend (`VITE_HORIZON_CLIENT=http`, proxied `/api`) |
| `npm run dev:mock` | The app alone on the mock client, no backend |
| `npm run demo` | Build the app and serve it and the API on one port, <http://127.0.0.1:8000> (`HORIZON_PORT`) |
| `npm test` | Backend tests (pytest), frontend unit tests, then the client contract against a real test-mode backend |

`uv run --project backend horizon reset --factory --yes` wipes `data/` (except downloaded models).

### Frontend scripts

Run these inside `frontend/`:

| Command | What it does |
|---|---|
| `npm run dev` | Start the dev server with hot reload |
| `npm run build` | Type-check and build a production bundle into `frontend/dist/` |
| `npm run preview` | Serve the production build locally |
| `npm test` | Run the unit and contract tests (Vitest) |
| `npm run e2e` | Run the Playwright end-to-end suite in Microsoft Edge on both clients: the mock (its own dev server on port 5186) and a throwaway test-mode backend (ports 8786 and 5187) |
| `npm run e2e:mock` | The end-to-end suite on the mock only |
| `npm run e2e:http` | The end-to-end suite on the backend only (scripted AI, temporary data, never your `data/` or `.env`) |
| `npm run typecheck` | Run the TypeScript project build with no output |
| `npm run lint` | Run oxlint |
| `npm run seed:build` | Regenerate `seed/` from the screenplays and fixtures in `frontend/scripts/seed-build/` |
| `npm run assets:check` | Fail if a shipped asset has no credit or provenance row in [`ASSETS.md`](ASSETS.md) |
| `npm run seed:check` | Regenerate in memory and fail if `seed/` is out of date |
| `npm run budget` | Check bundle sizes after a build: entry ≤ 150 KB gzip, each lazy chunk ≤ 60 KB |

### Repository layout

```
Horizon/
├── frontend/          React 19 + TypeScript + Vite app
│   └── src/
│       ├── client/    HorizonClient interface; index.ts picks the implementation
│       ├── mock/      MockClient: in-browser fake backend, scripted replies, scenarios
│       ├── contract/  Shared types for the data contract
│       ├── features/  Screens: shell, worlds, wizard, profile, session, ensemble, insight, settings, dev
│       ├── ui/ theme/ motion/ audio/ vfx/ character/   Design system and engines
│       └── router/    Hash router (#/w/:world/...)
├── backend/           FastAPI + SQLite local backend (uv)
│   ├── horizon/       The app: api/, sessions/, ai/ (agents, Jev decisions, memory), gateway/, services/, evals/
│   ├── tests/         pytest (fake provider, no spend)
│   └── manual/        Paid OpenRouter and real Docling checks, run by hand
├── seed/              The shipped demo: worlds, characters, recorded sessions, art, songs, documents
├── evals/             Evaluation data: datasets, scripted scenes, transcripts, a frozen seed
├── openspec/          Specs (current behaviour) and each milestone's archived design
├── scripts/           Repo-level scripts (the fresh-clone boot timing CI runs)
└── docs/              Requirements, UI/UX, backend and AI designs, measured checks: see docs/README.md
```

The UI talks only to the typed `HorizonClient` interface. `frontend/src/client/index.ts` picks the `MockClient` by
default (and on Vercel) or the `HttpClient` when built with `VITE_HORIZON_CLIENT=http`.

### In the app

- <kbd>?</kbd> shows every keyboard shortcut. <kbd>Space</kbd> plays and pauses a replay or debate, <kbd>←</kbd> /
  <kbd>→</kbd> step through turns, <kbd>I</kbd> opens the Insight drawer, <kbd>L</kbd> the session log, and
  <kbd>Ctrl</kbd>+<kbd>.</kbd> stops a streaming reply.
- <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd> opens the mock state switcher: set a mock key and choose **Continue
  live** in a replay (the mock client streams replies as if a model were behind it), or switch scenarios such as an
  empty world, an exhausted character, a rate limit or a cut-off stream.
- `#/dev/kit` shows the shared UI components.
- Sound starts after your first click or key press (the browser's autoplay rules); windows smaller than 1280 × 720
  show a "screen too small" notice.

### Developer switches

- **AI profile:** with a key, the app uses the `agent` profile (Jev decides, DeepSeek speaks); without one, `scripted`.
  Set `HORIZON_AI_PROFILE=naive` for the baseline (plain DeepSeek replies, the Jev router), or `HORIZON_AI_<PORT>` to
  change one port. The backend's start-up log names the profile and lists what every port resolved to.
- `HORIZON_CAPTURE_AI_CALLS=1` keeps each AI call's redacted prompt and reply in the local database for 7 days, for
  debugging with `horizon eval capture`. Forget and deletes clear it.
- `HORIZON_LANGSMITH=1` (plus `LANGSMITH_API_KEY` and the optional package, `uv sync --project backend --group
  tracing`) **sends** chat and document text to LangSmith for tracing. Leave it off unless you mean to share that text.

The last two are off by default. Every setting is listed in [`.env.example`](.env.example).

## Before you open a pull request

Run what CI runs ([.github/workflows/ci.yml](.github/workflows/ci.yml)). From the repo root:

```bash
# backend
cd backend
uv run ruff check .
uv run mypy
uv run pytest -q
cd ..

# frontend
cd frontend
npm run typecheck
npm run lint
npm test                 # unit tests and the client contract on the mock
npm run test:http        # the same contract against a throwaway test-mode backend
npm run seed:check       # seed/ matches its sources
npm run fixtures:check
npm run e2e              # Playwright on both clients (Microsoft Edge locally; set PW_CHANNEL="" for bundled Chromium)
```

The full backend suite is long (2,000+ tests). While you work, run the folders you touched, for example
`uv run pytest tests/knowledge`.

## Rules the tests rely on

- **Tests never spend money.** Nothing in `backend/tests` or `frontend/` may call OpenRouter. Checks against the real
  API, and real Docling conversions, live in [`backend/manual/`](backend/manual/README.md) and are run by hand.
- **Both clients stay in step.** The UI talks only to `HorizonClient`. A behaviour change goes into the `MockClient`
  (`frontend/src/mock/`) and the backend alike, and a test in `frontend/src/client/clientContract.portable.ts` runs on
  both.
- **The seed is generated.** Don't edit `seed/` by hand: change `frontend/scripts/seed-build/` and run
  `npm run seed:build` (then `npm run fixtures:build`).
- **Jev's questions are fingerprinted.** Files in `backend/horizon/ai/questions/` and the datasets under `evals/` are
  hashed into stored answers and eval baselines. Changing their text is a versioned change, not a typo fix.
- **No secrets in commits.** Keys belong in Settings, `.env` or `data/`, all git-ignored. As a second line of
  defence, use [gitleaks](#secret-hygiene) as a pre-commit hook.

## Secret hygiene

[gitleaks](https://github.com/gitleaks/gitleaks) as a **pre-commit hook** is optional, and the repository doesn't
install it for you.

1. Install it: `winget install gitleaks` (Windows), `brew install gitleaks` (macOS), or a release binary (Linux).
2. Create `.git/hooks/pre-commit` (no extension; Git for Windows runs it with its bundled shell):

   ```sh
   #!/bin/sh
   # Block a commit whose staged changes contain a secret.
   exec gitleaks git --pre-commit --staged --redact --verbose
   ```

   On Unix, make it executable: `chmod +x .git/hooks/pre-commit`. Older gitleaks 8.x releases spell the command
   `gitleaks protect --staged --redact --verbose`; check `gitleaks --help` for your version.

## How changes are made

- **Branches:** work on a branch from `dev` (`feat/…`, `fix/…`). Pull requests target `dev` and are squash-merged.
  `main` holds releases.
- **Bigger changes start with a design.** Horizon uses [OpenSpec](https://github.com/Fission-AI/OpenSpec): a change
  gets a proposal, a design and tasks under `openspec/changes/`, and its requirement deltas are merged into
  `openspec/specs/` when it is archived. Small fixes don't need one.
- **Say why in the code.** Comments cite the decision or requirement behind a rule (`D-118`, `CHAT-02`, `memory D13`);
  [docs/README.md](docs/README.md) explains the codes. If you change a decided behaviour, add a decision to
  [the decision log](docs/requirements/09-decision-log.md).
- **Commit messages:** one plain sentence saying what changed for a user or a developer, for example
  "Knowledge: a file over 10 MB is refused before the upload".

## Reporting problems

- **Bugs and ideas:** open a GitHub issue. Say what you did, what you expected and what happened; a screenshot helps.
- **Security problems:** please don't open a public issue. See [SECURITY.md](SECURITY.md).

By contributing you agree that your work is released under the project's [MIT licence](LICENSE).
