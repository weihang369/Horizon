# Horizon

Horizon is an open-source multi-agent character sandbox. You summon AI personas, give them faces, moods and theme songs, and have them advise you, debate each other, or just live their lives.

> **Status:** UI preview. The frontend is complete and runs on a built-in mock client with seeded demo data. You don't need a backend, an API key or a GPU. The FastAPI backend and the LangGraph agents come next.

## Quick start

**You need:** Node.js **20.19+** or **22.12+** (Vite 8 requires one of these) and npm.

```bash
git clone <this repo>
cd Horizon/frontend
npm install
npm run dev
```

Open the URL Vite prints, usually <http://localhost:5173>.

- **Window size:** use a desktop browser window of at least **1280 × 720**. Smaller viewports show a "screen too small" notice.
- **Audio:** sound starts after your first click or key press, because of the browser's autoplay rules.

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
| `npm run e2e` | Run the Playwright end-to-end suite in Microsoft Edge (starts its own dev server on port 5186) |
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
├── seed/              Demo worlds, characters, sessions, assets (served at /assets)
└── docs/
    ├── requirements/  Vision, functional requirements, screens, data contract, decision log
    └── ui-ux/         UI/UX design notes
```

The UI talks only to the typed `HorizonClient` interface. Today `frontend/src/client/index.ts` exports the `MockClient`; when the backend lands, it's a one-line swap to the HTTP client.

## Roadmap

1. **Requirements (BA).** Done. See [`docs/requirements/`](docs/requirements/).
2. **UI/UX.** The hardcoded frontend on the mock client (this stage).
3. **Backend.** FastAPI + SQLite that implements the same data contract.
4. **AI.** LangGraph multi-agent orchestration through OpenRouter (bring your own key; the key stays on the server).

## License

[MIT](LICENSE) © 2026 Tan Wei Hang
