# Contributing to Horizon

Thanks for taking a look. Bug reports, fixes and ideas are all welcome. This page covers how to set up, what to run
before a pull request, and how changes are made here.

## Set up

Follow [Run locally with the backend](README.md#run-locally-with-the-backend): Node.js 24 and uv, then

```bash
npm run setup      # npm installs (root + frontend) and uv sync for backend/
npm run dev        # backend on :8000 and the app on :5173
```

PDF and DOCX knowledge needs the optional Docling step (`npm run setup:docling`, then `horizon models fetch`). You
don't need an OpenRouter key to work on Horizon: every automated test runs on a fake provider.

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
- **No secrets in commits.** Keys belong in Settings, `.env` or `data/`, all git-ignored. The README suggests
  [gitleaks](README.md#secret-hygiene) as a pre-commit hook.

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
