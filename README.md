# Horizon

Horizon is an open-source multi-agent character sandbox. You summon AI personas, give them faces, moods and theme songs, and have them advise you, debate each other, or just live their lives.

> **Status:** the frontend is complete and runs on a built-in mock client with seeded demo data, which is what the live demo serves: no backend, API key or GPU needed. The local FastAPI backend ([docs/backend/](docs/backend/)) now runs the same app end to end: live chat, debates, character creation, knowledge upload and memory, with every paid call metered against your caps. The LangGraph agents come next.

**Live demo:** <https://horizon-seven-mauve.vercel.app> (desktop browser, 1280 × 720 or larger).

## Quick start

**You need:** Node.js **20.19+** or **22.12+** (Vite 8 requires one of these) and npm.

```bash
git clone https://github.com/weihang369/Horizon.git
cd Horizon/frontend
npm install
npm run dev
```

Open the URL Vite prints, usually <http://localhost:5173>.

- **Window size:** use a desktop browser window of at least **1280 × 720**. Smaller viewports show a "screen too small" notice.
- **Audio:** sound starts after your first click or key press, because of the browser's autoplay rules.

## Run locally with the backend

**You need:** Node.js **24** (pinned in [`.nvmrc`](.nvmrc)) and [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 for the backend by itself, so your system Python is untouched. Nothing else: no Docker, database server, GPU or PyTorch.

| | Windows (PowerShell) | macOS / Linux |
|---|---|---|
| Node.js 24 | `winget install OpenJS.NodeJS.LTS` | your package manager, [nvm](https://github.com/nvm-sh/nvm) or [nodejs.org](https://nodejs.org) |
| uv | `winget install --id=astral-sh.uv -e` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

**Step 1: the demo (about 5 minutes on a fresh clone).**

```powershell
git clone https://github.com/weihang369/Horizon.git
cd Horizon
npm run setup      # npm installs (root + frontend) and `uv sync` for backend/
npm run dev        # backend on http://127.0.0.1:8000 + the app on http://localhost:5173, talking to it
```

The commands are the same in a Unix shell. Open <http://localhost:5173>: the two demo worlds load from the backend in demo mode. Ctrl-C stops both processes. The backend keeps its data in `data/` at the repo root (git-ignored) and seeds the demo worlds on first start.

**Your OpenRouter key (optional).** Live chat and creation need a key from [openrouter.ai/keys](https://openrouter.ai/keys). Paste it in **Settings → Connection**: it's stored in `data/secrets.local.json` on this machine only. Alternatively, copy `.env.example` to `.env` and set `OPENROUTER_API_KEY` there; a key in `.env` or the environment wins over the one in Settings. Without a key, everything recorded still plays.

**Step 2: PDF and DOCX knowledge (optional, separate).** Markdown, plain text and pasted text work after step 1. PDF and DOCX uploads (including scanned PDFs, through OCR) need Docling with CPU PyTorch (no GPU) and its conversion models, about 1.4 GB, downloaded once:

```powershell
npm run setup:docling
uv run --project backend horizon models fetch
```

`GET /api/v1/health` reports `docling` as `not_installed`, `models_missing` or `ready`. A PDF or DOCX added before step 2 ends `failed`; **↻ Retry** converts it afterwards.

| Command (repo root) | What it does |
|---|---|
| `npm run setup` | Step 1: everything the demo needs |
| `npm run setup:docling` | Optional step 2: CPU PyTorch + Docling, then `horizon models fetch` (above) |
| `npm run dev` | Backend with auto-reload + the app on the backend (`VITE_HORIZON_CLIENT=http`, proxied `/api`) |
| `npm run dev:mock` | The app alone on the mock client, no backend (what the live demo runs) |
| `npm run demo` | Build the app and serve it and the API on one port, <http://127.0.0.1:8000> |
| `npm test` | Backend tests (pytest), frontend unit tests, then the client contract against a real test-mode backend |

- **Reset:** Settings → Data → "Reset demo data" restores the shipped demo and keeps your own worlds. `uv run --project backend horizon reset --factory --yes` wipes `data/` (except downloaded models).
- **Local only:** the backend binds to `127.0.0.1` and refuses any other address. The key never appears in logs, errors, exports or the ledger.
- **Tests never spend:** every automated test uses a fake provider and a fake key. Paid live checks are separate (`pytest -m live`) and never run by default.

### Secret hygiene

Your key belongs in Settings, `.env` or `data/`, all of which are git-ignored. As a second line of defence, we recommend [gitleaks](https://github.com/gitleaks/gitleaks) as a **pre-commit hook**. It is optional, and the repository doesn't install it for you.

1. Install it: `winget install gitleaks` (Windows), `brew install gitleaks` (macOS), or a release binary (Linux).
2. Create `.git/hooks/pre-commit` (no extension; Git for Windows runs it with its bundled shell):

   ```sh
   #!/bin/sh
   # Block a commit whose staged changes contain a secret.
   exec gitleaks git --pre-commit --staged --redact --verbose
   ```

   On Unix, make it executable: `chmod +x .git/hooks/pre-commit`. Older gitleaks 8.x releases spell the command `gitleaks protect --staged --redact --verbose`; check `gitleaks --help` for your version.

## A 5-minute tour

1. **Watch a debate.** On World Select, click **▶ Watch a 60-second AI debate**, then **Watch** (or press <kbd>Space</kbd>).
   - <kbd>Space</kbd> pauses and resumes.
   - **×2** and **×4** change the speed.
   - <kbd>I</kbd> opens the Insight drawer, which shows routing, recalled memory, context budget and cost.
   - **See the verdict** jumps to the outcome screen.
2. **Summon a character.** On a world's hub, choose **New character** and go through the 8-step wizard to the Summon reveal.
3. **Hang out.** **Sunny Hollow** has replays of a group chat, a Watch-mode scene and 1:1 chats.
4. **Go "live" without a key.** Press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd> to open the dev switcher.
   - Set a mock API key, then choose **Continue live** in a replay. The mock client streams replies as if a model were behind it.
   - You can also switch scenarios there, such as an empty world, an exhausted character, a rate limit or a cut-off stream.

### Keyboard shortcuts

| Key | Action |
|---|---|
| <kbd>?</kbd> | Show every shortcut |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd> | Open the mock state switcher (scenarios, mock key, demo speed) |
| <kbd>Space</kbd> | Play/pause a replay or debate |
| <kbd>←</kbd> / <kbd>→</kbd> | Previous/next turn in a replay; move between worlds on World Select |
| <kbd>I</kbd> | Open or close the Insight drawer in a session |
| <kbd>L</kbd> | Open the session log |
| <kbd>Ctrl</kbd>+<kbd>.</kbd> | Stop a streaming reply |
| <kbd>[</kbd> / <kbd>]</kbd> | Previous / next tab on a character profile |
| any key or click | Skip a ceremony (VS splash, round banner, Summon) |

To see the shared UI components, open `#/dev/kit`.

## Scripts

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
| `npm run seed:check` | Regenerate in memory and fail if `seed/` is out of date |
| `npm run budget` | Check bundle sizes after a build: entry ≤ 150 KB gzip, each lazy chunk ≤ 60 KB |

## Repository layout

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
├── backend/           FastAPI + SQLite local backend (uv); `horizon` CLI, tests, contract/schema.json
├── seed/              Demo worlds, characters, sessions, assets (served at /assets)
└── docs/
    ├── requirements/  Vision, functional requirements, screens, data contract, decision log
    └── ui-ux/         UI/UX design notes
```

The UI talks only to the typed `HorizonClient` interface. `frontend/src/client/index.ts` picks the `MockClient` by default (and on Vercel) or the `HttpClient` when built with `VITE_HORIZON_CLIENT=http`.

## Roadmap

1. **Requirements (BA).** Done. See [`docs/requirements/`](docs/requirements/).
2. **UI/UX.** The hardcoded frontend on the mock client (this stage).
3. **Backend.** FastAPI + SQLite that implements the same data contract.
4. **AI.** LangGraph multi-agent orchestration through OpenRouter (bring your own key; the key stays on the server).

## License

[MIT](LICENSE) © 2026 Tan Wei Hang
