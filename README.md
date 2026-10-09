# Horizon

Horizon is an open-source multi-agent character sandbox. You summon AI personas, give them faces, moods and theme songs, and have them advise you, debate each other, or just live their lives.

> **Status:** UI preview. The frontend is complete and runs on a built-in mock client with seeded demo data. You don't need a backend, an API key or a GPU. The local FastAPI backend is being built milestone by milestone ([docs/backend/](docs/backend/)): today it serves the demo data (browse, profiles, replays) and world create/rename/delete. The LangGraph agents come after.

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

**You also need:** [uv](https://docs.astral.sh/uv/). It fetches Python 3.12 for the backend by itself; your system Python is untouched.

```bash
git clone https://github.com/weihang369/Horizon.git
cd Horizon
npm run setup      # npm installs (root + frontend) and `uv sync` for backend/
npm run dev        # backend on http://127.0.0.1:8000 + the app on http://localhost:5173, talking to it
```

Ctrl-C stops both. The backend keeps its data in `data/` at the repo root (gitignored) and seeds it with the demo worlds on first start.

| Command (repo root) | What it does |
|---|---|
| `npm run setup` | Step 1: everything the demo needs |
| `npm run setup:docling` | Optional step 2: CPU PyTorch + Docling for PDF and DOCX knowledge uploads. Then run `uv run --project backend horizon models fetch` once to download the conversion models into `data/models/` (Markdown, text and pasted text work without either) |
| `npm run dev` | Backend with auto-reload + Vite in `--mode http` (`VITE_HORIZON_CLIENT=http`, proxied `/api`) |
| `npm run demo` | Build the app and serve it and the API on one port, <http://127.0.0.1:8000> |
| `npm test` | Backend tests (pytest), frontend unit tests, then the client contract against a real test-mode backend |

- **Reset:** Settings → Data → "Reset demo data" restores the shipped demo and keeps your own worlds. `uv run --project backend horizon reset --factory --yes` wipes `data/` (except downloaded models).
- **What the backend does today:** reads, replays and world CRUD. Live chat, character creation, top-ups and knowledge upload arrive in later milestones; until then the app says "Not available on the local backend yet". The mock (`cd frontend && npm run dev`) still does everything.
- The backend binds to `127.0.0.1` only. No API key is read yet.

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
