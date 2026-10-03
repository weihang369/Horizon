# M1b acceptance record (task 13.1)

**Date:** 2026-10-04 · **Machine:** Windows 11, Edge (Playwright channel `msedge`), Node 24.18, uv 0.11 / CPython 3.12.13.

**How:** `npm run dev` at the repo root (backend on :8000, Vite on :5173 in `--mode http`, so `VITE_HORIZON_CLIENT=http`), then `node frontend/scripts/http-contract/acceptance.mjs`. The script drives the real app with no mock anywhere and fails on any console error or warning. It passed twice in a row.

| Acceptance item | Result |
|---|---|
| Both seed worlds browse (world select + hub) | ✓ Meridian Council, Sunny Hollow |
| Every seed character profile opens | ✓ Amara, Mei, Victor, Hana, Rin, Takeshi |
| Knowledge tab on the backend | ✓ seed sources read `keyword_only` with the "keyword only" badge (OQ-1); Mei's password-protected DOCX stays `failed` with its shipped error |
| Every seed session replays to the end | ✓ Four-day work week (31 log items), Three-day headache (9), Long day (6), Dinner's on me (16), Rainy Sunday (14) |
| World create (through the UI), rename, delete | ✓ stored by the backend; list re-queries after `entity.changed` |
| Duplicates refused | ✓ `409 conflict` for a case-insensitive duplicate and for a shipped seed name |
| Console | ✓ clean |

**Also checked (task 12.2):**
- `npm run dev` + a real Ctrl-C (sent with `GenerateConsoleCtrlEvent`) stops every node, uv and python process, and ports 8000 and 5173 close, with `--reload` on.
- SSE streams through the Vite proxy unbuffered: replay frames arrive at once, and the 15 s keepalive follows.
- `npm run demo` serves the built app (deep links, Vite's hashed bundles), the seed assets and the API on :8000.

**Observation (not an M1b defect; for M3/M6):** when the URL hash jumps straight from one replay to another, the session screen is reused. Under the HttpClient it shows the previous replay for a moment while the next session's events load. A key press in that moment (e.g. End on the Seek slider) acts on the stale replay, and then the right session loads at 0:00. The MockClient loads synchronously, so it never shows this. The walk-through loads each replay fresh. A loading state keyed by session id would remove it; it belongs with the session-screen work in M3, or with E2E-on-backend in M6.
